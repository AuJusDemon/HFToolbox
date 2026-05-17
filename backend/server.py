"""
server.py — Production only. Not in public repo.
Wraps main app and loads private extensions at startup.
"""
import asyncio
from contextlib import asynccontextmanager
from main import app, lifespan as _main_lifespan
import private_extensions


def _suppress_connection_reset(loop, context):
    """Suppress harmless client disconnect errors that crash uvicorn on Windows."""
    exc = context.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
        return
    msg = context.get("message", "")
    if "connection" in msg.lower() and "lost" in msg.lower():
        return
    loop.default_exception_handler(context)


@asynccontextmanager
async def _lifespan(app):
    asyncio.get_event_loop().set_exception_handler(_suppress_connection_reset)
    async with _main_lifespan(app):
        await private_extensions.on_startup(app)
        yield


app.router.lifespan_context = _lifespan
