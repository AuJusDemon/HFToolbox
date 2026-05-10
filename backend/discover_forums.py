"""
Run once to discover private group forum FIDs:
  python discover_forums.py
Uses the first stored token to probe known group forum parent FIDs.
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import db
from HFClient import HFClient

# Known group section FIDs to probe — the API will return their subforums
# if the token has access. Add more ranges as needed.
PROBE_FIDS = list(range(330, 420)) + list(range(420, 470)) + [52, 99]

async def main():
    uids = db.get_all_uids()
    if not uids:
        print("No users logged in")
        return
    token = db.get_token(uids[0])
    if not token:
        print("No token")
        return
    
    client = HFClient(token)
    
    # Batch in groups of 4 (API limit)
    found = []
    for i in range(0, len(PROBE_FIDS), 4):
        chunk = PROBE_FIDS[i:i+4]
        try:
            data = await client.read({"forums": {
                "_fid": chunk,
                "fid": True, "name": True, "type": True,
            }})
            if data:
                rows = data.get("forums", [])
                if isinstance(rows, dict): rows = [rows]
                for r in (rows or []):
                    print(f"FID {r.get('fid')}: {r.get('name')} (type={r.get('type')})")
                    found.append(r)
        except Exception as e:
            pass  # FID not accessible or doesn't exist
    
    print(f"\nFound {len(found)} accessible forums in probed range")

asyncio.run(main())
