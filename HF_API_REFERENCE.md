# HF API v2 — Agent Skills Reference

> Comprehensive reference for building integrations with the HackForums API v2.
> All patterns, gotchas, and field behaviours confirmed against live data.
> Docs: https://apidocs.hackforums.net/

---

## Core Concepts

- **Base URL:** `https://hackforums.net/api/v2`
- **All calls are POST.** Two routes: `/read` and `/write`
- Auth header required on every call: `Authorization: Bearer ACCESS_TOKEN`
- Request body key: `"asks"` — a nested JSON object
- `_underscore` fields = **inputs** (what to look up). Plain fields = **outputs** (set to `true` to return).
- **Max 4 endpoints per single `read()` call.** 5+ silently returns 503 with no warning.
- **Rate limit: ~240 calls/hour per token** (empirical). Tracked via `x-rate-limit-remaining` response header.
- `401` = missing or invalid access token

---

## OAuth2 Flow

### Step 1 — Get Authorization Code

Redirect user to:
```
https://hackforums.net/api/v2/authorize?response_type=code&client_id=CLIENT_ID&state=OPTIONAL_STATE
```

On approval, HF redirects to your URI:
```
https://YOUR_REDIRECT_URI/?code=CODE&state=STATE
```

### Step 2 — Exchange Code for Token

> Code expires in **10 minutes**.

```
POST https://hackforums.net/api/v2/authorize
grant_type=authorization_code, client_id, client_secret, code
```

Returns: `access_token`, `uid`

### Scopes

| Scope | Unlocks |
|---|---|
| Basic Info | Public profile of authorized user (`uid`, `username`, `usergroup`, `bytes`, `vault`, etc.) |
| Advanced Info | Private fields: `unreadpms`, `invisible`, `totalpms`, `lastactive`, `warningpoints` |
| Posts | Forums, threads, posts — includes optional write |
| Users | Public info of other members |
| Bytes | Byte logs + optional write (transfers, deposits, withdrawals, bumps) |
| Contracts | Contracts, disputes, b-ratings |

> Increasing permissions requires users to re-authorize. Never put `client_secret` or access tokens in front-end or public code.

---

## Critical Gotchas

**Every value in every response is a string.** Cast everything explicitly.
```python
uid  = int(row.get("uid") or 0)
myps = float(row.get("myps") or 0)
```

**Single result returns a dict. Multiple results return a list of dicts.** Always normalize:
```python
rows = data.get("contracts")
if isinstance(rows, dict):
    rows = [rows]
```

**`me.bytes` vs `users.myps`** — same thing (byte balance), different field name by endpoint.

**`me` advanced fields** (`unreadpms`, `warningpoints`, `invisible`, `totalpms`, `lastactive`) require the "Advanced Info" OAuth scope. If the token lacks that scope these fields are **absent** from the response — they will not come back as zero or null.

**`bytes.amount` must be cast as `int(float(x))`**, never `int(x)` directly — values like `"430.43"` will crash on direct int cast.

**`_perpage` max is 30** for all endpoints. Values above 30 return empty results.

**Cannot use the same endpoint key twice in one call.** e.g. can't have two `"bytes"` keys in one call.

**`_from`, `_to`, and `_uid` filters require integer UIDs**, not strings. Passing a string UID causes `_from` to silently return empty results.
```python
# Wrong
{"bytes": {"_to": [uid_str]}}
# Right
{"bytes": {"_to": [int(uid)]}}
```

**`from` and `to` embedded fields are never returned** even when explicitly requested — counterparty display is impossible via the bytes endpoint. Use separate `_from`/`_to` filter calls to determine direction.

**Avatar URLs are relative paths** — must be prefixed with the site URL:
```python
# API returns: "./uploads/avatars/avatar_123.jpg?dateline=..."
avatar = "https://hackforums.net/" + raw.lstrip("./")
```

**`additionalgroups`** returns a comma-separated string — split on `,` to get individual group IDs.

**`contracts.idispute` / `odispute`** are embedded in the contract response — no extra API call needed.

**HF occasionally 503s valid queries** during load spikes. Handle `None`/empty gracefully and retry next cycle.

**`posts._uid`** returns only replies to other threads, NOT the user's own thread OPs — must combine with `firstpost` pids from threads response and dedupe to get all posts.

**`threads._uid`** does not reliably return `numreplies` in all contexts — verify before relying on it.

**`_uid` page 1 sorted newest first** for both posts and threads endpoints.

---

## Read Endpoints

### /me — Authorized user's own data
Scope: Basic Info (Advanced Info for private fields)

