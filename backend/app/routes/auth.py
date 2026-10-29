import re

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..models import User, db
from ..security import ApiError, current_user, login_user, throttle_check, throttle_clear, throttle_fail

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _me(user):
    return dict(user=dict(id=user.id, name=user.name, email=user.email, role=user.role,
                          can_approve=user.can_approve if user.role == "client" else None), csrf=session.get("csrf"))


@bp.post("/login")
def login():
    """Only wrong passwords count against you. Several people signing in to one account, even from the same office or phone
    network, are never held up; guessing one account's password, or many accounts from one address, is."""
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    by_account, by_address = f"login:{request.remote_addr}:{email}", f"login-ip:{request.remote_addr}"
    throttle_check(by_account, 15, 300)  # generous: a few typos by a few colleagues never lock an account
    throttle_check(by_address, 60, 300)
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        throttle_fail(by_account)
        throttle_fail(by_address)
        raise ApiError("Incorrect email or password.", 401, "bad_credentials")
    throttle_clear(by_account)
    if not user.active:
        raise ApiError("This account has been switched off. Please contact the studio owner.", 403, "inactive")
    login_user(user)
    return jsonify(_me(user))


@bp.get("/options")
def options():
    """What the sign-in page may offer. Sign-up exists only on test installs (DEMO_SIGNUP=1)."""
    return jsonify(signup=current_app.config["DEMO_SIGNUP"])


@bp.post("/signup")
def signup():
    """Test installs only: create your own account and try the tool. Not available on a real server."""
    if not current_app.config["DEMO_SIGNUP"]:
        raise ApiError("Not found.", 404, "not_found")
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:120]
    email = str(data.get("email", "")).strip().lower()[:255]
    password = str(data.get("password", ""))
    by_address = f"signup:{request.remote_addr}"
    throttle_check(by_address, 20, 3600)
    if not name:
        raise ApiError("Enter your name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ApiError("Enter a valid email address. It can be a made-up one, such as you@example.com.")
    if len(password) < 8:
        raise ApiError("Choose a password of at least 8 characters.")
    if User.query.filter_by(email=email).first():
        raise ApiError("That email already has an account. Sign in instead.", 409, "exists")
    throttle_fail(by_address)
    user = User(email=email, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify(_me(user)), 201


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    user = current_user()
    if not user:
        raise ApiError("Please sign in.", 401, "unauthenticated")
    return jsonify(_me(user))
