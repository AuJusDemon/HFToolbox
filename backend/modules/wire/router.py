"""
modules/wire/router.py — API routes for The Wire.
"""

import re
import asyncio
import time
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db
from .wire_db import (
    init, is_curator, is_lead_curator, is_admin, get_my_role,
    get_curators, add_curator, remove_curator, set_curator_role,
    add_thread, get_threads, get_thread, remove_thread, update_thread_stats,
    get_all_tids, get_my_submissions,
    get_cached_replies, get_reply_cache_ts,
    upsert_replies, clear_reply_cache,
    VALID_TAGS, get_latest_hf_news,
    get_thread_refresh_count, log_thread_refresh, REFRESH_MAX,
    update_firstpost_content, set_hf_news_flag,
)

log = logging.getLogger("hftoolbox.wire")
router = APIRouter(prefix="/api/wire", tags=["wire"])
init()

FID_NAMES = {
    "2":"Site News","4":"Beginner Hacking","5":"Coders Lounge","6":"Graphics",
    "8":"Computing Lounge","10":"Hacking Tools","12":"Bragging Rights",
    "25":"The Lounge","32":"Movies, TV & Videos","37":"Music","43":"Website Hacking",
    "44":"Buyers Bay","46":"Social Media Hacks","47":"Hacking Tutorials",
    "50":"Website Construction","65":"Gaming","79":"Mobile Smartphones",
    "85":"Linux","87":"Computer Hardware","89":"News & Happenings",
    "91":"VPN, Proxies & Socks","92":"Botnets & Botting","103":"SQL Injection",
    "104":"WiFi / Wireless Hacking","106":"Service Offerings","107":"Premium Sellers",
    "110":"Malware Removal","111":"Deal Disputes","112":"Anime & Manga",
    "113":"Keyloggers","114":"Remote Admin Tools","117":"Mobile Development",
    "118":"Software Development","121":"Shopping Deals","126":"Cryptography",
    "127":"Referrals","133":"Rate My Graphic","134":"Suggestions & Ideas",
    "136":"Ebook Bazaar","137":"Apple iOS","139":"Social Networking",
    "142":"SEO & Internet Marketing","143":"Hosting & Servers",
    "145":"Hosting Services","155":"Member Contests","157":"GFX Contests",
    "158":"Free Graphic Help","159":"MacOS","160":"Video Editing",
    "163":"Marketplace Discussions","167":"Sports","170":"Adult Content",
    "171":"VPN & Proxy Services","172":"Website Showcase","176":"Member Sales",
    "180":"Innuendo","182":"Currency Exchange","183":"Web Development",
    "186":"Free Services & Giveaways","192":"Android OS","193":"IoT & Electronics",
    "205":"Appraisals & Pricing","217":"Jobs & Partnerships","218":"Virtual Game Items",
    "219":"Graphics Market","221":"Free Money Ebooks","225":"Webmaster Market",
    "229":"Reverse Engineering","231":"Pentesting & Forensics","240":"Networking",
    "245":"Surveys","248":"Graphic Resources","255":"Rewards & Favors",
    "260":"Education & Careers","261":"Pets & Animals","262":"Health Wise",
    "263":"Social Media Services","268":"CPA / PPD","281":"Markets & Finance",
    "287":"Malware & Viruses","291":"Online Accounts","293":"Photography",
    "299":"Cryptography Market","308":"Service Requests","318":"Vices",
    "322":"OpSec & OSINT","339":"Hash Bounties","347":"Microsoft Windows",
    "354":"Food & Cooking","370":"Gambling","374":"Premium Tools",
    "375":"HF API","380":"Crypto Currency","385":"Cars & Motors",
    "400":"White Hat Hacking","402":"Promotional Advertising","403":"Brotherhood",
    "404":"Adult Zone Accounts","405":"Blackhat Training","431":"AI Discussion",
    "433":"Hacktivism","434":"Bug Bounties","456":"Academy","459":"VIBE",
    "461":"Prompt Engineering","462":"AI Programming","463":"AI Marketing",
    "464":"AI Tools & APIs","465":"AI Art & Music","466":"Jailbreaking & Modding",
}

PERPAGE_THREADS = 10
PERPAGE_REPLIES = 30
REPLY_CACHE_TTL = 3600 * 2


