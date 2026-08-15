from __future__ import annotations

from typing import Any

import db


def _rows(value: Any) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def _avatar_url(value: Any) -> str:
    avatar = str(value or "")
    if avatar and not avatar.startswith("http"):
        return "https://hackforums.net/" + avatar.lstrip("./")
    return avatar


def seed_users(rows: Any) -> int:
    out: dict[str, dict] = {}
    for row in _rows(rows):
        uid = str(row.get("uid") or row.get("lastposteruid") or "").strip()
        username = str(row.get("username") or row.get("lastposter") or "").strip()
        if not uid or not uid.isdigit() or not username:
            continue
        out[uid] = {
            "username": username,
            "avatar": _avatar_url(row.get("avatar")),
            "usertitle": str(row.get("usertitle") or ""),
            "reputation": int(row.get("reputation") or 0),
            "displaygroup": str(row.get("displaygroup") or row.get("usergroup") or ""),
            "additionalgroups": str(row.get("additionalgroups") or ""),
        }
    if out:
        db.upsert_uid_usernames(out)
    return len(out)


def seed_threads(rows: Any) -> int:
    titles: dict[str, str] = {}
    users: list[dict] = []
    for row in _rows(rows):
        tid = str(row.get("tid") or "").strip()
        subject = str(row.get("subject") or row.get("title") or "").strip()
        if tid and tid.isdigit() and subject:
            titles[tid] = subject
        if row.get("uid") and row.get("username"):
            users.append(row)
        if row.get("lastposteruid") and row.get("lastposter"):
            users.append({
                "uid": row.get("lastposteruid"),
                "username": row.get("lastposter"),
            })
    if titles:
        db.upsert_tid_titles(titles)
    if users:
        seed_users(users)
    return len(titles)


def seed_from_response(data: dict) -> dict[str, int]:
    seeded = {"users": 0, "threads": 0}
    if not isinstance(data, dict):
        return seeded
    seeded["users"] += seed_users(data.get("users"))
    seeded["threads"] += seed_threads(data.get("threads"))
    posts = data.get("posts")
    for post in _rows(posts):
        if post.get("uid") and post.get("username"):
            seeded["users"] += seed_users(post)
        author = post.get("author")
        if isinstance(author, dict):
            seeded["users"] += seed_users({
                "uid": author.get("uid") or post.get("uid"),
                "username": author.get("username") or post.get("username"),
                "avatar": author.get("avatar") or post.get("avatar"),
                "usertitle": author.get("usertitle") or post.get("usertitle"),
                "reputation": author.get("reputation") or post.get("reputation") or 0,
                "displaygroup": author.get("displaygroup") or author.get("usergroup") or "",
                "additionalgroups": author.get("additionalgroups") or "",
            })
    return seeded
