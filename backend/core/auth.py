import base64
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from backend.core.config import get_settings


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        if not settings.auth_password:
            return await call_next(request)

        if request.url.path in ["/health", "/login", "/static/styles.css", "/static/login.css"]:
            return await call_next(request)

        authorization = request.headers.get("Authorization")

        if not authorization:
            auth_cookie = request.cookies.get("auth")
            if auth_cookie:
                authorization = f"Basic {auth_cookie}"

        if not authorization or not authorization.startswith("Basic "):
            return RedirectResponse(url=f"/login?redirect={request.url.path}", status_code=303)

        try:
            credentials = base64.b64decode(authorization[6:]).decode("utf-8")
            username, password = credentials.split(":", 1)
        except Exception:
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication credentials"},
                    headers={"WWW-Authenticate": f'Basic realm="{settings.auth_realm}"'},
                )
            response = RedirectResponse(url=f"/login?redirect={request.url.path}", status_code=303)
            response.delete_cookie("auth")
            return response

        username_correct = secrets.compare_digest(
            username.encode("utf-8"),
            settings.auth_username.encode("utf-8"),
        )
        password_correct = secrets.compare_digest(
            password.encode("utf-8"),
            settings.auth_password.encode("utf-8"),
        )

        if not (username_correct and password_correct):
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Incorrect username or password"},
                    headers={"WWW-Authenticate": f'Basic realm="{settings.auth_realm}"'},
                )
            response = RedirectResponse(url=f"/login?redirect={request.url.path}", status_code=303)
            response.delete_cookie("auth")
            return response

        return await call_next(request)