def _uid(request: Request) -> str:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401, "Not authenticated")
    return uid


def _uid_opt(request: Request) -> str | None:
    """Like _uid but returns None instead of raising for unauthenticated requests."""
    return request.session.get("uid") or None


def _parse_tid(raw: str) -> str | None:
    raw = raw.strip()
    if raw.isdigit():
        return raw
    m = re.search(r'[?&]tid=(\d+)', raw)
    if m:
        return m.group(1)
    return None


def _normalize_avatar(av: str) -> str:
    if not av:
        return ""
    if av.startswith("http"):
        return av
    return "https://hackforums.net/" + av.lstrip("./")


def _enrich(t: dict) -> dict:
    t["fid_name"] = FID_NAMES.get(str(t.get("fid", "")), f"FID {t.get('fid','?')}")
    for k, v in t.items():
        if hasattr(v, "isoformat"):
            t[k] = str(v)
    return t


# ── Pydantic models ────────────────────────────────────────────────────────────

class SubmitBody(BaseModel):
    url:        str
    tag:        str
    note:       str = ""
    post_count: int = 1     # how many posts to fetch (1=OP only, 2+=multipost)
    is_hf_news: bool = False  # marks this as an HF News edition (pinned separately)


class ReplyBody(BaseModel):
    message: str


class AddCuratorBody(BaseModel):
    uid:  str
    role: str = "curator"


class SetRoleBody(BaseModel):
    role: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/users/resolve")
async def resolve_usernames(request: Request, uids: str = ""):
    """Resolve UIDs to usernames. Hits uid_usernames cache first, HF API for misses."""
    uid_list = [u.strip() for u in uids.split(",") if u.strip().isdigit()]
    if not uid_list:
        return {}

    # Step 1: hit uid_usernames cache (zero HF calls)
    cache    = await asyncio.to_thread(db.get_uid_usernames, uid_list)
    result   = {uid: info["username"] for uid, info in cache.items() if info.get("username")}
    missing  = [int(u) for u in uid_list if u not in result]

    # Step 2: HF API for anything not in cache — only if authenticated
    caller = _uid_opt(request)
    if missing and caller:
        try:
            token = await asyncio.to_thread(db.get_token, caller)
            if token:
                from HFClient import HFClient
                hf = HFClient(token)
                data = await hf.read({
                    "users": {
                        "_uid": missing[:30], "uid": True, "username": True,
                        "avatar": True, "usertitle": True, "reputation": True,
                        "usergroup": True, "displaygroup": True, "additionalgroups": True,
                    }
                })
                if data:
                    rows = data.get("users", [])
                    if isinstance(rows, dict): rows = [rows]
                    new_map = {}
                    for r in rows:
                        uid_str = str(r.get("uid", ""))
                        name    = r.get("username", "")
                        if uid_str and name:
                            result[uid_str]  = name
                            av = r.get("avatar", "") or ""
                            if av and not av.startswith("http"):
                                av = "https://hackforums.net/" + av.lstrip("./")
                            new_map[uid_str] = {
                                "username":        name,
                                "avatar":          av,
                                "usertitle":       r.get("usertitle", "") or "",
                                "reputation":      int(r.get("reputation") or 0),
                                "displaygroup":    str(r.get("displaygroup") or r.get("usergroup") or ""),
                                "additionalgroups":str(r.get("additionalgroups") or ""),
                            }
                    if new_map:
                        await asyncio.to_thread(db.upsert_uid_usernames, new_map)
        except Exception as e:
            log.warning("Wire resolve_usernames HF API error: %s", e)

    return result


@router.get("/me")
async def wire_me(request: Request):
    uid = _uid_opt(request)
    if not uid:
        return {"role": "none", "is_curator": False, "is_lead": False, "is_admin": False}
    role = await asyncio.to_thread(get_my_role, uid)
    return {
        "role":          role,
        "is_curator":    role in ("admin", "lead", "curator"),
        "is_lead":       role in ("admin", "lead"),
        "is_admin":      role == "admin",
    }


