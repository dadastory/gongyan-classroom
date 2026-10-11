"""Serve the built React app without intercepting API or missing asset requests."""

import re
from pathlib import Path

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_REQUEST_BYTES = 1024 * 1024
FINGERPRINT = re.compile(r"-[A-Za-z0-9_-]{8,}\.")


class FrontendFiles(StaticFiles):
    async def check_config(self) -> None:
        # API-only development remains available before the first frontend build.
        if Path(self.directory).exists():
            await super().check_config()

    async def get_response(self, path: str, scope: Scope):
        raw_parts = scope["path"].split("/")
        if (
            path == "api"
            or path.startswith("api/")
            or any(part.startswith(".") for part in raw_parts if part)
            or "\\" in scope["path"]
            or "\x00" in scope["path"]
        ):
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if (
                error.status_code != 404
                or path == "assets"
                or path.startswith("assets/")
                or "." in Path(path).name and path != "."
            ):
                raise
            try:
                response = await super().get_response("index.html", scope)
            except HTTPException as missing:
                if missing.status_code != 404:
                    raise
                return JSONResponse({"detail": "网页资源暂不可用，请先构建前端"}, status_code=503)
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if path.startswith("assets/") and FINGERPRINT.search(Path(path).name)
            else "no-cache"
        )
        return response


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = Headers(scope=scope).get("content-length")
        if length is not None:
            try:
                declared_size = int(length)
                if declared_size < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse({"detail": "请求长度无效"}, status_code=400)(scope, receive, send)
                return
            if declared_size > self.max_bytes:
                await JSONResponse({"detail": "请求内容超过 1MiB 上限"}, status_code=413)(
                    scope, receive, send
                )
                return
        received_size = 0

        async def limited_receive():
            nonlocal received_size
            message = await receive()
            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))
                if received_size > self.max_bytes:
                    raise HTTPException(status_code=413, detail="请求内容超过 1MiB 上限")
            return message

        await self.app(scope, limited_receive, send)
