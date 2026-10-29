"""Client portal API. The review token in the URL is the only credential; nothing else is trusted."""
import io

import segno
from flask import Blueprint, abort, jsonify, request, send_file

from .. import services as sv
from ..models import ProjectFile, ReviewToken, db
from ..security import ApiError, rate_limit, read_download, resolve_review_token, sign_download
from ..serializers import brand_dict, client_project_view
from ..storage import get_storage

bp = Blueprint("client", __name__, url_prefix="/api")


@bp.get("/r/<token>")
@rate_limit(120, 60, "portal")
def portal(token):
    rt = resolve_review_token(token)
    if not request.args.get("quiet"):  # background refreshes must not count as views
        sv.touch_link(rt)
        db.session.commit()
    return jsonify(client_project_view(rt.project, rt))


@bp.get("/r/<token>/versions/<int:vid>/pages/<int:page>")
@rate_limit(300, 60, "preview")
def preview(token, vid, page):
    rt = resolve_review_token(token)
    v = next((x for x in rt.project.versions if x.id == vid), None)  # must belong to THIS project
    if not v or not 1 <= page <= len(v.preview_file_ids):
        abort(404)
    f = db.session.get(ProjectFile, v.preview_file_ids[page - 1])
    if not f or f.kind != "preview" or f.project_id != rt.project_id:
        abort(404)
    resp = send_file(get_storage().local_path(f.storage_key), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Content-Disposition"] = "inline"
    return resp


@bp.post("/r/<token>/revisions")
@rate_limit(10, 60, "revision")
def revision(token):
    rt = resolve_review_token(token)
    data = request.get_json(silent=True) or {}
    design = data.get("deliverable_id")
    sv.request_revision(rt.project, str(data.get("body", "")), int(design) if str(design).isdigit() else None)
    db.session.commit()
    return jsonify(client_project_view(rt.project, rt))


@bp.post("/r/<token>/approve")
@rate_limit(10, 60, "approve")
def approve(token):
    rt = resolve_review_token(token)
    data = request.get_json(silent=True) or {}
    try:
        vid = int(data.get("version_id"))
    except (TypeError, ValueError):
        raise ApiError("Missing version.")
    sv.approve(rt.project, vid)
    db.session.commit()
    return jsonify(client_project_view(rt.project, rt))


def _upi_uri(p):
    s, inv = sv.get_settings(), p.invoice
    return sv.upi_uri(s["upi_id"], s["upi_payee_name"] or s["brand_name"], inv.amount_due, f"{p.code} {inv.number}")


def _advance_uri(p):
    s = sv.get_settings()
    return sv.upi_uri(s["upi_id"], s["upi_payee_name"] or s["brand_name"], p.advance_amount - p.advance_paid,
                      f"{p.code} advance")


@bp.get("/r/<token>/payment-qr.png")
def payment_qr(token):
    rt = resolve_review_token(token)
    p = rt.project
    inv = p.invoice
    if not inv or inv.status != "issued":
        abort(404)
    s = sv.get_settings()
    if s["upi_id"]:
        img = segno.make(_upi_uri(p), error="m")
        buf = io.BytesIO()
        img.save(buf, kind="png", scale=8, border=2)
        buf.seek(0)
        resp = send_file(buf, mimetype="image/png")
    elif s["upi_qr_file_id"]:
        f = db.session.get(ProjectFile, s["upi_qr_file_id"])
        if not f:
            abort(404)
        resp = send_file(get_storage().local_path(f.storage_key), mimetype=f.mime)
    else:
        abort(404)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/r/<token>/upi-uri")
def upi_uri(token):
    """For the 'Pay with UPI app' button on phones. `?for=advance` is the advance, otherwise the invoice."""
    rt = resolve_review_token(token)
    p = rt.project
    if not sv.setting("upi_id"):
        return jsonify(uri=None)
    if request.args.get("for") == "advance":
        return jsonify(uri=_advance_uri(p) if p.advance_status in ("requested", "submitted") else None)
    inv = p.invoice
    if not inv or inv.status != "issued":
        return jsonify(uri=None)
    return jsonify(uri=_upi_uri(p))


@bp.get("/r/<token>/advance-qr.png")
def advance_qr(token):
    p = resolve_review_token(token).project
    if p.advance_status not in ("requested", "submitted") or not sv.setting("upi_id"):
        abort(404)
    buf = io.BytesIO(sv.qr_png(_advance_uri(p), scale=8, border=2))
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.post("/r/<token>/advance")
@rate_limit(6, 60, "advance")
def submit_advance(token):
    rt = resolve_review_token(token)
    data = request.form if request.form or request.files else (request.get_json(silent=True) or {})
    sv.submit_advance(rt.project, str(data.get("reference", "")), request.files.get("proof"))
    db.session.commit()
    return jsonify(client_project_view(rt.project, rt))


@bp.post("/r/<token>/payments")
@rate_limit(6, 60, "payment")
def submit_payment(token):
    rt = resolve_review_token(token)
    sv.submit_payment(rt.project, request.form.get("reference", ""), request.files.get("proof"))
    db.session.commit()
    return jsonify(client_project_view(rt.project, rt))


@bp.post("/r/<token>/files/<int:fid>/link")
@rate_limit(30, 60, "dl_link")
def download_link(token, fid):
    """Step 1 of a download: authorise, then hand back a 5-minute signed URL."""
    rt = resolve_review_token(token)
    p = rt.project
    f = db.session.get(ProjectFile, fid)
    reason = sv.delivery_block_reason(p, f)
    if reason:
        raise ApiError(reason, 404 if reason == "File not found." else 403, "not_available")
    return jsonify(url=f"/api/dl/{sign_download(p.id, f.id, rt.id)}")


@bp.get("/dl/<signed>")
@rate_limit(30, 60, "dl")
def download(signed):
    """Step 2: re-check everything (link may have been revoked, payment reversed) and stream."""
    data = read_download(signed)
    rt = db.session.get(ReviewToken, data["t"])
    if not rt or rt.state != "active" or rt.project_id != data["p"]:
        raise ApiError("This link is no longer active.", 410, "revoked")
    p = rt.project
    f = db.session.get(ProjectFile, data["f"])
    reason = sv.delivery_block_reason(p, f)
    if reason:
        raise ApiError(reason, 403, "not_available")
    sv.record_download(p, f)
    db.session.commit()
    ext = f.original_name.rsplit(".", 1)[-1] if "." in f.original_name else "bin"
    name = f"{p.code}-{(f.label or 'final').replace(' ', '-')}.{ext}"
    resp = send_file(get_storage().local_path(f.storage_key), mimetype="application/octet-stream",
                     as_attachment=True, download_name=name)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/brand/logo")
def brand_logo():
    fid = sv.setting("logo_file_id")
    f = db.session.get(ProjectFile, fid) if fid else None
    if not f or f.kind != "brand":
        abort(404)
    return send_file(get_storage().local_path(f.storage_key), mimetype=f.mime, max_age=300)


@bp.get("/brand")
def brand():
    return jsonify(brand_dict())

