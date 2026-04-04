# HF Toolbox

HFToolbox is a self-hosted web dashboard for [HackForums](https://hackforums.net). Instead of juggling tabs and refreshing your profile page, you get everything in one place — your bytes, contracts, threads, posting, and more — all pulling live from the HF API v2.

You host it yourself. Your data stays on your server. Anyone with an HF account can log in with OAuth and get their own isolated dashboard.

---

**What it looks like in practice:**
- You open the dashboard and immediately see your byte balance, recent transactions, active contracts, and which threads are due for a bump
- You click into Bytes and see your full transaction history going back years, broken down by category (sportsbook, slots, contract payments, etc.)
- You look up another member and see their recent posts, threads, b-ratings, and trade history in one view
- You set up Auto Bumper and your marketplace threads get bumped on schedule without you touching anything

---

## Features

- **Dashboard** — bytes balance, vault, transaction history, active contracts, and auto-bumper at a glance
- **Bytes** — full transaction history with search, stats/analytics by category (sportsbook, slots, contracts, etc.), send bytes, vault deposit/withdraw
- **Contracts** — contract list with status filtering, contract detail view with terms and dispute info
- **Auto Bumper** — schedule threads to be bumped automatically at set intervals with smart skip logic
- **Posting** — reply to threads with a BBCode editor and draft system
- **Sigmarket** — browse and manage signature marketplace listings
- **User Lookup** — look up any HF user's profile, recent posts, threads, b-ratings, and trade stats
- **Groups** — browse member-owned groups and their members
- **Bytes Crawler** — background task that builds a complete local history of your byte transactions

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLite (WAL mode) |
| Frontend | React 18, Vite, Zustand |
| Auth | HF OAuth2 |
| Reverse proxy | Caddy (recommended) or nginx |

---

## Prerequisites

1. A HackForums account
2. An HF API OAuth application — create one at `usercp.php?action=options` → API Management
3. Python 3.11+
4. Node.js 18+

> **Cloudflare / Datacenter IPs:** HackForums is behind Cloudflare, which blocks most cloud/VPS IP ranges. If you're hosting on a server (DigitalOcean, AWS, etc.) you'll need to route API calls through a residential proxy. Set `HF_PROXY_URL` in your `.env` — see [Proxy Setup](#proxy-setup) below.

---

## Setup

### Option A — Docker (recommended, works on Linux/Mac/Windows)

```bash
git clone https://github.com/AuJusDemon/hftoolbox.git
cd hftoolbox

cp backend/.env.example backend/.env
# Edit backend/.env with your credentials

docker compose up -d
```

That's it. Frontend on port 80, backend on port 8000. Put Caddy or nginx in front for HTTPS.

---

### Option B — Manual (Linux)

**1. Clone**
```bash
git clone https://github.com/AuJusDemon/hftoolbox.git
cd hftoolbox
```

**2. Backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set HF_CLIENT_ID, HF_CLIENT_SECRET, SESSION_SECRET, FRONTEND_URL
```

Run manually:
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Or install as a systemd service (auto-start on boot):
```bash
# Edit hftoolbox.service if your install path differs from /opt/hftoolbox
sudo cp hftoolbox.service /etc/systemd/system/
sudo systemctl enable --now hftoolbox
sudo systemctl status hftoolbox
```

**3. Frontend**
```bash
cd frontend
npm install
npm run build   # outputs to dist/
```

**4. Reverse Proxy (Caddy)**

```bash
sudo apt install caddy   # or download from caddyserver.com
```

Caddyfile:
```
yourdomain.com {
    handle /auth/*    { reverse_proxy localhost:8000 }
    handle /api/*     { reverse_proxy localhost:8000 }
    handle /modules/* { reverse_proxy localhost:8000 }
    handle /health    { reverse_proxy localhost:8000 }
    handle {
        root * /path/to/hftoolbox/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

---

### Option C — Manual (Windows)

**Backend:**
```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
:: Edit .env then:
python -m uvicorn main:app --port 8000
```

**Frontend:** same as Linux — `npm install && npm run build`

**Reverse proxy:** Download [Caddy for Windows](https://caddyserver.com/download), use same Caddyfile as above.

---

## Proxy Setup

If you're on a datacenter IP and getting 403 errors from HF, set `HF_PROXY_URL` in your `.env`:

```env
# HTTP proxy
HF_PROXY_URL=http://user:password@proxy.example.com:8080

# SOCKS5
HF_PROXY_URL=socks5://user:password@proxy.example.com:1080
```

Any aiohttp-compatible proxy URL works. 

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

| Variable | Description |
|---|---|
| `HF_CLIENT_ID` | Your HF OAuth app client ID |
| `HF_CLIENT_SECRET` | Your HF OAuth app client secret |
| `HF_REDIRECT_URI` | Must exactly match what you set in your HF app (e.g. `https://yourdomain.com/auth/callback`) |
| `SESSION_SECRET` | Random secret for session signing — use `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FRONTEND_URL` | Your frontend URL (used for CORS) |
| `HF_PROXY_URL` | Optional residential proxy URL — needed on datacenter IPs |
| `ENV` | `production` or `development` |

---

## Database

SQLite database is created automatically at `backend/data/hf_dash.db` on first run. No migrations needed. The database runs in WAL mode for better concurrent read performance.

---

## HF API Notes

A few things that aren't obvious from the HF API docs and took testing to figure out:

- `posts._uid` is **oldest-first**. Page 1 = the user's oldest post, not newest. Fetch the last page for recent activity.
- `posts._uid` does **not** reliably include thread OPs — filter them using `firstpost` PIDs from the `threads` response.
- `bytes.amount` must be cast as `int(float(x))` — values like `"430.43"` crash on direct `int()`.
- `_from`, `_to`, and `_uid` filter inputs require **integer UIDs**, not strings.
- Max **4 endpoints per `read()` call** — 5+ silently returns 503.
- `unreadpms` and other advanced fields require the **Advanced Info** OAuth scope.
- HF contract URL uses `contracts.php` (with an s) — not `contract.php`.

---

## Rate Limits

The HF API allows ~240 calls/hour per token. HFToolbox tracks remaining calls per token and displays them in the top nav bar. Background tasks (bytes crawler, auto-bumper) are designed to stay well within budget.

---

## License

MIT — do whatever you want with it. A shoutout is appreciated but not required.

---

## Contributing

PRs welcome. If you're adding a new page or module, follow the existing pattern — FastAPI router in `backend/modules/`, React page in `frontend/src/core/`.