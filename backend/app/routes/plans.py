"""The studio owner sets up a monthly client's plan and the sign-ins their people use."""
from datetime import date

from flask import Blueprint, jsonify, request

from .. import services as sv
from ..models import Client, User, db
from ..security import ApiError, admin_required
from ..serializers import login_dict, plan_detail
from .admin import _date, _int, _str, body, get_or_404

bp = Blueprint("plans", __name__, url_prefix="/api")


def _plan_fields(d, existing=None):
    return dict(
        name=_str(d, "name", 120) or "Monthly plan", monthly_price=_int(d, "monthly_price", 0, 0, 10**10, "Monthly price"),
        start_date=_date(d, "start_date") or (existing.start_date if existing else date.today()),
        active=bool(d.get("active", True)), revisions_per_post=_int(d, "revisions_per_post", 2, 0, 20, "Revisions"),
        inclusions=sv.clean_inclusions(d.get("inclusions")),
        client_approval=bool(d.get("client_approval", existing.client_approval if existing else False)),
        payment_reminder=bool(d.get("payment_reminder", existing.payment_reminder if existing else False)))


@bp.get("/clients/<int:cid>/plan")
@admin_required
def get_plan(cid):
    c = get_or_404(Client, cid)
    return jsonify(plan_detail(c.plan) if c.plan else None)


@bp.put("/clients/<int:cid>/plan")
@admin_required
def put_plan(cid):
    c = get_or_404(Client, cid)
    plan = sv.save_plan(c, _plan_fields(body(), c.plan))
    db.session.commit()
    return jsonify(plan_detail(plan))


@bp.post("/clients/<int:cid>/plan/toggles")
@admin_required
def plan_toggles(cid):
    """Switch the client's approval, or the month-end payment reminder, on or off without touching the rest of the plan."""
    c = get_or_404(Client, cid)
    if not c.plan:
        raise ApiError("This client has no monthly plan yet.", 404, "not_found")
    d = body()
    for k in ("client_approval", "payment_reminder"):
        if k in d:
            setattr(c.plan, k, bool(d[k]))
    db.session.commit()
    return jsonify(plan_detail(c.plan))


@bp.post("/clients/<int:cid>/plan/payments")
@admin_required
def record_payment(cid):
    """Write down money the client paid: the amount, the day, a reference and, if you have it, the payment screenshot."""
    c = get_or_404(Client, cid)
    if not c.plan:
        raise ApiError("This client has no monthly plan yet.", 404, "not_found")
    d = request.form if request.form else body()
    received = _date(d, "received_on") or date.today()
    sv.record_plan_payment(c.plan, _int(d, "amount", 0, 1, 10**10, "Amount"), received, str(d.get("reference") or ""),
                           str(d.get("note") or ""), request.files.get("proof"))
    db.session.commit()
    return jsonify(plan_detail(c.plan)), 201


@bp.post("/clients/<int:cid>/plan/invoice")
@admin_required
def plan_invoice(cid):
    """Make the client's invoice from their accepted quote; what they have already paid is taken off it."""
    c = get_or_404(Client, cid)
    if not c.plan:
        raise ApiError("This client has no monthly plan yet.", 404, "not_found")
    sv.issue_plan_invoice(c.plan)
    db.session.commit()
    return jsonify(plan_detail(c.plan)), 201


@bp.post("/clients/<int:cid>/plan/paid")
@admin_required
def plan_paid(cid):
    c = get_or_404(Client, cid)
    if not c.plan:
        raise ApiError("This client has no monthly plan yet.", 404, "not_found")
    sv.mark_plan_paid(c.plan, bool(body().get("paid", True)))
    db.session.commit()
    return jsonify(plan_detail(c.plan))


@bp.get("/clients/<int:cid>/logins")
@admin_required
def list_logins(cid):
    get_or_404(Client, cid)
    users = User.query.filter_by(role="client", client_id=cid).order_by(User.name).all()
    return jsonify([login_dict(u) for u in users])


@bp.post("/clients/<int:cid>/logins")
@admin_required
def create_login(cid):
    c = get_or_404(Client, cid)
    d = body()
    u = sv.create_client_login(c, str(d.get("name") or ""), str(d.get("email") or ""), str(d.get("password") or ""),
                               bool(d.get("can_approve", True)))
    db.session.commit()
    return jsonify(login_dict(u)), 201


@bp.put("/logins/<int:uid>")
@admin_required
def update_login(uid):
    from werkzeug.security import generate_password_hash
    u = get_or_404(User, uid)
    if u.role != "client":
        raise ApiError("Not found.", 404, "not_found")
    d = body()
    if "name" in d:
        u.name = _str(d, "name", 120, required=True, label="Name")
    if "active" in d:
        u.active = bool(d["active"])
    if "can_approve" in d:
        u.can_approve = bool(d["can_approve"])
    if d.get("password"):
        if len(str(d["password"])) < 10:
            raise ApiError("The password must be at least 10 characters.")
        u.password_hash = generate_password_hash(str(d["password"]))
    db.session.commit()
    return jsonify(login_dict(u))
