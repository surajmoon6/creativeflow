"""Admin auth (server-side session cookie), CSRF, rate limiting, and client token resolution."""
from __future__ import annotations

import secrets
import threading
import time
from functools import wraps

from flask import abort, current_app, g, jsonify, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .models import ReviewToken, User, db


class ApiError(Exception):
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


# ---------- admin session ----------

def login_user(user: User):
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    session["csrf"] = secrets.token_urlsafe(24)


def current_user():
    uid = session.get("uid")
    user = db.session.get(User, uid) if uid else None
    return user if user and user.active else None  # switching an account off ends its session at once


def _guard(allowed_roles: tuple[str, ...]):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                raise ApiError("Please sign in.", 401, "unauthenticated")
            if user.role not in allowed_roles:
                raise ApiError("This is for the studio owner.", 403, "owner_only")
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                sent = request.headers.get("X-CSRF-Token", "")
                if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
                    raise ApiError("Your session expired. Refresh the page.", 403, "csrf")
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco


# The studio owner only. Every route uses this unless it is deliberately opened to the team, so anything
# added later stays private to the owner by default.
admin_required = _guard(("admin",))
# The owner and employees. Employees are limited to their assigned clients (see check_project_access).
team_required = _guard(("admin", "staff"))
# A login belonging to someone at a client company. Their routes live under /api/c/ and are scoped to that client.
client_required = _guard(("client",))


def is_staff() -> bool:
    u = g.get("user")
    return bool(u and u.role == "staff")


def assigned_client_ids() -> set[int]:
    return {c.id for c in g.user.clients}


def check_project_access(project):
    """An employee asking for a project of a client they aren't assigned to gets 'not found', not 'forbidden'."""
    if is_staff() and project.client_id not in assigned_client_ids():
        raise ApiError("Not found.", 404, "not_found")


# ---------- rate limiting (in-process; fine for one gunicorn worker group, swap for Redis later) ----------

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()


def rate_limit(limit: int, per: int, scope: str | None = None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if current_app.config.get("RATELIMIT_ENABLED", True):
                who = getattr(getattr(g, "user", None), "id", None)  # a signed-in person is counted on their own, not with everyone sharing their IP
                key = f"{scope or fn.__name__}:{('u' + str(who)) if who else request.remote_addr}"
                t = time.monotonic()
                with _lock:
                    hits = [h for h in _hits.get(key, []) if t - h < per]
                    if len(hits) >= limit:
                        _hits[key] = hits
                        raise ApiError("Too many attempts. Please wait a minute and try again.",
                                       429, "rate_limited")
                    hits.append(t)
                    _hits[key] = hits
            return fn(*a, **kw)
        return wrapper
    return deco


def throttle_check(key: str, limit: int, per: int):
    """Refuse when `key` has already failed `limit` times in the last `per` seconds. Only failures are recorded (see throttle_fail)."""
    if not current_app.config.get("RATELIMIT_ENABLED", True):
        return
    t = time.monotonic()
    with _lock:
        hits = [h for h in _hits.get(key, []) if t - h < per]
        _hits[key] = hits
        if len(hits) >= limit:
            raise ApiError("Too many wrong attempts. Please wait a few minutes and try again.", 429, "rate_limited")


def throttle_fail(key: str):
    with _lock:
        _hits.setdefault(key, []).append(time.monotonic())


def throttle_clear(key: str):
    with _lock:
        _hits.pop(key, None)


# ---------- client review tokens ----------

TOKEN_MESSAGES = {
    "expired": "This review link has expired. Please contact the studio for a new link.",
    "revoked": "This review link is no longer active.",
    "invalid": "This link is not valid. Please check the link or contact the studio.",
}


def new_token() -> str:
    return secrets.token_urlsafe(16)  # 128 bits


def resolve_review_token(token: str) -> ReviewToken:
    """The token is the client's only credential. Project ids from the URL are never trusted."""
    if not token or len(token) > 64:
        raise ApiError(TOKEN_MESSAGES["invalid"], 404, "invalid")
    rt = ReviewToken.query.filter_by(token=token).first()
    if not rt:
        raise ApiError(TOKEN_MESSAGES["invalid"], 404, "invalid")
    if rt.state != "active":
        raise ApiError(TOKEN_MESSAGES[rt.state], 410, rt.state)
    return rt


# ---------- short-lived signed download links ----------

def _dl_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="cf-download")


def sign_download(project_id: int, file_id: int, review_token_id: int) -> str:
    return _dl_serializer().dumps({"p": project_id, "f": file_id, "t": review_token_id})


def read_download(signed: str) -> dict:
    try:
        return _dl_serializer().loads(signed, max_age=current_app.config["DOWNLOAD_LINK_TTL"])
    except SignatureExpired:
        raise ApiError("This download link has expired. Open your delivery page to get a fresh one.",
                       410, "expired")
    except BadSignature:
        abort(404)


def error_response(e: ApiError):
    return jsonify(error=e.message, code=e.code), e.status
