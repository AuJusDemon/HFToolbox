def format_alert(event: dict) -> str:
    t     = event.get("type", "")
    title = (event.get("title") or "").strip()
    body  = (event.get("body") or "").strip()
    link  = (event.get("link") or "").strip()

    if t == "contract_new":
        text = f"📜 <b>New contract</b>"
        if title:
            text += f"\n{title}"
    elif t == "contract_status_change":
        text = f"📜 <b>Contract update</b>"
        if title:
            text += f"\n{title}"
    elif t == "contract_b_rating":
        text = f"⭐ <b>B-rating received</b>"
        if title:
            text += f"\n{title}"
    elif t == "contract_dispute":
        text = f"⚠ <b>Contract dispute</b>"
        if title:
            text += f"\n{title}"
    elif t == "pm_unread_increase":
        text = f"✉ <b>New private messages</b>"
        if title:
            text += f"\n{title}"
    elif t == "reply_tracked_thread":
        text = f"💬 <b>New reply</b>"
        if title:
            text += f"\n{title}"
        if body:
            text += f"\n{body}"
    elif t == "bytes_received":
        text = f"💰 <b>Bytes received</b>"
        if title:
            text += f"\n{title}"
    else:
        text = f"🔔 <b>{title}</b>" if title else "🔔 New alert"
        if body:
            text += f"\n{body}"

    if link:
        text += f'\n<a href="{link}">View</a>'

    return text
