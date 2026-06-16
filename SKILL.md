---
name: hftoolbox
description: Use this skill when building, modifying, or extending the HFToolbox open-source project. Covers backend API endpoints, frontend pages, module metadata, HF API integration, background tasks, caching, and project conventions.
---

# HFToolbox Developer Skill

HFToolbox is a self-hosted HackForums dashboard built on HF API v2.
Stack: FastAPI backend, React 18 / Vite frontend, SQLite by default, MySQL when `DB_HOST` is set.
Repo: https://github.com/AuJusDemon/HFToolbox

## Project Structure

```text
backend/
  main.py             FastAPI app, core endpoints, startup, background loops
  server.py           production wrapper around main.app
  auth.py             OAuth2 flow under /auth/*
  db.py               framework-level persistence and shared local history tables
  _db_compat.py       SQLite/MySQL _db() compatibility shim
  db_connection.py    MySQL pool and SQL translation layer
  HFClient.py         HF API v2 wrapper and rate-limit tracking
  hf_cache.py         resource cache tables and TTL logic
  hf_service.py       stale-while-revalidate helpers and token selection
  module_registry.py  module manifest and router registry
  modules/
    autobump/         bump jobs, settings, logs, poller
    bytes_crawler/    bytes analytics endpoint; crawl loop lives in main.py
    contracts/        package kept for contract-related module namespace
    posting/          scheduled posts, drafts, replies, image upload
    sigmarket/        signature marketplace status, browse, buy, rotation
    wire/             curated/news threads, replies, curators

frontend/src/
  App.jsx             router
  store.js            Zustand auth, settings, module prefs, caches
  index.css           design system and utility classes
  core/
    Shell.jsx         sidebar, topbar, notifications, rate display
    Dashboard.jsx     overview cards
    Login.jsx         OAuth landing/login page
    Settings.jsx      settings and module visibility
    api.js            fetch wrapper
    *Page.jsx         feature pages
```

## Backend Endpoints

Use the existing FastAPI patterns in `main.py` or a module router. Always gate user data by the session UID.

```python
@app.get("/api/myfeature")
async def my_feature(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)

    from HFClient import HFClient
    client = HFClient(token)
    data = await client.read({"me": {"uid": True}})
    if not data:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)

    return {"result": data}
```

## Modules

For a new module with a router, create:

```text
backend/modules/mymodule/
  __init__.py
  router.py
  mymodule_db.py
```

Register public metadata and the router in `backend/modules/__init__.py`:

```python
from modules.mymodule.router import router as mymodule_router

register(
    ModuleMeta(
        id="mymodule",
        name="My Module",
        description="Short user-facing description.",
        icon="MOD",
        category="tools",
        api_cost="low",
    ),
    mymodule_router,
)
```

`main.py` imports `modules` during lifespan startup and mounts every registered router. Core app surfaces can still be mounted directly in `main.py` when they need special startup behavior.

## DB Helpers

Module DB files should import `_db` from `_db_compat`. Do not open raw SQLite connections in module code.

```python
from _db_compat import _db


def init_mymodule_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS my_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid VARCHAR(64) NOT NULL,
                data TEXT NOT NULL,
                created_at BIGINT DEFAULT (strftime('%s','now'))
            )
        """)


def list_rows(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM my_table WHERE uid=? ORDER BY created_at DESC",
            (uid,),
        ).fetchall()
        return [dict(r) for r in rows]
```

Call module init functions from lifespan startup if the module has tables needed before first request.

Always wrap DB work from async endpoints:

```python
rows = await asyncio.to_thread(list_rows, uid)
```

## HF API Usage

Use `HFClient` for HF API calls. Use `hf_service.get_or_fetch()` when adding cacheable/shared reads.

```python
from HFClient import HFClient

client = HFClient(token)
data = await client.read({
    "me": {"uid": True, "bytes": True, "vault": True},
    "threads": {"_uid": [int(uid)], "_page": 1, "_perpage": 30,
                "tid": True, "subject": True, "lastpost": True},
})
```

Rules:
- Max 4 endpoint keys per `read()` call.
- Endpoint keys must be unique in a single call.
- `_uid`, `_from`, and `_to` filters need integer UIDs.
- `_perpage` max is 30.
- All HF values arrive as strings; cast explicitly.
- Use `int(float(x))` for bytes amounts.
- Single result can be a dict, multiple results are lists; normalize both.
- `posts._uid` is oldest-first. `threads._uid` page 1 is newest/most recently active.
- Handle `None` from `client.read()` / `client.write()`.

See `HF_API_REFERENCE.md` for endpoint details, fields, batching examples, and known API limitations.

## Unified User Dashboard Refresh

`backend/dashboard_refresh.py` is the canonical home for all bundled private per-user HF reads.

Do NOT scatter new private HF reads into feature routes or module pollers. To add a new dashboard resource:
1. Add the HF API fields to the relevant ask dict in `refresh_user_dashboard()`.
2. Write a `_section_<name>()` helper that processes the result and writes to local DB.
3. Call it (wrapped in `try/except`) from `refresh_user_dashboard()`.

`main.py`'s `_crawl_user_bytes()` delegates to `refresh_user_dashboard()`. The scheduler,
activity trigger, and idle-return trigger all call through this path.

## Cache-First Endpoint Pattern

Feature routes must serve local DB or cache first and make HF calls only as a bounded cold fallback:

