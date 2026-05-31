# HF API v2 - Agent Reference

> Reference for building HFToolbox integrations with the HackForums API v2.
> All patterns, gotchas, and field behaviours confirmed against live data.
> Docs: https://apidocs.hackforums.net/

---

## Core Concepts

- **Base URL:** `https://hackforums.net/api/v2`
- **All calls are POST.** Two routes: `/read` and `/write`
- Auth header required on every call: `Authorization: Bearer ACCESS_TOKEN`
- Request body key: `"asks"` - a nested JSON object
- `_underscore` fields = **inputs** (what to look up). Plain fields = **outputs** (set to `true` to return).
- **Max 4 endpoints per single `read()` call.** 5+ silently returns 503 with no warning.
- **Rate limit: ~240 calls/hour per token** (empirical). Tracked via `x-rate-limit-remaining` response header.
- `401` = missing or invalid access token

---

## OAuth2 Flow

### Step 1 - Get Authorization Code

Redirect user to:
```
https://hackforums.net/api/v2/authorize?response_type=code&client_id=CLIENT_ID&state=OPTIONAL_STATE
```

On approval, HF redirects to your URI:
```
https://YOUR_REDIRECT_URI/?code=CODE&state=STATE
```

### Step 2 - Exchange Code for Token


```
POST https://hackforums.net/api/v2/authorize
grant_type=authorization_code, client_id, client_secret, code
```

Returns: `access_token`, `expires_in`, and usually `refresh_token`. Fetch `/me` after token exchange to get the UID.

### Scopes

| Scope | Unlocks |
|---|---|
| Basic Info | Public profile of authorized user (`uid`, `username`, `usergroup`, `bytes`, `vault`, etc.) |
| Advanced Info | Private fields: `unreadpms`, `invisible`, `totalpms`, `lastactive`, `warningpoints` |
| Posts | Forums, threads, posts - includes optional write |
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

**`me.bytes` vs `users.myps`** - same thing (byte balance), different field name by endpoint.

**`me` advanced fields** (`unreadpms`, `warningpoints`, `invisible`, `totalpms`, `lastactive`) require the "Advanced Info" OAuth scope. If the token lacks that scope these fields are **absent** from the response - they will not come back as zero or null.

**`bytes.amount` must be cast as `int(float(x))`**, never `int(x)` directly - values like `"430.43"` will crash on direct int cast.

**`_perpage` max is 30** for all endpoints. Values above 30 return empty results.

**Cannot use the same endpoint key twice in one call.** e.g. can't have two `"bytes"` keys in one call.

**`_from`, `_to`, and `_uid` filters require integer UIDs**, not strings. Passing a string UID causes `_from` to silently return empty results.
```python
# Wrong
{"bytes": {"_to": [uid_str]}}
# Right
{"bytes": {"_to": [int(uid)]}}
```

**`from` and `to` embedded fields are never returned** even when explicitly requested - counterparty display is impossible via the bytes endpoint. Use separate `_from`/`_to` filter calls to determine direction.

**Avatar URLs are relative paths** - must be prefixed with the site URL:
```python
# API returns: "./uploads/avatars/avatar_123.jpg?dateline=..."
avatar = "https://hackforums.net/" + raw.lstrip("./")
```

**`additionalgroups`** returns a comma-separated string - split on `,` to get individual group IDs.

**`contracts.idispute` / `odispute`** are embedded in the contract response - no extra API call needed.

**`posts._uid`** returns only replies to other threads, NOT the user's own thread OPs - must combine with `firstpost` pids from threads response and dedupe to get all posts.

**`threads._uid`** does not reliably return `numreplies` in all contexts - verify before relying on it.

**`threads._uid` page 1 is newest/most recently active. `posts._uid` is oldest-first; fetch the last page for recent activity.**

---

## Read Endpoints

### /me - Authorized user's own data
Scope: Basic Info (Advanced Info for private fields)

