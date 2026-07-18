"""
Run once to purge contaminated my_threads rows:
  python backfill_thread_ownership.py

dashboard_refresh.py used to trust HF's threads._uid filter alone as proof of
thread authorship, which isn't reliable enough (see HF_API_REFERENCE.md) -
threads where a uid was only a contract counterparty leaked into my_threads
as if they owned them. That write path is now fixed (verifies th.uid == uid
before recording), but existing bad rows are already persisted and won't
self-correct until each uid's next full crawl re-derives everything from
scratch. This re-verifies every row against real HF thread authorship and
deletes the ones that don't match.
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import db
from HFClient import HFClient
from modules.posting.posting_db import get_all_tracked_threads, delete_my_thread

TIDS_PER_CALL = 4  # HF API max TIDs per _tid list


async def main():
    rows = get_all_tracked_threads()
    if not rows:
        print("No tracked threads found")
        return

    by_uid: dict[str, list[str]] = {}
    for r in rows:
        by_uid.setdefault(str(r["uid"]), []).append(str(r["tid"]))

    total_checked = 0
    total_deleted = 0

    for uid, tids in by_uid.items():
        token = db.get_token(uid)
        if not token:
            print(f"uid={uid}: no token, skipping {len(tids)} row(s)")
            continue

        client = HFClient(token)
        real_owner: dict[str, str] = {}

        for i in range(0, len(tids), TIDS_PER_CALL):
            chunk = tids[i:i + TIDS_PER_CALL]
            try:
                data = await client.read({"threads": {"_tid": chunk, "tid": True, "uid": True}})
            except Exception as e:
                print(f"uid={uid} chunk={chunk}: fetch failed ({e}), leaving as-is")
                continue
            if not data:
                print(f"uid={uid} chunk={chunk}: no data returned, leaving as-is")
                continue
            thread_rows = data.get("threads", [])
            if isinstance(thread_rows, dict):
                thread_rows = [thread_rows]
            for t in (thread_rows or []):
                t_tid = str(t.get("tid") or "")
                if t_tid:
                    real_owner[t_tid] = str(t.get("uid") or "")

        for tid in tids:
            total_checked += 1
            owner = real_owner.get(tid)
            if owner is None:
                # HF didn't return this thread at all (deleted/inaccessible) - leave it,
                # not evidence of contamination, just stale/unreachable.
                continue
            if owner != uid:
                delete_my_thread(uid, tid)
                total_deleted += 1
                print(f"uid={uid}: deleted tid={tid} (real owner={owner})")

    print(f"\nChecked {total_checked} row(s), deleted {total_deleted} contaminated row(s)")

asyncio.run(main())