@router.get("/threads")
async def list_threads(request: Request, tag: str = "all", page: int = 1, search: str = "", sort: str = "recent"):
    tag = tag.lower()
    if tag != "all" and tag not in VALID_TAGS:
        tag = "all"
    if sort not in ("recent", "active"):
        sort = "recent"
    result = await asyncio.to_thread(get_threads, tag, max(1, page), PERPAGE_THREADS, search.strip(), sort)
    for t in result["threads"]:
        _enrich(t)
    return result


@router.patch("/thread/{tid}/hf-news")
async def set_thread_hf_news(request: Request, tid: str, body: dict):
    """Lead/admin only — set or clear is_hf_news flag on an existing thread."""
    uid = _uid(request)
    if not await asyncio.to_thread(is_lead_curator, uid):
        raise HTTPException(403, "Lead curators only")
    row = await asyncio.to_thread(get_thread, tid)
    if not row:
        raise HTTPException(404, "Thread not found")
    flag = int(bool(body.get("is_hf_news", False)))
    await asyncio.to_thread(set_hf_news_flag, tid, flag)
    return {"ok": True, "tid": tid, "is_hf_news": flag}


@router.get("/hf-news")
async def get_hf_news(request: Request):
    """Return the latest HF News thread (pinned separately from main feed)."""
    row = await asyncio.to_thread(get_latest_hf_news)
    if not row:
        return {"thread": None}
    return {"thread": _enrich(dict(row))}


@router.get("/thread/{tid}")
async def get_single_thread(request: Request, tid: str):
    row = await asyncio.to_thread(get_thread, tid)
    if not row:
        raise HTTPException(404, "Thread not found")
    return _enrich(dict(row))


@router.post("/thread/{tid}/refresh")
async def refresh_thread(request: Request, tid: str):
    """Re-fetch thread data from HF API. Rate limited to 3 per thread per hour."""
    uid = _uid(request)

    row = await asyncio.to_thread(get_thread, tid)
    if not row:
        raise HTTPException(404, "Thread not found in The Wire")

    count = await asyncio.to_thread(get_thread_refresh_count, tid)
    if count >= REFRESH_MAX:
        raise HTTPException(429, f"Refresh limit reached ({REFRESH_MAX}/hr). Try again later.")

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        raise HTTPException(401, "No HF token")

    try:
        from HFClient import HFClient
        hf = HFClient(token)
        # Bundle threads + posts in one call — was 2 separate calls, now 1.
        data = await hf.read({
            "threads": {
                "_tid":       [int(tid)],
                "tid":        True, "fid": True, "subject": True,
                "numreplies": True, "lastpost": True, "closed": True,
                "firstpost":  True,
            },
            "posts": {
                "_tid":     [int(tid)],
                "_page":    1,
                "_perpage": 2,   # OP + maybe one reply; we match by PID
                "pid":      True,
                "message":  True,
            },
        })
    except Exception as e:
        raise HTTPException(503, f"HF API unavailable: {e}")

    if not data:
        raise HTTPException(503, "HF API returned no data")

    t = data.get("threads")
    if not t:
        raise HTTPException(404, "Thread not found on HackForums")
    if isinstance(t, list):
        t = t[0]

    fp = t.get("firstpost") or {}
    if isinstance(fp, list): fp = fp[0] if fp else {}
    if isinstance(fp, str):
        firstpost_pid = fp
    else:
        firstpost_pid = str(fp.get("pid") or "")

    numreplies = int(t.get("numreplies") or 0)
    lastpost   = int(t.get("lastpost")   or 0)
    closed     = int(t.get("closed")     or 0)

    # Extract firstpost body from the bundled posts response — no second API call needed
    firstpost_body = ""
    posts_raw = data.get("posts", [])
    if isinstance(posts_raw, dict): posts_raw = [posts_raw]
    for _p in (posts_raw or []):
        if str(_p.get("pid", "")) == str(firstpost_pid):
            firstpost_body = _p.get("message", "")
            break
    if not firstpost_body and posts_raw:
        firstpost_body = posts_raw[0].get("message", "")  # fallback: first post returned
    if not firstpost_body:
        log.warning("Wire refresh: no firstpost content in bundled response tid=%s pid=%s", tid, firstpost_pid)

    await asyncio.to_thread(update_thread_stats, tid, numreplies, lastpost, closed)

    if firstpost_body:
        await asyncio.to_thread(update_firstpost_content, tid, firstpost_body)

    await asyncio.to_thread(log_thread_refresh, tid, uid)

    updated = await asyncio.to_thread(get_thread, tid)
    refreshes_left = REFRESH_MAX - (count + 1)
    return {
        "ok": True,
        "thread": _enrich(dict(updated)) if updated else None,
        "refreshes_left": max(0, refreshes_left),
    }