| Field | Scope | Notes |
|---|---|---|
| `uid`, `username`, `usergroup`, `displaygroup`, `additionalgroups` | Basic | |
| `postnum`, `threadnum`, `awards` | Basic | |
| `bytes` | Basic | Token owner's byte balance - `users` endpoint calls this `myps` |
| `vault` | Basic | API Client Vault balance |
| `avatar`, `avatardimensions`, `avatartype` | Basic | Avatar is a relative path - prefix `https://hackforums.net/` |
| `lastvisit`, `usertitle`, `website`, `timeonline`, `reputation`, `referrals` | Basic | |
| `lastactive`, `unreadpms`, `invisible`, `totalpms`, `warningpoints` | Advanced | Absent (not zero) if scope missing |

- `avatardimensions` returns `"120|120"` (pipe-separated width|height string)
- `additionalgroups` returns a comma-separated string e.g. `"67,68,78"`

---

### /users - Any user(s) by UID
Scope: Users Permissions  
Input: `_uid` [array of ints]

Fields: `uid`, `username`, `usergroup`, `displaygroup`, `additionalgroups`, `postnum`, `threadnum`, `awards`, `myps`, `avatar`, `avatardimensions`, `avatartype`, `usertitle`, `website`, `timeonline`, `reputation`, `referrals`

> `myps` = byte balance. Same data as `me.bytes` but different field name.  
> Advanced scope fields (`unreadpms` etc.) are **not available** via `/users` - only via `/me`.

---

### /forums - Forum metadata
Scope: Posts Permissions  
Input: `_fid` [array]  
Fields: `fid`, `name`, `description`, `type`

| type code | Description |
|---|---|
| `f` | Forum - actual subforum, contains threads |
| `c` | Category - parent container, no threads directly |

> Only `type="f"` forums will ever have threads. Never use category FIDs as `_fid` inputs for thread queries.

**Category FID set** (never valid for `_fid` thread queries):
`1, 7, 45, 88, 105, 120, 141, 151, 156, 241, 259, 444, 445, 446, 447, 448, 449, 450, 451, 452, 453, 460`

#### Known FIDs - Forum Map

Category FIDs (`type="c"`) are bold. Do not use category FIDs as `_fid` inputs for thread watching.