```python
# Correct: local DB first, live only when empty
rows = await asyncio.to_thread(db.get_bytes_history, uid, 30, 0)
if rows:
    return {"transactions": rows}
# ... cold fallback live fetch here

# Correct: shared cache with stale-while-revalidate
data, is_stale = await hf_service.get_or_fetch(
    cache_key     = f"user:{target_uid}:profile",
    resource_type = "user_profile",
    fetch_fn      = lambda: _do_fetch(target_uid, token),
    uid           = uid,
)
```

Shared cacheable resources (user profile, contract detail, thread metadata, sigmarket browse,
user activity/trust) use stable `hf_cache` keys and `hf_service.get_or_fetch()` so one
request can refresh a shared entry and all concurrent requests see the same cached data.

## HF Failure Handling

`HFClient.read()` returns `None` for all failure types. Callers must handle `None` cleanly:

- **CF HTML challenge**: HF returns HTTP 200 with HTML body. `HFClient` returns `None`
  immediately without retrying. Do not retry CF failures in a loop - they do not clear in
  milliseconds. Serve stale cache when available.
- **Timeout/network error**: `HFClient` retries with backoff up to `_MAX_RETRIES` times,
  then returns `None`. Serve stale cache.
- **401 AuthExpired**: `HFClient` raises `AuthExpired`. Routes must catch this, clear the
  session, and return 401 to the frontend.
- **Rate limit exhaustion**: check `_throttle_level()` before non-critical background calls.

Each feature should degrade independently. A `None` from sigmarket must not block bytes or
autobump. A CF hit on one resource must not stall other in-flight requests.

## Autobump Safety Rule

Autobump MUST live-read from HF immediately before every bump decision. No exceptions.

- Timer mode: live-read `threads._tid` and verify `lastpost`/`lastposteruid`/`numreplies`.
- Page-1 mode: live-read forum page 1 and verify the thread position.
- If the live read returns `None` (CF, timeout, or network failure): skip/defer and log.
  Never bump from stale cache data.

Cache and local DB may be used for UI display, job lists, stats, and bump history only.

## Frontend Pages

Create feature pages under `frontend/src/core/` unless there is a clear module-specific frontend folder already in use.

```jsx
import { useEffect, useState } from 'react'
import { api } from './api.js'

export default function MyFeaturePage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/myfeature')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="empty"><div className="spin" /></div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-head">
          <span className="card-icon">MOD</span>
          <span className="card-title">My Feature</span>
        </div>
        <div className="card-body">
          {/* content */}
        </div>
      </div>
    </div>
  )
}
```

Register routes in `App.jsx` and nav links in `Shell.jsx` when the page should be user-facing.

## Design System

Use `frontend/src/index.css` variables and existing utility classes.

Important classes:

```text
.card, .card-head, .card-body, .card-icon, .card-title
.btn, .btn-acc, .btn-ghost, .btn-danger
.inp, .input, .tog, .tog.off
.tab, .tab.on
.badge, .badge-acc, .badge-yel, .badge-blue, .badge-red, .badge-dim
.col-lbl, .spin, .empty, .pg, .pg-btn, .pg-info, .grid2, .up
```

Rules:
- Use CSS variables instead of hardcoded colors.
- Keep dashboard/tool screens dense and scannable.
- Use `minmax(0, 1fr)` for grid tracks that contain long text.
- Keep card nesting shallow.
- Make loading, empty, error, and disabled states explicit.
- Avoid console logging in committed frontend code.

## Auth And Frontend API

```js
import useStore from '../store.js'
import { api } from './api.js'

const user = useStore(s => s.user)
const data = await api.get('/api/myfeature')
await api.post('/api/myfeature', { key: 'value' })
```

The `api` wrapper includes credentials, parses JSON, throws on non-OK responses, and redirects to `/` on most 401 responses.

## Background Tasks

Long-running work belongs in an existing loop only when it is truly shared app behavior. Keep intervals explicit and rate-limit aware.

```python
_last_mytask = 0.0
MYTASK_INTERVAL = 300

if now - _last_mytask >= MYTASK_INTERVAL:
    try:
        await my_background_task()
        _last_mytask = _t.time()
    except Exception as e:
        log.exception("mytask error: %s", e)
```

## Caching

For simple per-user dashboard cache:

```python
cached = await asyncio.to_thread(db.get_dash_cache, uid, "my_key", 1800)
if cached:
    return cached

await asyncio.to_thread(db.set_dash_cache, uid, "my_key", result)
```

For reusable HF resources, prefer `hf_service.get_or_fetch()` with a stable cache key and resource type.

## Conventions

- Keep secrets in `.env`, never source files.
- Never block the event loop with direct DB work.
- Keep API responses scoped to `request.session["uid"]` unless the data is intentionally public.
- Delete-account support lives in `db.delete_user_data()`; add new uid-owned tables there.
- User-facing write endpoints should invalidate or refresh affected caches.
- Prefer local DB/cache reads over extra HF API calls.
- Do not reintroduce contract-template creation code; the live app does not ship it.
- Contract approval state requires both `status` and `istatus`/`ostatus`. The API can return `status="0"` for a pending contract (treat the same as `status="1"`). Use `istatus` (initiator's approval flag) and `ostatus` (other party's flag) to determine which party still needs to act; do not rely on `status` alone.
