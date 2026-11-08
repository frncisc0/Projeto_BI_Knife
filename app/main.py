import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ai.provider import NoAIProvider
from app.api.routes import router
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.version, docs_url=None, redoc_url=None)
app.state.ai_provider = NoAIProvider()
# Only local Host headers are accepted (mitigates DNS rebinding against the local API).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.include_router(router)
app.mount("/static", StaticFiles(directory=settings.frontend_dir, check_dir=True), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")