@router.get("/my-submissions")
async def my_submissions(request: Request):
    uid = _uid(request)
    if not await asyncio.to_thread(is_curator, uid):
        raise HTTPException(403, "Curators only")
    rows = await asyncio.to_thread(get_my_submissions, uid)
    return {"submissions": [_enrich(dict(r)) for r in rows]}


def _enrich_replies(replies: list[dict]) -> list[dict]:
    """Fill in missing username/avatar from uid_usernames cache. Zero HF API calls."""
    rows = [dict(r) for r in replies]
    missing_uids = [r["uid"] for r in rows if (not r.get("username") or not r.get("avatar")) and r.get("uid")]
    if missing_uids:
        try:
            cache = db.get_uid_usernames(missing_uids)
            for r in rows:
                uid = str(r.get("uid", ""))
                info = cache.get(uid, {})
                if isinstance(info, dict):
                    if not r.get("username") and info.get("username"):
                        r["username"] = info["username"]
                    if not r.get("avatar") and info.get("avatar"):
                        r["avatar"] = info["avatar"]
                elif isinstance(info, str) and not r.get("username"):
                    r["username"] = info
        except Exception:
            pass  # cache miss is fine — just show without username
    return rows


@router.get("/thread/{tid}/replies")
async def get_replies(request: Request, tid: str, page: int = 1, refresh: bool = False):
    uid = _uid_opt(request)
    page = max(1, page)

    cached  = await asyncio.to_thread(get_cached_replies, tid, page)
    cache_ts = await asyncio.to_thread(get_reply_cache_ts, tid)
    stale   = (cache_ts is None) or ((int(time.time()) - cache_ts) > REPLY_CACHE_TTL)

    if cached and not (refresh and stale):
        return {"replies": _enrich_replies(cached), "cached": True, "cached_at": cache_ts, "page": page}

    # Unauthenticated — can only serve from cache; no live HF API calls
    if not uid:
        if cached:
            return {"replies": _enrich_replies(cached), "cached": True, "cached_at": cache_ts, "page": page}
        return {"replies": [], "cached": False, "cached_at": None, "page": page}

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        if cached:
            return {"replies": _enrich_replies(cached), "cached": True, "cached_at": cache_ts, "page": page}
        raise HTTPException(401, "No HF token — cannot fetch replies")

    try:
        from HFClient import HFClient
        hf = HFClient(token)
        data = await hf.read({
            "posts": {
                "_tid":     [int(tid)],
                "_page":    page,
                "_perpage": PERPAGE_REPLIES,
                "pid":      True, "uid": True, "dateline": True,
                "message":  True,
                "author":   {"uid": True, "username": True, "avatar": True},
            }
        })
    except Exception as e:
        log.warning("Wire: replies fetch failed tid=%s: %s", tid, e)
        if cached:
            return {"replies": _enrich_replies(cached), "cached": True, "cached_at": cache_ts, "page": page}
        raise HTTPException(503, "HF API unavailable")

    if not data:
        if cached:
            return {"replies": _enrich_replies(cached), "cached": True, "cached_at": cache_ts, "page": page}
        raise HTTPException(503, "HF API returned no data")

    rows = data.get("posts", [])
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return {"replies": [], "cached": False, "cached_at": None, "page": page}

    # Extract author data BEFORE upsert — upsert reads top-level keys
    out = []
    for r in rows:
        author = r.get("author") or {}
        if isinstance(author, list): author = author[0] if author else {}
        out.append({
            "pid":      r.get("pid", ""),
            "uid":      str(r.get("uid", "") or author.get("uid", "")),
            "username": author.get("username", "") or r.get("username", ""),
            "avatar":   _normalize_avatar(author.get("avatar", "") or r.get("avatar", "")),
            "dateline": int(r.get("dateline") or 0),
            "message":  r.get("message", ""),
        })

    await asyncio.to_thread(upsert_replies, out, tid, page)

    # Cache user profiles — never throw away free API data
    user_profiles = {}
    for r in out:
        if r.get("uid") and r.get("username"):
            user_profiles[str(r["uid"])] = {
                "username": r["username"],
                "avatar":   r.get("avatar", ""),
            }
    if user_profiles:
        await asyncio.to_thread(db.upsert_uid_usernames, user_profiles)

    return {"replies": out, "cached": False, "cached_at": int(time.time()), "page": page}


