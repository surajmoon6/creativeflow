"""What a client's own login sees: their content calendar, and nothing else. No prices, no other clients."""
from flask import Blueprint, abort, g, jsonify, request, send_file

from .. import services as sv
from ..models import Deliverable, Plan, ProjectFile, ProjectVersion, db
from ..security import ApiError, client_required, rate_limit
from ..serializers import brand_dict, calendar_payload, post_dict, thread_payload
from ..storage import get_storage
from .admin import body, get_or_404

bp = Blueprint("portal", __name__, url_prefix="/api/c")


def _plan() -> Plan:
    plan = Plan.query.filter_by(client_id=g.user.client_id).first()
    if not plan or not plan.active:
        raise ApiError("Your monthly plan isn't active yet. Please contact the studio.", 404, "no_plan")
    return plan


def _own_post(did) -> Deliverable:
    d = get_or_404(Deliverable, did)
    if d.project.kind != "retainer" or d.project.client_id != g.user.client_id:
        raise ApiError("Not found.", 404, "not_found")  # someone else's post looks like no post at all
    return d


@bp.get("/calendar")
@client_required
def calendar():
    plan = _plan()
    out = calendar_payload(plan, request.args.get("month") or "", for_client=True)
    out.update(brand=brand_dict(), can_approve=g.user.can_approve and plan.client_approval, me=dict(name=g.user.name),
               payment=sv.plan_payment(plan),
               updates=[dict(e, at=e["at"].isoformat() + "Z") for e in sv.client_updates(plan)])
    return jsonify(out)


@bp.get("/posts/<int:did>")
@client_required
def post(did):
    d = _own_post(did)
    out = post_dict(d, for_client=True)  # what was unread when they opened it
    sv.mark_thread_seen(d, "client")
    db.session.commit()
    out["history"] = [dict(id=v.id, number=v.label, status=v.status, created_at=v.created_at.isoformat() + "Z",
                           note=v.note, pages=len(v.preview_file_ids)) for v in reversed(d.versions)]
    out["thread"] = thread_payload(d, for_client=True)
    return jsonify(out)


@bp.post("/posts/<int:did>/messages")
@client_required
@rate_limit(120, 60, "c_message")
def message(did):
    d = _own_post(did)
    sv.add_message(d, "client", g.user.name, str(body().get("body", "")))
    sv.mark_thread_seen(d, "client")
    db.session.commit()
    return jsonify(thread=thread_payload(d, for_client=True)), 201


@bp.post("/posts/<int:did>/brief")
@client_required
@rate_limit(60, 60, "c_brief")
def send_brief(did):
    d = _own_post(did)
    sv.save_brief(d, request.form.get("text", ""), request.files.getlist("files"), g.user.name, request.form.get("base"))
    db.session.commit()
    return jsonify(post_dict(d, for_client=True)), 201


@bp.delete("/posts/<int:did>/brief/files/<int:fid>")
@client_required
def remove_brief_file(did, fid):
    d = _own_post(did)
    sv.remove_brief_file(d, fid)
    db.session.commit()
    return jsonify(post_dict(d, for_client=True))


@bp.get("/brief-files/<int:fid>")
@client_required
def brief_file(fid):
    f = get_or_404(ProjectFile, fid)
    d = next((x for x in sv.designs(f.project) if f.id in (x.brief_file_ids or [])), None) if f.project else None
    if f.kind != "client_ref" or not d or d.project.client_id != g.user.client_id:
        abort(404)
    resp = send_file(get_storage().local_path(f.storage_key), mimetype=f.mime, download_name=f.original_name)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.post("/payment/claim")
@client_required
@rate_limit(10, 60, "c_paid")
def claim_payment():
    sv.claim_plan_payment(_plan())
    db.session.commit()
    return jsonify(payment=sv.plan_payment(_plan()))


@bp.get("/versions/<int:vid>/pages/<int:page>")
@client_required
def preview(vid, page):
    v = get_or_404(ProjectVersion, vid)
    if not v.deliverable or v.project.kind != "retainer" or v.project.client_id != g.user.client_id:
        abort(404)
    if not 1 <= page <= len(v.preview_file_ids):
        abort(404)
    f = db.session.get(ProjectFile, v.preview_file_ids[page - 1])
    if not f or f.kind != "preview":
        abort(404)
    resp = send_file(get_storage().local_path(f.storage_key), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-cache"
    return resp


def _can_approve():
    plan = _plan()
    if not plan.client_approval:
        raise ApiError("Approvals are not used on your plan. Please tell us what you think in the chat.", 403, "approval_off")
    if not g.user.can_approve:
        raise ApiError("Your login can view the calendar but not approve. Ask your colleague who approves.", 403, "view_only")


@bp.post("/posts/<int:did>/approve")
@client_required
@rate_limit(60, 60, "c_approve")
def approve(did):
    _can_approve()
    d = _own_post(did)
    try:
        vid = int(body().get("version_id"))
    except (TypeError, ValueError):
        raise ApiError("Missing version.")
    sv.approve(d.project, vid)
    db.session.commit()
    return jsonify(post_dict(d, for_client=True))


@bp.post("/posts/<int:did>/revisions")
@client_required
@rate_limit(60, 60, "c_revision")
def revisions(did):
    _can_approve()
    d = _own_post(did)
    sv.request_revision(d.project, str(body().get("body", "")), d.id)
    db.session.commit()
    return jsonify(post_dict(d, for_client=True))
