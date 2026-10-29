"""Team accounts. Only the studio owner can add employees, choose which clients they see, or switch them off."""
import re

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from ..models import Client, User, db
from ..security import ApiError, admin_required
from .admin import _str, body, get_or_404

bp = Blueprint("team", __name__, url_prefix="/api")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def member_dict(u: User):
    return dict(id=u.id, name=u.name, email=u.email, role=u.role, active=u.active,
                created_at=u.created_at.isoformat() + "Z", client_ids=[c.id for c in u.clients],
                clients=[dict(id=c.id, name=c.display_name) for c in u.clients])


def _clients(ids):
    if not isinstance(ids, list):
        raise ApiError("Choose clients from the list.")
    found = Client.query.filter(Client.id.in_([int(i) for i in ids if str(i).isdigit()])).all() if ids else []
    return found


def _password(d, required):
    pw = str(d.get("password") or "")
    if not pw and not required:
        return None
    if len(pw) < 10:
        raise ApiError("The password must be at least 10 characters.")
    return pw


@bp.get("/team")
@admin_required
def list_team():
    users = User.query.order_by(User.role.asc(), User.name.asc()).all()
    return jsonify([member_dict(u) for u in users])


@bp.post("/team")
@admin_required
def create_member():
    d = body()
    email = (_str(d, "email", 255, required=True, label="Email") or "").lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address.")
    if User.query.filter_by(email=email).first():
        raise ApiError("There is already an account with this email.", 409)
    u = User(name=_str(d, "name", 120, required=True, label="Name"), email=email, role="staff", active=True,
             password_hash=generate_password_hash(_password(d, True)))
    u.clients = _clients(d.get("client_ids") or [])
    db.session.add(u)
    db.session.commit()
    return jsonify(member_dict(u)), 201


@bp.put("/team/<int:uid>")
@admin_required
def update_member(uid):
    u = get_or_404(User, uid)
    if u.role != "staff":
        raise ApiError("Only employee accounts can be changed here.", 409)
    d = body()
    if "name" in d:
        u.name = _str(d, "name", 120, required=True, label="Name")
    if "active" in d:
        u.active = bool(d["active"])
    if "client_ids" in d:
        u.clients = _clients(d["client_ids"])
    pw = _password(d, False)
    if pw:
        u.password_hash = generate_password_hash(pw)
    db.session.commit()
    return jsonify(member_dict(u))
