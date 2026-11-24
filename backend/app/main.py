from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import characters, editing, jobs, media, projects, references, styles, system, voices
from app.core.config import settings
from app.core.database import init_db
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.services.jobs import mark_interrupted_on_startup
from app.services.storage_service import ensure_dirs


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    ensure_dirs()
    (settings.projects_dir / "project-data").mkdir(parents=True, exist_ok=True)
    init_db()
    mark_interrupted_on_startup()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
register_error_handlers(app)
app.include_router(system.router)
app.include_router(projects.router)
app.include_router(media.router)
app.include_router(jobs.router)
app.include_router(references.router)
app.include_router(styles.router)
app.include_router(editing.router)
app.include_router(voices.router)
app.include_router(characters.router)