| Field | Scope | Notes |
|---|---|---|
| `uid`, `username`, `usergroup`, `displaygroup`, `additionalgroups` | Basic | |
| `postnum`, `threadnum`, `awards` | Basic | |
| `bytes` | Basic | Token owner's byte balance — `users` endpoint calls this `myps` |
| `vault` | Basic | API Client Vault balance |
| `avatar`, `avatardimensions`, `avatartype` | Basic | Avatar is a relative path — prefix `https://hackforums.net/` |
| `lastvisit`, `usertitle`, `website`, `timeonline`, `reputation`, `referrals` | Basic | |
| `lastactive`, `unreadpms`, `invisible`, `totalpms`, `warningpoints` | Advanced | Absent (not zero) if scope missing |

- `avatardimensions` returns `"120|120"` (pipe-separated width|height string)
- `additionalgroups` returns a comma-separated string e.g. `"67,68,78"`

---

### /users — Any user(s) by UID
Scope: Users Permissions  
Input: `_uid` [array of ints]

Fields: `uid`, `username`, `usergroup`, `displaygroup`, `additionalgroups`, `postnum`, `threadnum`, `awards`, `myps`, `avatar`, `avatardimensions`, `avatartype`, `usertitle`, `website`, `timeonline`, `reputation`, `referrals`

> `myps` = byte balance. Same data as `me.bytes` but different field name.  
> Advanced scope fields (`unreadpms` etc.) are **not available** via `/users` — only via `/me`.

---

### /forums — Forum metadata
Scope: Posts Permissions  
Input: `_fid` [array]  
Fields: `fid`, `name`, `description`, `type`

| type code | Description |
|---|---|
| `f` | Forum — actual subforum, contains threads |
| `c` | Category — parent container, no threads directly |

> Only `type="f"` forums will ever have threads. Never use category FIDs as `_fid` inputs for thread queries.

**Category FID set** (never valid for `_fid` thread queries):
`1, 7, 45, 88, 105, 120, 141, 151, 156, 241, 259, 444, 445, 446, 447, 448, 449, 450, 451, 452, 453, 460`

---

### /threads — Thread info
Scope: Posts Permissions

| Input | Description |
|---|---|
| `_tid` [array] | Specific threads by ID |
| `_fid` [array] | All threads in a forum |
| `_uid` [array] | Threads by user — supports `_page`, `_perpage` |

Fields: `tid`, `uid`, `fid`, `subject`, `closed`, `numreplies`, `views`, `dateline`, `firstpost`, `lastpost`, `lastposter`, `lastposteruid`, `prefix`, `icon`, `poll`, `username`, `sticky`, `bestpid`

> `_uid` page 1 sorted newest first = user's most recently active threads.

---

### /posts — Post info
Scope: Posts Permissions

| Input | Description |
|---|---|
| `_pid` [array] | Specific posts by ID |
| `_tid` [array] | All posts in a thread — supports `_page`, `_perpage` |
| `_uid` [array] | Posts by user — supports `_page`, `_perpage` |

Fields: `pid`, `tid`, `uid`, `fid`, `dateline`, `message`, `subject`, `edituid`, `edittime`, `editreason`

> Posts support an embedded `author` object to avoid a separate `/users` call:
> ```python
> "posts": {"_tid": [TID], "message": True, "author": {"uid": True, "username": True}}
> ```
> `_uid` returns oldest-first. Page 1 = user's oldest posts. Fetch the last page for recent activity.

---

### /bytes — Byte transaction history
Scope: Bytes Permissions

| Input | Description |
|---|---|
| `_id` [array] | Specific transactions |
| `_uid` [array] | All transactions for user (sent + received) |
| `_from` [array] | Transactions SENT by user — requires int UID |
| `_to` [array] | Transactions RECEIVED by user — requires int UID |

All support `_page`, `_perpage` (max 30).

Fields: `id`, `amount`, `dateline`, `type`, `reason`

> `amount` is a float string (e.g. `"430.43"`) — always cast via `int(float(x))`.  
> Direction is determined by using two separate calls: `_from` for sent, `_to` for received.  
> `from` and `to` embedded fields are never returned even when requested.

#### Bytes Transaction Type Codes (confirmed live, 290+ transactions)

