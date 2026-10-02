import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.ai.provider import NoAIProvider
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.version, docs_url=None, redoc_url=None)
app.state.ai_provider = NoAIProvider()
app.include_router(router)
app.mount("/static", StaticFiles(directory=settings.frontend_dir, check_dir=True), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")
