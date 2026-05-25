import ssl
import logging
import aiohttp

log = logging.getLogger("toolbox.telegram")

_API_BASE = "https://api.telegram.org/bot"
_session: aiohttp.ClientSession | None = None

# Telegram API calls go out through the server's network stack, which may have
# a proxy with a self-signed cert in the chain. Skip verification for these
# outbound calls only - we're not receiving untrusted data, just posting to Telegram.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def send_message(token: str, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    url = f"{_API_BASE}{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        async with _get_session().post(url, json=payload, ssl=_SSL_CTX, timeout=aiohttp.ClientTimeout(total=10)) as resp:
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
        async with _get_session().post(url, json=payload, ssl=_SSL_CTX, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            if data.get("ok"):
                log.info("Telegram webhook registered: %s", webhook_url)
                return True
            log.warning("setWebhook failed: %s", data.get("description", ""))
            return False
    except Exception as e:
        log.warning("setWebhook error: %s", e)
        return False
