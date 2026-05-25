import logging
import aiohttp

log = logging.getLogger("toolbox.telegram")

_API_BASE = "https://api.telegram.org/bot"
_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def send_message(token: str, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    url = f"{_API_BASE}{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        async with _get_session().post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return True
            if resp.status == 429:
                log.warning("Telegram rate limit chat_id=%s", chat_id)
                return False
            if resp.status in (400, 403):
                try:
                    data = await resp.json()
                    log.warning("Telegram rejected chat_id=%s: %s", chat_id, data.get("description", ""))
                except Exception:
                    pass
                return False
            log.warning("Telegram send failed chat_id=%s status=%s", chat_id, resp.status)
            return False
    except Exception as e:
        log.warning("Telegram send error chat_id=%s: %s", chat_id, e)
        return False


async def register_webhook(token: str, webhook_url: str, secret: str) -> bool:
    url = f"{_API_BASE}{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": secret,
        "allowed_updates": ["message"],
    }
    try:
        async with _get_session().post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            if data.get("ok"):
                log.info("Telegram webhook registered: %s", webhook_url)
                return True
            log.warning("setWebhook failed: %s", data.get("description", ""))
            return False
    except Exception as e:
        log.warning("setWebhook error: %s", e)
        return False
