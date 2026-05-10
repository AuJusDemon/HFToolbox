---
name: hftoolbox
description: Use this skill when building, modifying, or extending the HFToolbox open-source project. Covers adding new backend API endpoints, new frontend pages, new modules, HF API integration patterns, the design system, and project conventions. Trigger whenever the user asks to add a feature, fix a bug, or build something new for HFToolbox.
---

# HFToolbox — Developer Skill

HFToolbox is a self-hosted personal dashboard for HackForums, built on HF API v2.
Stack: **FastAPI (Python) backend** + **React 18 / Vite frontend** + **SQLite database**.
Repo: https://github.com/AuJusDemon/HFToolbox

---

## Project Structure

```
backend/
  main.py                        # FastAPI app, all core endpoints, background tasks
  auth.py                        # OAuth2 flow (/auth/*)
  db.py                          # SQLite helpers — framework-level tables only
  HFClient.py                    # HF API v2 wrapper
  crypto.py                      # Token encryption (Fernet)
  scheduler.py                   # Module poll scheduler
  module_registry.py             # Module plugin contract
  modules/
    autobump/                    # Auto bump scheduler
    bytes_crawler/               # Background bytes history crawler
    contracts/                   # Contracts module
    posting/                     # Thread posting, drafts, reply queue
    sigmarket/                   # Signature marketplace

frontend/src/
  App.jsx                        # Router
  store.js                       # Zustand (auth, user, settings, module prefs)
  index.css                      # Full design system — CSS variables + utility classes
  core/
    Shell.jsx                    # Sidebar nav + topbar + profile strip
    Dashboard.jsx                # Main dashboard (overview cards)
    Login.jsx                    # OAuth login page
    Settings.jsx                 # Settings page
    api.js                       # fetch wrapper (get/post/patch/delete/put)
    [FeatureName]Page.jsx        # One file per full page
```

---

## Adding a New Backend Endpoint

### 1. Simple endpoint in `main.py`

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
    data = await client.read({ ... })
    return {"result": data}
```

### 2. New module with its own router

Create `backend/modules/mymodule/`:

```
modules/mymodule/
  __init__.py    # Poll handler (if background task needed)
  router.py      # FastAPI APIRouter
  mymodule_db.py # SQLite helpers for this module's tables
```

**router.py pattern:**
```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import asyncio
import db

router = APIRouter(prefix="/api/mymodule", tags=["mymodule"])

def _auth(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, JSONResponse({"error": "unauthenticated"}, status_code=401)
    return uid, None

@router.get("/data")
async def get_data(request: Request):
    uid, err = _auth(request)
    if err: return err
    # ... your logic
    return {"data": []}
```

**Mount in `main.py` lifespan:**
```python
from modules.mymodule.router import router as mymodule_router
app.include_router(mymodule_router)
```

### 3. DB helpers pattern (`mymodule_db.py`)

```python
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/hf_dash.db")

def _connect():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_mymodule_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS my_table (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                uid        TEXT NOT NULL,
                data       TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
```

Call `init_mymodule_db()` from the main lifespan startup block in `main.py`.

### 4. Async DB calls — always use `asyncio.to_thread`

Never call SQLite directly from an async context — it blocks the event loop.

```python
# Right
result = await asyncio.to_thread(db.get_something, uid)

# Wrong
result = db.get_something(uid)
```

---

## Adding a New Frontend Page

### 1. Create the page file

`frontend/src/core/MyFeaturePage.jsx`:

```jsx
import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api.js'
import useStore from '../store.js'

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (ms == null) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

export default function MyFeaturePage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    api.get('/api/myfeature')
      .then(d => { if (d) { setData(d); setLoading(false) } })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])
  usePolling(load, 60000)

  if (loading) return <div className="empty"><div className="spin" /></div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-head">
          <span className="card-icon">🔧</span>
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

### 2. Register the route in `App.jsx`

