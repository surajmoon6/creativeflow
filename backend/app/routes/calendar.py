"""The content calendar as the studio's team uses it: plan each post, upload its designs, mark it posted."""
from flask import Blueprint, g, jsonify, request

from .. import services as sv
from ..models import Client, Deliverable, Plan, db
from ..security import ApiError, check_project_access, is_staff, team_required
from ..serializers import calendar_payload, post_dict, thread_payload
from .admin import _int, body, get_or_404

bp = Blueprint("calendar", __name__, url_prefix="/api")


def _plans():
    q = Plan.query.join(Client)
    if is_staff():
        q = q.filter(Plan.client_id.in_([c.id for c in g.user.clients] or [0]))
    return q.order_by(Client.name).all()


def _plan_for(client_id):
    plan = Plan.query.filter_by(client_id=client_id).first()
    if not plan:
        raise ApiError("This client has no monthly plan yet.", 404, "not_found")
    check_project_access(plan.project)
    return plan


@bp.get("/calendar/clients")
@team_required
def calendar_clients():
    return jsonify([dict(id=p.client.id, name=p.client.display_name, plan=p.name, active=p.active,
                         unread=sum(sv.post_unread(d, "team") for d in sv.designs(p.project))) for p in _plans()])


@bp.get("/calendar/attention")
@team_required
def attention():
    """What the clients have sent that your team has not opened yet: new briefs and messages."""
    items = sv.team_attention(_plans())
    return jsonify(count=sum(i["count"] for i in items), items=items)


@bp.get("/calendar")
@team_required
def get_calendar():
    plan = _plan_for(_int(request.args, "client_id", 0, 1, label="Client"))
    return jsonify(calendar_payload(plan, request.args.get("month") or "", for_client=False))


@bp.post("/calendar/posts")
@team_required
def add_post():
    d = body()
    plan = _plan_for(_int(d, "client_id", 0, 1, label="Client"))
    post = sv.add_post(plan, d)
    db.session.commit()
    return jsonify(post_dict(post)), 201


def _post(did) -> Deliverable:
    d = get_or_404(Deliverable, did)
    if d.project.kind != "retainer":
        raise ApiError("Not found.", 404, "not_found")
    check_project_access(d.project)
    return d


@bp.get("/calendar/posts/<int:did>/thread")
@team_required
def get_thread(did):
    d = _post(did)
    sv.mark_thread_seen(d, "team")
    db.session.commit()
    return jsonify(thread=thread_payload(d, for_client=False))


@bp.post("/calendar/posts/<int:did>/messages")
@team_required
def send_message(did):
    d = _post(did)
    sv.add_message(d, "team", g.user.name, str(body().get("body", "")))
    sv.mark_thread_seen(d, "team")
    db.session.commit()
    return jsonify(thread=thread_payload(d, for_client=False)), 201


@bp.put("/calendar/posts/<int:did>")
@team_required
def update_post(did):
    d = sv.update_post(_post(did), body())
    db.session.commit()
    return jsonify(post_dict(d))


@bp.delete("/calendar/posts/<int:did>")
@team_required
def remove_post(did):
    sv.remove_post(_post(did))
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/calendar/posts/<int:did>/posted")
@team_required
def mark_posted(did):
    d = _post(did)
    sv.set_posted(d, bool(body().get("posted", True)))
    db.session.commit()
    return jsonify(post_dict(d))