| FID | Name | Parent |
|---|---|---|
| **1** | **Hack Forums Official Information** | root |
| 2 | Site News | 1 |
| 134 | Suggestions and Ideas | 2 |
| **45** | **Hacks, Exploits, and Various Discussions** | root |
| **447** | **Blackhat** | 45 |
| 10 | Hacking Tools and Programs | 447 |
| 114 | Remote Administration Tools | 447 |
| 92 | Botnets and Botting | 447 |
| 113 | Keyloggers | 447 |
| 126 | Cryptography, Encryption, and Decryption | 447 |
| 287 | Malware and Viruses | 447 |
| 405 | Blackhat Training | 447 |
| 229 | Reverse Engineering | 405 |
| 466 | Jailbreaking, Modding, and Rooting | 447 |
| **449** | **Grayhat** | 45 |
| 4 | Beginner Hacking | 449 |
| 47 | Hacking Tutorials | 4 |
| 43 | Website Hacking | 449 |
| 103 | SQL Injection Attacks | 43 |
| 91 | VPN, Proxies, and Socks | 449 |
| 46 | Social Media Hacks | 449 |
| 104 | Wifi / 5G / WPA / WEP / Bluetooth / Wireless Hacking | 449 |
| 433 | Hacktivism | 449 |
| **448** | **Whitehat** | 45 |
| 110 | Malware, Rat, and Virus Removal | 448 |
| 400 | White Hat Hacking | 448 |
| 322 | OpSec and OSINT | 448 |
| 231 | Pentesting and Forensics | 448 |
| 193 | IoT, Embedded Systems, Electronics, Gadgets, and DIY | 448 |
| 434 | Bug Bounties | 448 |
| **444** | **Tech** | root |
| **460** | **Artificial Intelligence** | 444 |
| 431 | Artificial Intelligence Discussion | 460 |
| 461 | Prompt Engineering & Optimization | 460 |
| 462 | AI Programming and Vibe Coding | 460 |
| 463 | AI for Marketing & Automation | 460 |
| 464 | AI Tools, APIs & Platforms | 460 |
| 465 | AI-Generated Art, Music & Video | 460 |
| **151** | **Coding** | 444 |
| 5 | Coders Lounge | 151 |
| 118 | Software Development | 151 |
| 117 | Mobile Development | 151 |
| 183 | Web Development | 151 |
| 375 | HF API | 151 |
| **88** | **Computing** | 444 |
| 8 | Computing Lounge | 88 |
| 87 | Computer Hardware | 88 |
| 240 | Networking and Firewalls | 87 |
| 79 | Mobile Smartphones | 88 |
| 192 | Android OS | 79 |
| 137 | Apple iOS | 79 |
| 347 | Microsoft Windows | 88 |
| 85 | Linux | 88 |
| 159 | MacOS | 88 |
| **141** | **Webmasters** | 444 |
| 50 | Website Construction | 141 |
| 172 | Website Showcase and Reviews | 141 |
| 142 | SEO and Internet Marketing | 141 |
| 139 | Social Networking | 141 |
| 143 | Hosting and Web Servers | 141 |
| **156** | **Graphics** | 444 |
| 6 | Graphics | 156 |
| 248 | Graphic Resources | 6 |
| 157 | GFX Contests | 6 |
| 133 | Rate My Graphic | 156 |
| 158 | Free Graphic Help | 156 |
| 160 | Video Editing | 156 |
| 293 | Photography | 156 |
| **241** | **Money** | root |
| 380 | Crypto Currency | 241 |
| **120** | **Monetizing Techniques** | 241 |
| 221 | Free Money Making Ebooks | 120 |
| 245 | Surveys | 120 |
| 127 | Referrals | 120 |
| 268 | CPA / PPD Make Money | 120 |
| 170 | Adult Content Management | 241 |
| 155 | Member Contests | 241 |
| 121 | Shopping Deals | 241 |
| 281 | Markets, Finance, and Investing | 241 |
| **105** | **Marketplace** | root |
| **450** | **Bazaar** | 105 |
| 163 | Marketplace Discussions | 450 |
| 402 | Promotional Advertising | 450 |
| 186 | Free Services and Giveaways | 450 |
| 205 | Appraisals and Pricing | 450 |
| 217 | Jobs and Partnerships | 450 |
| 111 | Deal Disputes | 450 |
| **451** | **Premium** | 105 |
| 107 | Premium Sellers Section | 451 |
| 374 | Premium Tools and Programs | 451 |
| 299 | Cryptography and Encryption Market | 451 |
| 136 | Ebook Bazaar | 451 |
| 182 | Currency Exchange | 451 |
| 218 | Virtual Game Items | 451 |
| **452** | **Services** | 105 |
| 145 | Hosting Services | 452 |
| 263 | Social Media Services | 452 |
| 106 | Service Offerings | 452 |
| 219 | Graphics Market | 452 |
| 171 | VPN and Proxy Services | 452 |
| 308 | Service Requests | 452 |
| **453** | **Auxiliary** | 105 |
| 44 | Buyers Bay | 453 |
| 176 | Member Sales Market | 453 |
| 291 | Online Accounts | 453 |
| 404 | Adult Zone Accounts | 291 |
| 339 | Hash Bounties | 453 |
| 255 | Rewards and Small Favors | 453 |
| 225 | Webmaster Marketplace | 453 |
| **7** | **General Topics** | root |
| **445** | **World** | 7 |
| 25 | The Lounge | 445 |
| 89 | News and Happenings | 445 |
| 12 | Bragging Rights | 445 |
| 260 | Education and Careers | 445 |
| **446** | **Entertainment** | 7 |
| 65 | Gaming | 446 |
| 112 | Anime and Manga | 446 |
| 32 | Movies, TV, and Videos | 446 |
| 37 | Music | 446 |
| 167 | Sports | 446 |
| 385 | Cars, Bikes, and Motors | 446 |
| **259** | **Personal Life** | 7 |
| 318 | Vices | 259 |
| 370 | Gambling | 259 |
| 262 | Health Wise | 259 |
| 180 | Innuendo | 259 |
| 261 | Pets and Animals | 259 |
| 354 | Food, Recipes, and Cooking | 259 |

---

### /threads - Thread info
Scope: Posts Permissions

| Input | Description |
|---|---|
| `_tid` [array] | Specific threads by ID |
| `_fid` [array] | All threads in a forum |
| `_uid` [array] | Threads by user - supports `_page`, `_perpage` |