| Code | Direction | Description |
|---|---|---|
| `att` | OUT | Manual bytes send to another user |
| `bla` | IN | Blackjack winner |
| `bon` | IN | Bonus (event award, quick love bonus) |
| `bum` | OUT | Thread bump fee |
| `cfl` | OUT | Coin flips loser |
| `cfw` | IN | Coin flips winner |
| `cgp` | OUT | Crypto game coin purchase |
| `cgs` | IN | Crypto game coin sell |
| `cvr` | IN | Convo rain |
| `don` | IN/OUT | Peer-to-peer send/receive — contract payments come in as `don` with reason `"Contract"` |
| `gce` | OUT | Bytes to game cash exchange |
| `ltb` | OUT | Lottery ticket purchase |
| `qlc` | IN | Quick love convo |
| `qlp` | IN/OUT | Quick love post |
| `sbs` | IN | Sportsbook winner |
| `sbw` | OUT | Sportsbook wager |
| `sbc` | IN | Sportsbook cancel/refund |
| `scp` | OUT | Scratch card purchase |
| `slo` | IN | Slots winner |
| `ugb` | IN | Upgrade bonus |

> `don` is the only code that appears on both sides and represents real peer-to-peer money movement.  
> To isolate contract payments: filter `type == "don"` and `reason == "Contract"`.

---

### /contracts — Contract info
Scope: Contracts Permissions

| Input | Description |
|---|---|
| `_cid` [array] | Specific contracts by ID |
| `_uid` [array] | All contracts you're party to — supports `_page`, `_perpage` |

Fields: `cid`, `dateline`, `otherdateline`, `public`, `timeout_days`, `timeout`, `status`, `type`, `istatus`, `ostatus`, `muid`, `inituid`, `otheruid`, `iprice`, `icurrency`, `iproduct`, `oprice`, `ocurrency`, `oproduct`, `terms`, `tid`, `idispute`, `odispute`

> `idispute`/`odispute` are embedded — dispute info comes free with the contracts call.  
> All contract values are numeric strings.

#### Contract Status Map (confirmed live)

| Value | Label |
|---|---|
| `"1"` | Awaiting Approval |
| `"2"` | Cancelled |
| `"3"` | Unknown (likely middleman escrow) |
| `"4"` | Unknown (likely middleman escrow) |
| `"5"` | Active Deal |
| `"6"` | Complete |
| `"7"` | Disputed |
| `"8"` | Expired |

#### Contract Type Map (confirmed live)

| Value | Label |
|---|---|
| `"1"` | Selling |
| `"2"` | Purchasing |
| `"3"` | Exchanging |
| `"4"` | Trading |
| `"5"` | Vouch Copy |

> `type` reflects the **initiator's** position at creation time.  
> `istatus`/`ostatus`: `"0"` = not approved, `"1"` = approved — per-party flags, separate from overall `status`.

#### Contract Value Display Logic

Most contracts use `currency="other"` with the actual payment in `iproduct`/`oproduct`. Use this fallback chain:

```python
def contract_value(c: dict) -> str:
    iprice = c.get("iprice", "0")
    icur   = c.get("icurrency", "other")
    oprice = c.get("oprice", "0")
    ocur   = c.get("ocurrency", "other")
    iproduct = c.get("iproduct", "")
    oproduct = c.get("oproduct", "")
    if iprice != "0" and icur.lower() != "other":
        return f"{iprice} {icur}"
    if oprice != "0" and ocur.lower() != "other":
        return f"{oprice} {ocur}"
    if iproduct not in ("", "other", "n/a"):
        return iproduct
    if oproduct not in ("", "other", "n/a"):
        return oproduct
    return ""
```

#### HF Contract URL

```
https://hackforums.net/contracts.php?action=view&cid=CID
```
Note: `contracts.php` with an **s** — not `contract.php`.

---

### /bratings — Buyer/seller ratings
Scope: Contracts Permissions

| Input | Description |
|---|---|
| `_crid` [array] | Specific ratings by ID |
| `_cid` [array] | Ratings for a contract |
| `_uid` [array] | All ratings involving user |
| `_from` [array] | Ratings left by user |
| `_to` [array] | Ratings received by user |

Fields: `crid`, `contractid`, `fromid`, `toid`, `dateline`, `amount`, `message`, `contract` (embedded), `from` (embedded User), `to` (embedded User)

---

### /disputes — Contract disputes
Scope: Contracts Permissions

| Input | Description |
|---|---|
| `_cdid` [array] | Specific disputes by ID |
| `_cid` [array] | Dispute for a contract |
| `_uid` [array] | All disputes involving user |
| `_claimantuid` [array] | Disputes where user is claimant |
| `_defendantuid` [array] | Disputes where user is defendant |

Fields: `cdid`, `contractid`, `claimantuid`, `defendantuid`, `dateline`, `status`, `dispute_tid`, `claimantnotes`, `defendantnotes`, `contract` (embedded), `claimant`/`defendant`/`dispute_thread` (embedded)