@router.post("/thread/{tid}/reply")
async def post_reply(request: Request, tid: str, body: ReplyBody):
    uid = _uid(request)
    if not body.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        raise HTTPException(401, "No HF token")
    try:
        from HFClient import HFClient
        data = await HFClient(token).write({"posts": {"_tid": int(tid), "_message": body.message}})
    except Exception as e:
        raise HTTPException(503, f"HF API error: {e}")
    if not data:
        raise HTTPException(503, "Reply failed")
    return {"ok": True, "pid": data.get("posts", {}).get("pid")}


@router.post("/thread/{tid}/replies/refresh")
async def refresh_replies(request: Request, tid: str):
    await asyncio.to_thread(clear_reply_cache, tid)
    return await get_replies(request, tid, page=1, refresh=True)


@router.post("/threads")
async def submit_thread(request: Request, body: SubmitBody):
    uid = _uid(request)
    if not await asyncio.to_thread(is_curator, uid):
        raise HTTPException(403, "Curators only")

    tag = body.tag.lower()
    if tag not in VALID_TAGS:
        raise HTTPException(400, f"Invalid tag. Must be one of: {', '.join(sorted(VALID_TAGS))}")

    tid = _parse_tid(body.url)
    if not tid:
        raise HTTPException(400, "Could not parse thread ID from input")

    existing = await asyncio.to_thread(get_thread, tid)
    if existing:
        raise HTTPException(409, f"Thread {tid} is already in The Wire")

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        raise HTTPException(401, "No HF token — cannot fetch thread data")

    # ── Call 1 (2 endpoints): thread metadata + first N posts ──────────────────
    # Fetching posts._tid page 1 here covers both the firstpost body AND any
    # secondpost needed for multi-post submissions. Eliminates call 3 entirely
    # and bundles what was previously call 1 alone (threads only).
    try:
        from HFClient import HFClient
        hf = HFClient(token)
        t_data = await hf.read({
            "threads": {
                "_tid":      [int(tid)],
                "tid":       True, "uid": True, "fid": True, "subject": True,
                "dateline":  True, "firstpost": True, "numreplies": True,
                "lastpost":  True, "closed": True,
            },
            "posts": {
                "_tid":     [int(tid)],
                "_page":    1,
                "_perpage": 5,   # enough for multi-post (up to 5 posts in body)
                "pid":      True,
                "message":  True,
            },
        })
    except Exception as e:
        raise HTTPException(503, f"HF API unavailable: {e}")

    if not t_data:
        raise HTTPException(503, "HF API returned no data for thread")

    t = t_data.get("threads")
    if not t:
        raise HTTPException(404, "Thread not found on HackForums")
    if isinstance(t, list):
        t = t[0]

    # firstpost can be a dict, list, or bare pid string
    fp = t.get("firstpost") or {}
    if isinstance(fp, list):
        fp = fp[0] if fp else {}
    if isinstance(fp, str):
        firstpost_pid  = fp
    else:
        firstpost_pid  = str(fp.get("pid") or "")

    author_uid  = str(t.get("uid") or "")
    fid         = str(t.get("fid") or "")
    subject     = str(t.get("subject") or "")
    dateline    = int(t.get("dateline") or 0)
    numreplies  = int(t.get("numreplies") or 0)
    lastpost    = int(t.get("lastpost") or 0)
    closed      = int(t.get("closed") or 0)

    # Extract firstpost + secondpost from the bundled posts response
    posts_bundled = t_data.get("posts", [])
    if isinstance(posts_bundled, dict): posts_bundled = [posts_bundled]
    posts_bundled = list(posts_bundled or [])

    firstpost_body = ""
    for _bp in posts_bundled:
        if str(_bp.get("pid", "")) == str(firstpost_pid):
            firstpost_body = _bp.get("message", "")
            break
    if not firstpost_body and posts_bundled:
        firstpost_body = posts_bundled[0].get("message", "")

    # Build secondpost + extra_posts from the same bundled list (no extra API call)
    secondpost_content = ""
    secondpost_pid_val = ""
    extra_posts_val    = ""
    if body.post_count > 1:
        import json as _json
        extra_list = []
        for _bp in posts_bundled:
            if str(_bp.get("pid", "")) == str(firstpost_pid):
                continue
            if not secondpost_pid_val:
                secondpost_pid_val = str(_bp.get("pid", ""))
                secondpost_content = _bp.get("message", "")
            else:
                extra_list.append({"pid": str(_bp.get("pid", "")), "message": _bp.get("message", "")})
            if 1 + len(extra_list) >= body.post_count - 1:
                break
        extra_posts_val = _json.dumps(extra_list) if extra_list else ""

    author_name = author_avatar = author_usertitle = ""
    author_reputation = "0"
    author_groups = ""

    # ── Call 2 (1 endpoint): author profile ─────────────────────────────────────
    # Was previously bundled with posts._pid in call 2. Now it stands alone since
    # posts are already handled above. Net: 3 calls → 2 calls for basic submit.
    if author_uid:
        try:
            extra = await hf.read({
                "users": {
                    "_uid": [int(author_uid)],
                    "uid": True, "username": True, "avatar": True,
                    "usertitle": True, "reputation": True,
                    "usergroup": True, "additionalgroups": True,
                }
            })
            if extra:
                u = extra.get("users") or {}
                if isinstance(u, list): u = u[0] if u else {}
                author_name      = u.get("username", "")
                author_avatar    = _normalize_avatar(u.get("avatar", ""))
                author_usertitle = u.get("usertitle", "")
                author_reputation= str(u.get("reputation") or "0")
                ug  = str(u.get("usergroup") or "")
                ags = str(u.get("additionalgroups") or "")
                author_groups = ",".join(filter(None, [ug] + [g.strip() for g in ags.split(",") if g.strip()]))
        except Exception as e:
            log.warning("Wire submit: author fetch failed tid=%s: %s", tid, e)

    curator_name = ""
    try:
        urow = await asyncio.to_thread(db.get_user, uid)
        if urow:
            curator_name = urow.get("username", "")
    except Exception:
        pass

    await asyncio.to_thread(
        add_thread,
        tid, fid, subject,
        author_uid, author_name, author_avatar,
        author_usertitle, author_reputation, author_groups,
        firstpost_pid, firstpost_body,
        dateline, numreplies, lastpost, closed,
        tag, uid, curator_name, body.note.strip(),
        int(body.post_count > 1), secondpost_content, secondpost_pid_val,
        int(body.is_hf_news), extra_posts_val if body.post_count > 1 else "", body.post_count,
    )
    return {"ok": True, "tid": tid, "subject": subject, "tag": tag}


