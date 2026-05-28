import ssl
import logging
import aiohttp

log = logging.getLogger("toolbox.telegram")

_API_BASE = "https://api.telegram.org/bot"

# The server's network stack has a proxy with a self-signed cert in the chain.
# Skip verification for outbound Telegram API calls only.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_TIMEOUT = aiohttp.ClientTimeout(connect=5, sock_read=10, total=15)


def _new_session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(limit=5, ssl=_SSL_CTX)
    return aiohttp.ClientSession(connector=connector, timeout=_TIMEOUT)


async def send_message(token: str, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    url = f"{_API_BASE}{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True,
               "link_preview_options": {"is_disabled": True}}
    try:
        async with _new_session() as session:
            async with session.post(url, json=payload) as resp:
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
        async with _new_session() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if data.get("ok"):
                    log.info("Telegram webhook registered: %s", webhook_url)
                    return True
                log.warning("setWebhook failed: %s", data.get("description", ""))
                return False
    except Exception as e:
        log.warning("setWebhook error: %s", e)
        return False
