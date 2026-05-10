"""bytes_crawler/router.py — analytics endpoints served from local DB"""

import asyncio
import re
from fastapi import APIRouter, Request, HTTPException
import db

router = APIRouter(prefix="/api/bytes", tags=["bytes_history"])


def _uid(r: Request) -> str:
    uid = r.session.get("uid")
    if not uid: raise HTTPException(401)
    return uid


def categorize(reason: str) -> str:
    r = reason.lower()
    if "sportsbook wager" in r or "sport wager" in r: return "Sportsbook"
    if "wager winner" in r or "sports wager winner" in r: return "Sportsbook Win"
    if "slots" in r: return "Slots"
    if "blackjack" in r: return "Blackjack"
    if "flip" in r: return "Flips"
    if "bump" in r or "thread bump" in r: return "Thread Bumps"
    if "quick love" in r: return "Quick Love"
    if "rain" in r: return "Rain"
    if "contract" in r: return "Contracts"
    if "scratch" in r: return "Scratch Cards"
    if "lottery" in r or "lotto" in r: return "Lottery"
    if "crypto" in r: return "Crypto Game"
    if "casino" in r or "blackjack" in r: return "Casino"
    return "Other"


@router.get("/history/stats")
async def bytes_stats(request: Request):
    uid = _uid(request)
    txns = await asyncio.to_thread(db.get_bytes_history_all, uid)
    count = len(txns)
    if not count:
        return {"count": 0, "total_in": 0, "total_out": 0, "net": 0,
                "categories": [], "crawl": None}

    total_in  = sum(abs(float(t["amount"])) for t in txns if not t["sent"])
    total_out = sum(abs(float(t["amount"])) for t in txns if t["sent"])
    net       = total_in - total_out

    # Category breakdown
    from collections import defaultdict
    cat_in  = defaultdict(float)
    cat_out = defaultdict(float)
    for t in txns:
        cat = categorize(t.get("reason") or "")
        amt = abs(float(t["amount"]))
        if t["sent"]:
            cat_out[cat] += amt
        else:
            cat_in[cat] += amt

    all_cats = set(cat_in) | set(cat_out)
    categories = sorted([{
        "name":  cat,
        "in":    round(cat_in[cat], 2),
        "out":   round(cat_out[cat], 2),
        "net":   round(cat_in[cat] - cat_out[cat], 2),
    } for cat in all_cats], key=lambda x: abs(x["net"]), reverse=True)

    state = await asyncio.to_thread(db.get_crawl_state, uid)
    recv_done = bool(state.get("recv_done"))
    sent_done = bool(state.get("sent_done"))

    return {
        "count":      count,
        "total_in":   round(total_in, 2),
        "total_out":  round(total_out, 2),
        "net":        round(net, 2),
        "categories": categories,
        "crawl": {
            "complete":   recv_done and sent_done,
            "recv_page":  state.get("recv_page", 1),
            "sent_page":  state.get("sent_page", 1),
            "last_crawl": state.get("last_crawl"),
        }
    }