@router.delete("/threads/{tid}")
async def delete_thread(request: Request, tid: str):
    uid = _uid(request)
    if not await asyncio.to_thread(is_curator, uid):
        raise HTTPException(403, "Curators only")
    row = await asyncio.to_thread(get_thread, tid)
    if not row:
        raise HTTPException(404, "Thread not found")
    if not await asyncio.to_thread(is_lead_curator, uid):
        if str(row.get("curator_uid", "")) != uid:
            raise HTTPException(403, "You can only remove threads you submitted")
    await asyncio.to_thread(remove_thread, tid)
    return {"ok": True}


# ── Curator management ─────────────────────────────────────────────────────────

@router.get("/curators")
async def list_curators(request: Request):
    uid = _uid(request)
    if not await asyncio.to_thread(is_lead_curator, uid):
        raise HTTPException(403, "Lead curators and above only")
    rows = await asyncio.to_thread(get_curators)
    return {"curators": [dict(r) for r in rows]}


@router.post("/curators")
async def add_curator_route(request: Request, body: AddCuratorBody):
    uid = _uid(request)
    lead = await asyncio.to_thread(is_lead_curator, uid)
    admin = await asyncio.to_thread(is_admin, uid)

    if not lead:
        raise HTTPException(403, "Lead curators and above only")

    target_role = body.role.lower()
    if target_role not in ("curator", "lead"):
        raise HTTPException(400, "Role must be 'curator' or 'lead'")
    if target_role == "lead" and not admin:
        raise HTTPException(403, "Only admin can add lead curators")

    target_uid = body.uid.strip()
    if not target_uid.isdigit():
        raise HTTPException(400, "UID must be numeric")

    token = await asyncio.to_thread(db.get_token, uid)
    username = ""
    if token:
        try:
            from HFClient import HFClient
            data = await HFClient(token).read({"users": {"_uid": [int(target_uid)], "uid": True,
                "username": True, "avatar": True, "usertitle": True, "reputation": True,
                "usergroup": True, "displaygroup": True, "additionalgroups": True}})
            u = data.get("users") if data else None
            if isinstance(u, list): u = u[0] if u else None
            if u:
                username = u.get("username", "")
                av = str(u.get("avatar","") or "")
                if av and not av.startswith("http"):
                    av = "https://hackforums.net/" + av.lstrip("./")
                await asyncio.to_thread(db.upsert_uid_usernames, {str(target_uid): {
                    "username":        username,
                    "avatar":          av,
                    "usertitle":       u.get("usertitle","") or "",
                    "reputation":      int(u.get("reputation") or 0),
                    "displaygroup":    str(u.get("displaygroup") or u.get("usergroup") or ""),
                    "additionalgroups":str(u.get("additionalgroups") or ""),
                }})
        except Exception:
            pass

    await asyncio.to_thread(add_curator, target_uid, username, uid, target_role)
    return {"ok": True, "uid": target_uid, "username": username, "role": target_role}


