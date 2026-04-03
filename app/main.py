from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router
from app.core.config import settings
from app.db.database import init_db

app = FastAPI(title="Atlas-SubtitleSearchEngine")

ROOT_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))

app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    settings.ensure_dirs()
    init_db()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/results", response_class=HTMLResponse)
async def results_page(request: Request):
    return templates.TemplateResponse("results.html", {"request": request})

@app.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    return templates.TemplateResponse("library.html", {"request": request})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/video/{video_id}", response_class=HTMLResponse)
async def video_detail_page(request: Request, video_id: str):
    return templates.TemplateResponse(
        "video_detail.html",
        {"request": request, "video_id": video_id},
    )

app.include_router(router, prefix="/api")