---

### /sigmarket — Signature marketplace

**market** — Input: `_type`=`"market"`, `_uid` [array], `_page`, `_perpage`  
Fields: `uid`, `user` (embedded), `price`, `duration`, `active`, `sig`, `dateadded`, `ppd`

**order** — Input: `_type`=`"order"`, `_smid`/`_uid`/`_seller`/`_buyer` [arrays], `_page`, `_perpage`  
Fields: `smid`, `buyer`/`seller` (embedded User), `startdate`, `enddate`, `price`, `duration`, `active`

---

## Write Endpoints

All writes: `POST https://hackforums.net/api/v2/write` + `Authorization: Bearer TOKEN`

### posts — Reply to a thread
Scope: Posts Write
```python
{"posts": {"_tid": TID, "_message": "BBCode content"}}
```
Returns: `pid`, `tid`, `uid`, `message`

---

### threads — Create a thread
Scope: Posts Write
```python
{"threads": {"_fid": FID, "_subject": "Title", "_message": "Body"}}
```
Returns: `tid`, `uid`, `subject`, `dateline`, `firstpost` {`pid`, `message`}

> **No `_prefix` parameter exists.** Prefixes cannot be set via the API — must be set manually on HF after posting.

---

### bytes — Byte operations
Scope: Bytes Write
```python
# Send bytes to a user
{"bytes": {"_uid": "UID", "_amount": "100", "_reason": "Payment"}}

# Deposit to vault (min 100)
{"bytes": {"_deposit": 500}}

# Withdraw from vault (min 100)
{"bytes": {"_withdraw": 500}}

# Bump a thread (costs bytes, uses Stanley bot)
{"bytes": {"_bump": TID}}
```

---

### contracts — Contract actions
Scope: Contracts Write

| `_action` | Notes |
|---|---|
| `new` | Requires `_uid`, `_terms`, `_position`. Optional: `_yourproduct`, `_yourcurrency`, `_youramount`, `_theirproduct`, `_theircurrency`, `_theiramount`, `_tid`, `_muid`, `_timeout`, `_public` |
| `undo` | Undo a contract you just created |
| `deny` | Deny as counterparty |
| `approve` | Approve as counterparty |
| `cancel` | Request cancellation — both parties must submit |
| `complete` | Mark your side complete |
| `middleman_deny` / `middleman_approve` | Middleman actions |

> `_position` values: `selling`, `buying`, `exchanging`, `trading`, `vouchcopy`

---

### sigmarket — Signature market actions
```python
# List your sig for sale
{"sigmarket": {"_type": "setsale", "_price": BYTES, "_duration": DAYS}}

# Remove from sale
{"sigmarket": {"_type": "removesale"}}

# Update sig on active orders ('all' updates all)
{"sigmarket": {"_type": "changesig", "_smid": SMID_OR_"all", "_sig": "new BBCode"}}

# Buy someone's sig slot
{"sigmarket": {"_type": "buy", "_uid": UID, "_price": MAX_PRICE}}
```

---

## Efficient Batching

### Rules (confirmed via live testing)
- Max **4 endpoints per call** — 5+ causes a silent 503
- Each endpoint key must be **unique** in the dict
- Each endpoint gets its own `_perpage` independently
- `me` always returns exactly 1 result regardless of paging params

### Full Dashboard in 2 Calls

```python
# Call 1: me + received bytes + threads + contracts  [4/4 slots]
data1 = await hf.read({
    "me":        {"uid": True, "bytes": True, "vault": True, "unreadpms": True},
    "bytes":     {"_to": [uid_int], "_page": 1, "_perpage": 30,
                  "id": True, "amount": True, "dateline": True, "reason": True, "type": True},
    "contracts": {"_uid": [uid_int], "_page": 1, "_perpage": 30,
                  "cid": True, "status": True, "type": True,
                  "iproduct": True, "oproduct": True, "iprice": True, "icurrency": True,
                  "oprice": True, "ocurrency": True, "dateline": True},
    "threads":   {"_uid": [uid_int], "_page": 1, "_perpage": 30,
                  "tid": True, "subject": True, "lastpost": True,
                  "lastposteruid": True, "numreplies": True},
})

# Call 2: sent bytes  [1/4 slots — can't combine two "bytes" keys]
data2 = await hf.read({
    "bytes": {"_from": [uid_int], "_page": 1, "_perpage": 30,
              "id": True, "amount": True, "dateline": True, "reason": True, "type": True},
})
```