Fields: `tid`, `uid`, `fid`, `subject`, `closed`, `numreplies`, `views`, `dateline`, `firstpost`, `lastpost`, `lastposter`, `lastposteruid`, `prefix`, `icon`, `poll`, `username`, `sticky`, `bestpid`

> `_uid` page 1 sorted newest first = user's most recently active threads.

---

### /posts - Post info
Scope: Posts Permissions

| Input | Description |
|---|---|
| `_pid` [array] | Specific posts by ID |
| `_tid` [array] | All posts in a thread - supports `_page`, `_perpage` |
| `_uid` [array] | Posts by user - supports `_page`, `_perpage` |

Fields: `pid`, `tid`, `uid`, `fid`, `dateline`, `message`, `subject`, `edituid`, `edittime`, `editreason`

> Posts support an embedded `author` object to avoid a separate `/users` call:
> ```python
> "posts": {"_tid": [TID], "message": True, "author": {"uid": True, "username": True}}
> ```
> `_uid` returns oldest-first. Page 1 = user's oldest posts. Fetch the last page for recent activity.

---

### /bytes - Byte transaction history
Scope: Bytes Permissions

| Input | Description |
|---|---|
| `_id` [array] | Specific transactions |
| `_uid` [array] | All transactions for user (sent + received) |
| `_from` [array] | Transactions SENT by user - requires int UID |
| `_to` [array] | Transactions RECEIVED by user - requires int UID |

All support `_page`, `_perpage` (max 30).

Fields: `id`, `amount`, `dateline`, `type`, `reason`, `post` (embedded when requested)

> `amount` is a float string (e.g. `"430.43"`) - always cast via `int(float(x))`.  
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
| `don` | IN/OUT | Peer-to-peer send/receive - contract payments come in as `don` with reason `"Contract"` |
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

### /contracts - Contract info
Scope: Contracts Permissions

| Input | Description |
|---|---|
| `_cid` [array] | Specific contracts by ID |
| `_uid` [array] | All contracts you're party to - supports `_page`, `_perpage` |

Fields: `cid`, `dateline`, `otherdateline`, `public`, `timeout_days`, `timeout`, `status`, `type`, `istatus`, `ostatus`, `muid`, `inituid`, `otheruid`, `iprice`, `icurrency`, `iproduct`, `oprice`, `ocurrency`, `oproduct`, `terms`, `tid`, `idispute`, `odispute`

> `idispute`/`odispute` are embedded - dispute info comes free with the contracts call.  
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
> `istatus`/`ostatus`: `"0"` = not approved, `"1"` = approved - per-party flags, separate from overall `status`.

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
Note: `contracts.php` with an **s** - not `contract.php`.

---

### /bratings - Buyer/seller ratings
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

### /disputes - Contract disputes
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

### /sigmarket - Signature marketplace

**market** - Input: `_type`=`"market"`, `_uid` [array], `_page`, `_perpage`  
Fields: `uid`, `user` (embedded), `price`, `duration`, `active`, `sig`, `dateadded`, `ppd`

**order** - Input: `_type`=`"order"`, `_smid`/`_uid`/`_seller`/`_buyer` [arrays], `_page`, `_perpage`  
Fields: `smid`, `buyer`/`seller` (embedded User), `startdate`, `enddate`, `price`, `duration`, `active`

---

## Write Endpoints

All writes: `POST https://hackforums.net/api/v2/write` + `Authorization: Bearer TOKEN`

### posts - Reply to a thread
Scope: Posts Write
```python
{"posts": {"_tid": TID, "_message": "BBCode content"}}
```
Returns: `pid`, `tid`, `uid`, `message`

---

### threads - Create a thread
Scope: Posts Write
```python
{"threads": {"_fid": FID, "_subject": "Title", "_message": "Body"}}
```
Returns: `tid`, `uid`, `subject`, `dateline`, `firstpost` {`pid`, `message`}

> **No `_prefix` parameter exists.** Prefixes cannot be set via the API - must be set manually on HF after posting.

---

