from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.gzip import GZipMiddleware

from .config import settings
from .db import SessionLocal
from .routes import ai, auth, discussion, reports, topics
from .web import FrontendFiles, RequestBodyLimitMiddleware
from .worker import worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(title="共研 · 课堂协作学习", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    # Pydantic's default input/ctx can echo passwords, API keys or private messages.
    return JSONResponse(
        {"detail": [{key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()]},
        status_code=422,
    )


app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    response = None
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in settings().origins:
            response = JSONResponse({"detail": "请求来源不被允许"}, status_code=403)
    if response is None:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "framework": "Agno", "version": "1.0.0"}


for router in (auth.router, topics.router, discussion.router, ai.router, reports.router):
    app.include_router(router, prefix="/api")

app.mount("/", FrontendFiles(directory=settings().frontend_dist, check_dir=False), name="frontend")