```jsx
const MyFeaturePage = lazy(() => import('./core/MyFeaturePage.jsx'))

// Inside the dashboard routes:
<Route path="myfeature" element={<Suspense fallback={<Spin/>}><MyFeaturePage /></Suspense>} />
```

### 3. Add nav link in `Shell.jsx`

```jsx
<NavLink to="/dashboard/myfeature" icon="🔧" label="My Feature" />
```

---

## Design System

All styles are in `frontend/src/index.css`. Use CSS variables and utility classes — never hardcode colors or sizes.

### CSS Variables

```css
/* Backgrounds (darkest to lightest) */
--bg        /* page background */
--s1        /* sidebar */
--s2        /* card surface */
--s3        /* input / subtle surface */

/* Borders */
--b1  --b2  --b3

/* Text */
--text      /* primary */
--sub       /* secondary */
--dim       /* muted / labels */
--muted     /* mid-level */

/* Accent colors */
--acc       /* teal — primary accent */
--acc2      /* teal low opacity — backgrounds */
--acc3      /* teal medium opacity */
--red   --red2
--yellow  --yellow2
--blue  --blue2

/* Typography */
--sans      /* body font */
--mono      /* monospace / numbers / labels */

/* Misc */
--r         /* border radius (4px) */
--ease      /* transition timing (130ms ease) */
--topbar-h  /* topbar height (42px) */
```

### Utility Classes

```
.card                 card container
.card-head            card header row (flex, gap, border-bottom)
.card-body            card body (padding: 12px 13px)
.card-icon            emoji icon in card header
.card-title           title text in card header

.btn                  base button
.btn-acc              teal primary button
.btn-ghost            ghost/outline button
.btn-danger           red danger button

.inp  .input          text input / select / textarea
.tog                  toggle switch (.tog.off = off state)

.tab                  tab button
.tab.on               active tab

.badge                small label pill
.badge-acc .badge-yel .badge-blue .badge-red .badge-dim

.col-lbl              column header label (uppercase, small, mono)
.spin                 loading spinner (14x14)
.empty                centered empty state container
.pg                   pagination row
.pg-btn               pagination arrow button
.pg-info              pagination info text
.grid2                2-column grid with alignItems:start
.up                   fade-up entry animation

.sp                   group tag pill
.sp-rank .sp-vendor .sp-comm .sp-dim
```

### Card pattern

```jsx
<div className="card">
  <div className="card-head">
    <span className="card-icon">📊</span>
    <span className="card-title">Title</span>
    <span className="badge badge-acc">LIVE</span>            {/* optional */}
    <button className="btn btn-ghost"
      style={{ marginLeft: 'auto', fontSize: 10 }}>         {/* optional right-side action */}
      Action
    </button>
  </div>
  <div className="card-body">
    {/* content */}
  </div>
</div>
```

### Column header + row grid pattern

```jsx
<div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,80px) minmax(0,1fr) 60px',
  gap: 8, padding: '0 0 5px', borderBottom: '1px solid var(--b1)', marginBottom: 4 }}>
  <span className="col-lbl">Amount</span>
  <span className="col-lbl">Reason</span>
  <span className="col-lbl" style={{ textAlign: 'right' }}>When</span>
</div>

{items.map(item => (
  <div key={item.id} style={{ display: 'grid',
    gridTemplateColumns: 'minmax(0,80px) minmax(0,1fr) 60px',
    gap: 8, alignItems: 'center', padding: '6px 0',
    borderBottom: '1px solid rgba(21,30,46,.5)' }}>
    <span style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{item.amount}</span>
    <span style={{ fontSize: 12, color: 'var(--sub)', overflow: 'hidden',
      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.reason}</span>
    <span style={{ fontSize: 10, color: 'var(--dim)', textAlign: 'right',
      fontFamily: 'var(--mono)' }}>{ago(item.dateline)}</span>
  </div>
))}
```

### Common helpers (copy into any page)

```js
const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now()/1000) - ts
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}

const fmt = n => Number(n || 0).toLocaleString()
```

---

## HF API Usage

### HFClient — always use this, never raw fetch