---

## Common Patterns

### Detect a user's most recent post activity
```python
data = await hf.read({
    "posts": {"_uid": [uid], "_page": 1, "_perpage": 1, "pid": True, "dateline": True}
})
```

### Pull all contracts for a user (paginated)
```python
page, all_contracts = 1, []
while True:
    resp = await hf.read({"contracts": {"_uid": [uid], "_page": page, "_perpage": 30,
                                         "cid": True, "status": True, "type": True}})
    rows = resp.get("contracts", [])
    if isinstance(rows, dict): rows = [rows]
    if not rows: break
    all_contracts.extend(rows)
    if len(rows) < 30: break
    page += 1
```

### Resolve multiple UIDs to usernames in one call
```python
data  = await hf.read({"users": {"_uid": uid_list, "uid": True, "username": True}})
rows  = data.get("users", [])
if isinstance(rows, dict): rows = [rows]
names = {str(r["uid"]): r["username"] for r in rows}
```

### Get a user's b-rating history
```python
data = await hf.read({"bratings": {"_to": [uid], "_page": 1, "_perpage": 30,
                                    "crid": True, "amount": True, "message": True, "dateline": True}})
```

### Fetch posts correctly (last page = newest)
```python
# posts._uid is oldest-first. To get recent posts:
# 1. Get numreplies from threads endpoint
# 2. Calculate last page: last_page = ceil(numreplies / 30)
# 3. Fetch that page
import math
last_page = max(1, math.ceil(int(numreplies) / 30))
data = await hf.read({
    "posts": {"_tid": [tid], "_page": last_page, "_perpage": 30,
              "pid": True, "uid": True, "dateline": True, "message": True}
})
```

### Check unread PMs (requires Advanced Info scope)
```python
data  = await hf.read({"me": {"unreadpms": True}})
count = int(data["me"].get("unreadpms") or 0)
```

### Detect thread reply activity
```python
# Crawl threads._uid to get lastpost + lastposteruid — zero cost, free in any call
# Compare lastpost against stored cursor
# If changed and lastposteruid != your uid: flag for post fetch
# Fetch posts from correct page using numreplies to calculate page number
```

---

## Usergroups

`usergroup`, `displaygroup`, and `additionalgroups` all return numeric strings.
`displaygroup` is the group whose flair renders on the profile — may differ from primary group.
`additionalgroups` is comma-separated.

To check if a user is banned/exiled, check both `usergroup` **and** `displaygroup`:
```python
is_banned = usergroup in ("7", "38") or displaygroup in ("7", "38")
```

### Core Groups
| ID | Label |
|---|---|
| `"2"` | Registered |
| `"9"` | L33t |
| `"28"` | Ub3r |
| `"67"` | Vendor |
| `"7"` | Exiled |
| `"38"` | Banned |

### Member-Owned Groups
| ID | Label |
|---|---|
| `"46"` | H4CK3R$ |
| `"68"` | Brotherhood |
| `"48"` | Quantum |
| `"52"` | PinkLSZ |
| `"78"` | VIBE |
| `"70"` | Gamblers |
| `"50"` | Legends |
| `"77"` | Academy |
| `"71"` | Warriors |

---

## Rate Limit Budget

- Hard limit: ~240 calls/hour per token
- Track via `x-rate-limit-remaining` response header
- A good floor to pause background polling: 30 remaining
- Cost-free operations: reading from local DB/cache, client-side filtering
- Never increase polling intervals to solve rate limit problems — use batching, caching, and eliminating redundant calls

### Typical dashboard cost (1 active user)
| Task | Cost |
|---|---|
| Full dashboard refresh (balance + bytes + contracts + threads) | 2 calls |
| Reply detection (checking 30 threads for new activity) | 0 extra — free via threads._uid |
| Fetching posts for a thread with new replies | 1-3 calls depending on thread length |
| Username batch resolution | 1 call per 4 UIDs (max per call) |
| Autobump cycle (per 4 threads) | 1 read + 1-2 writes per bump |

---

## Known API Limitations

- **No prefix write** — cannot set thread prefixes via the API at all
- **No b-rating write** — b-ratings can only be left on the HF website
- **No contract create via API** that works reliably for all cases — the write endpoint exists but has constraints
- **No `from`/`to` counterparty fields** returned in bytes responses even when requested
- **Advanced Info scope required** for `unreadpms` — silently absent without it, not zero
- **Category FIDs** return empty when used as `_fid` in thread queries
- **`threads._uid`** returns up to 30 most recently active threads — quiet old threads fall out of view