@router.patch("/curators/{target_uid}")
async def update_curator_role(request: Request, target_uid: str, body: SetRoleBody):
    uid = _uid(request)
    if not await asyncio.to_thread(is_admin, uid):
        raise HTTPException(403, "Admin only")
    new_role = body.role.lower()
    if new_role not in ("curator", "lead"):
        raise HTTPException(400, "Role must be 'curator' or 'lead'")
    await asyncio.to_thread(set_curator_role, target_uid, new_role)
    return {"ok": True}


@router.delete("/curators/{target_uid}")
async def remove_curator_route(request: Request, target_uid: str):
    uid = _uid(request)
    lead  = await asyncio.to_thread(is_lead_curator, uid)
    admin = await asyncio.to_thread(is_admin, uid)
    if not lead:
        raise HTTPException(403, "Lead curators and above only")
    if target_uid == uid:
        raise HTTPException(400, "Cannot remove yourself")

    # Leads can only remove regular curators; admin can remove anyone
    rows = await asyncio.to_thread(get_curators)
    target = next((r for r in rows if str(r["uid"]) == target_uid), None)
    if target and target.get("role") == "lead" and not admin:
        raise HTTPException(403, "Only admin can remove lead curators")

    await asyncio.to_thread(remove_curator, target_uid)
    return {"ok": True}


# ── Background sync ────────────────────────────────────────────────────────────

async def sync_wire_threads(token: str):
    tids = await asyncio.to_thread(get_all_tids)
    if not tids:
        return
    try:
        from HFClient import HFClient
        hf = HFClient(token)
    except Exception:
        return
    for i in range(0, len(tids), 4):
        batch = [int(t) for t in tids[i:i+4]]
        try:
            data = await asyncio.wait_for(
                hf.read({"threads": {
                    "_tid": batch, "tid": True,
                    "numreplies": True, "lastpost": True, "closed": True,
                }}),
                timeout=12,
            )
            if not data:
                continue
            rows = data.get("threads", [])
            if isinstance(rows, dict): rows = [rows]
            for row in rows:
                await asyncio.to_thread(
                    update_thread_stats,
                    str(row.get("tid", "")),
                    int(row.get("numreplies") or 0),
                    int(row.get("lastpost") or 0),
                    int(row.get("closed") or 0),
                )
        except asyncio.TimeoutError:
            log.warning("Wire sync: batch timed out tids=%s — skipping", batch)
        except Exception as e:
            log.warning("Wire sync batch failed: %s", e)
        await asyncio.sleep(1)