### bytes - Byte operations
Scope: Bytes Write
```python
# Send bytes to a user
{"bytes": {"_uid": "UID", "_amount": "100", "_reason": "Payment", "_pid": "optional_pid"}}

# Deposit to vault (min 100)
{"bytes": {"_deposit": 500}}

# Withdraw from vault (min 100)
{"bytes": {"_withdraw": 500}}

# Bump a thread (costs bytes, uses Stanley bot)
{"bytes": {"_bump": TID}}
```

Send bytes returns `bytes[0].id` (transaction ID).

---

### contracts - Contract actions
Scope: Contracts Write
All actions except `new` require `_cid`.

| `_action` | Required params | Optional params | Notes |
|---|---|---|---|
| `new` | `_uid`, `_terms`, `_position` | `_yourproduct`, `_yourcurrency`, `_youramount`, `_theirproduct`, `_theircurrency`, `_theiramount`, `_tid`, `_muid`, `_timeout` (default 14d), `_public`=`"yes"`, `_address` | Creates contract |
| `undo` | `_cid` | | Undo a contract you just created |
| `deny` | `_cid` | | Deny as counterparty |
| `approve` | `_cid` | `_address` | Approve as counterparty |
| `cancel` | `_cid` | | Request cancellation - both parties must submit |
| `complete` | `_cid` | `_address` (txn ID) | Mark your side complete |
| `middleman_deny` | `_cid` | | Middleman rejects the contract |
| `middleman_approve` | `_cid` | | Middleman approves the contract |
| `vendor_cancel` | `_cid` | | Cancel a template-spawned contract as vendor |

> `_position` values: `selling`, `buying`, `exchanging`, `trading`, `vouchcopy`

---

### sigmarket - Signature market actions
Scope: Sigmarket Permissions
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
- Max **4 endpoints per call** - 5+ causes a silent 503
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

# Call 2: sent bytes  [1/4 slots - can't combine two "bytes" keys]
data2 = await hf.read({
    "bytes": {"_from": [uid_int], "_page": 1, "_perpage": 30,
              "id": True, "amount": True, "dateline": True, "reason": True, "type": True},
})
```

---

## Common Patterns

### Detect a user's recent post activity
```python
# posts._uid is oldest-first. Estimate the last page from profile counts,
# then fetch that page and sort by dateline descending.
import math
reply_count = max(0, int(user["postnum"]) - int(user["threadnum"]))
last_page = max(1, math.ceil(reply_count / 30))
data = await hf.read({
    "posts": {"_uid": [uid], "_page": last_page, "_perpage": 30,
              "pid": True, "tid": True, "dateline": True, "message": True}
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

### Fetch the newest posts in a thread
```python
# posts._tid is paginated oldest-first. Use the thread reply count to fetch the last page.
import math
last_page = max(1, math.ceil((int(numreplies) + 1) / 30))
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
# Crawl threads._uid to get lastpost + lastposteruid - zero cost, free in any call
# Compare lastpost against stored cursor
# If changed and lastposteruid != your uid: flag for post fetch
# Fetch posts from correct page using numreplies to calculate page number
```

---

## Usergroups

`usergroup`, `displaygroup`, and `additionalgroups` all return numeric strings.
`displaygroup` is the group whose flair renders on the profile - may differ from primary group.
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
- Prefer batching, caching, and eliminating redundant calls before increasing polling intervals

### Typical dashboard cost (1 active user)
| Task | Cost |
|---|---|
| Full dashboard refresh (balance + bytes + contracts + threads) | 2 calls |
| Reply detection (checking 30 threads for new activity) | 0 extra - free via threads._uid |
| Fetching posts for a thread with new replies | 1-3 calls depending on thread length |
| Username batch resolution | 1 call per users endpoint batch |
| Autobump cycle (per 4 threads) | 1 read + 1-2 writes per bump |

---

## Known API Limitations

- **No prefix write** - cannot set thread prefixes via the API at all
- **No b-rating write** - b-ratings can only be left on the HF website
- **No contract create via API** that works reliably for all cases - the write endpoint exists but has constraints
- **No `from`/`to` counterparty fields** returned in bytes responses even when requested
- **Advanced Info scope required** for `unreadpms` - silently absent without it, not zero
- **Category FIDs** return empty when used as `_fid` in thread queries
- **`threads._uid`** returns up to 30 most recently active threads - quiet old threads fall out of view