```python
from HFClient import HFClient
client = HFClient(token)          # token from db.get_token(uid)
data = await client.read({...})   # POST /read
data = await client.write({...})  # POST /write
```

### Key rules

- Max **4 endpoints per `read()` call** — 5+ returns silent 503
- All API values are **strings** — cast everything explicitly
- `int(float(x))` for bytes amounts — never `int(x)` directly on float strings
- Single result = dict, multiple results = list — always normalize:
  ```python
  rows = data.get("things", [])
  if isinstance(rows, dict): rows = [rows]
  ```
- `_uid`, `_from`, `_to` filters require **integer UIDs** not strings
- `_perpage` max is **30**
- Rate limit: ~240 calls/hour — track via `x-rate-limit-remaining` header

### Typical read call

```python
data = await client.read({
    "me": {"uid": True, "bytes": True, "vault": True, "unreadpms": True,
           "postnum": True, "threadnum": True, "reputation": True},
    "threads": {"_uid": [uid_int], "_page": 1, "_perpage": 30,
                "tid": True, "subject": True, "fid": True,
                "lastpost": True, "lastposteruid": True, "numreplies": True},
    # up to 2 more endpoints here
})
if not data:
    return JSONResponse({"error": "HF API unavailable"}, status_code=503)
```

### Full API reference

See `HF_API_REFERENCE.md` in the repo root for all endpoints, field listings, type code tables, batching examples, and confirmed gotchas.

---

## Auth & Session

```python
# Backend — get current user in any endpoint
uid = request.session.get("uid")
if not uid:
    return JSONResponse({"error": "unauthenticated"}, status_code=401)

token = await asyncio.to_thread(db.get_token, uid)
```

```js
// Frontend — auth state from Zustand
const user    = useStore(s => s.user)     // {uid, username, avatar, groups}
const logout  = useStore(s => s.logout)
```

---

## API Calls from Frontend

```js
import { api } from './api.js'

api.get('/api/myfeature')
api.post('/api/myfeature', { key: 'value' })
api.patch('/api/myfeature/123', { key: 'value' })
api.put('/api/myfeature/123', { key: 'value' })
api.delete('/api/myfeature/123')
```

Returns parsed JSON or throws on error. Automatically redirects to `/` on 401.

---

## Background Tasks

Add to the unified scheduler loop in `main.py` inside `_unified_loop()`:

```python
_last_mytask    = 0.0
MYTASK_INTERVAL = 300  # seconds

if now - _last_mytask >= MYTASK_INTERVAL:
    try:
        await my_background_task()
        _last_mytask = _t.time()
    except Exception as e:
        log.exception("My task error: %s", e)
```

---

## Caching

Use the built-in dash cache for any data that doesn't need to be live on every request:

```python
# Check cache first
cached = await asyncio.to_thread(db.get_dash_cache, uid, "my_cache_key", 1800)  # 1800s TTL
if cached:
    return cached

# ... fetch fresh data ...

# Store in cache
await asyncio.to_thread(db.set_dash_cache, uid, "my_cache_key", result)
return result
```

Force-refresh pattern: accept `?force=true` query param and skip cache check when set.

---

## Conventions

- **Never block the event loop** — wrap all DB calls in `asyncio.to_thread()`
- **Always handle None from HF API** — `client.read()` returns `None` on network error or 503
- **Equal-width grid columns** — use `minmax(0, 1fr)` not `1fr`; grids containing sticky children need `alignItems: 'start'`
- **Sticky elements** — topbar is `42px` (`--topbar-h`); sticky content needs `top: 50` to clear it
- **No hardcoded colors** — always use CSS variables
- **Timestamps** — all HF API timestamps are Unix epoch strings; cast with `int()`
- **Client-side filtering** — filter/sort in the frontend where possible to avoid extra API calls
- **Pagination** — `_perpage` max 30; paginate with `_page` starting at 1
- **Delete account data** — if your module adds tables with a `uid` column, add them to `delete_user_data()` in `db.py`
