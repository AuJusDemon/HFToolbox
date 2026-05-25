def format_alert(event: dict) -> str:
    t     = event.get("type", "")
    title = (event.get("title") or "").strip()
    body  = (event.get("body") or "").strip()
    link  = (event.get("link") or "").strip()

    if t == "contract_new":
        text = "📜 <b>New contract</b>"
        if title:
            text += f"\n{title}"
    elif t == "contract_status_change":
        text = "📜 <b>Contract updated</b>"
        if title:
            text += f"\n{title}"
    elif t == "contract_b_rating":
        text = "⭐ <b>B-rating received</b>"
        if title:
            text += f"\n{title}"
    elif t == "contract_dispute":
        text = "⚠️ <b>Contract disputed</b>"
        if title:
            text += f"\n{title}"
    elif t == "pm_unread_increase":
        text = "✉️ <b>New private messages</b>"
        if title:
            text += f"\n{title}"
    elif t == "reply_tracked_thread":
        text = "💬 <b>New reply</b>"
        if title:
            text += f"\n{title}"
        if body:
            text += f"\n{body}"
    elif t == "bytes_received":
        text = "💰 <b>Bytes received</b>"
        if title:
            text += f"\n{title}"
        if body:
            text += f"\n{body}"
    elif t == "token_dead":
        text = "🔐 <b>Auth token expired</b>"
        if body:
            text += f"\n{body}"
        else:
            text += "\nYour HackForums token has expired. Log back in to HFToolbox to resume autobump and alerts."
    elif t == "token_expiring":
        text = "⏰ <b>Auth token expiring soon</b>"
        if body:
            text += f"\n{body}"
    elif t == "autobump_budget":
        text = "💸 <b>Autobump weekly budget hit</b>"
        if body:
            text += f"\n{body}"
    elif t == "autobump_paused":
        text = "⏸️ <b>Autobump paused — token expired</b>"
        if body:
            text += f"\n{body}"
        else:
            text += "\nLog back in to HFToolbox to resume."
    elif t == "autobump_daily":
        text = "⚡ <b>Autobump daily recap</b>"
        if body:
            text += f"\n{body}"
    elif t == "sigmarket_sale":
        text = "💰 <b>Sig space sold</b>"
        if body:
            text += f"\n{body}"
    else:
        text = f"🔔 <b>{title}</b>" if title else "🔔 New alert"
        if body:
            text += f"\n{body}"

    if link:
        text += f'\n<a href="{link}">View</a>'

    return text
