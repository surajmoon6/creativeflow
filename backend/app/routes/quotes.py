"""Quotations: the studio builds and shares them; the client opens a private link and accepts or declines."""
from datetime import date, timedelta

import io

from flask import Blueprint, jsonify, request, send_file

from .. import services as sv
from ..models import Client, Quote, db
from ..security import ApiError, admin_required, rate_limit
from ..quote_render import filename, render_pdf, render_png
from ..serializers import client_quote_view, quote_detail, quote_summary
from .admin import _date, _int, _str, body, get_or_404

bp = Blueprint("quotes", __name__, url_prefix="/api")
public = Blueprint("quotes_public", __name__, url_prefix="/api")

MAX_ITEMS = 30


def _fields(d, existing: Quote | None = None):
    client = get_or_404(Client, _int(d, "client_id", 0, 1, label="Client"))
    raw = d.get("items")
    if not isinstance(raw, list) or not raw:
        raise ApiError("Add at least one item.")
    if len(raw) > MAX_ITEMS:
        raise ApiError(f"A quote can have up to {MAX_ITEMS} items.")
    items = []
    for r in raw:
        r = r if isinstance(r, dict) else {}
        items.append(dict(description=_str(r, "description", 255, required=True, label="Item description"),
                          quantity=_int(r, "quantity", 1, 1, 10000, "Quantity"),
                          unit_price=_int(r, "unit_price", 0, 0, 10**10, "Item price"),
                          complimentary=bool(r.get("complimentary")), detail=_str(r, "detail", 2000),
                          period="monthly" if r.get("period") == "monthly" else "once",
                          list_price=_int(r, "list_price", 0, 0, 10**10, "Standard price") or None))
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items if not i["complimentary"])
    discount = _int(d, "discount", 0, 0, 10**11, "Discount")
    if discount > subtotal:
        raise ApiError("Discount can't be more than the quote total.")
    valid = _date(d, "valid_until") or date.today() + timedelta(days=int(sv.setting("quote_valid_days")))
    if valid < date.today() and not (existing and existing.valid_until == valid):
        raise ApiError("The valid-until date must be today or later.")
    return dict(
        client=client, title=_str(d, "title", 200, required=True, label="Title"), items=items, discount=discount,
        gst_enabled=bool(d.get("gst_enabled")),
        gst_rate_bp=_int(d, "gst_rate_bp", sv.setting("gst_rate_bp_default"), 0, 5000, "GST rate"),
        notes=_str(d, "notes", 2000),
        closing=_str(d, "closing", 1500) if "closing" in d else sv.default_closing(client.name),
        terms=_str(d, "terms", 4000) if "terms" in d else (sv.setting("quote_terms") or None),
        revisions_included=_int(d, "revisions_included", int(sv.setting("default_revisions")), 0, 50, "Revisions"),
        advance_percent=_int(d, "advance_percent", int(sv.setting("quote_advance_percent")), 0, 100, "Advance"),
        valid_until=valid, sections=sv.clean_sections(d.get("sections")),
        billing="monthly" if d.get("billing") == "monthly" else "once", scope_first=d.get("scope_first") is not False,
        recurring_start="launch" if d.get("recurring_start") == "launch" else "now",
        discount_label=_str(d, "discount_label", 80), plan_inclusions=sv.clean_inclusions(d.get("plan_inclusions")))


def _download(q: Quote):
    fmt = (request.args.get("format") or "pdf").lower()
    if fmt not in ("pdf", "png"):
        raise ApiError("Choose pdf or png.")
    data = render_pdf(q) if fmt == "pdf" else render_png(q)
    resp = send_file(io.BytesIO(data), mimetype="application/pdf" if fmt == "pdf" else "image/png",
                     as_attachment=True, download_name=filename(q, fmt))
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ---------- studio side ----------

@bp.get("/quotes")
@admin_required
def list_quotes():
    rows = Quote.query.order_by(Quote.id.desc()).all()
    return jsonify([quote_summary(q) for q in rows])


@bp.post("/quotes")
@admin_required
def create_quote():
    q = sv.create_quote(_fields(body()))
    db.session.commit()
    return jsonify(quote_detail(q)), 201


@bp.get("/quotes/<int:qid>")
@admin_required
def get_quote(qid):
    return jsonify(quote_detail(get_or_404(Quote, qid)))


@bp.put("/quotes/<int:qid>")
@admin_required
def update_quote(qid):
    q = get_or_404(Quote, qid)
    sv.update_quote(q, _fields(body(), q))
    db.session.commit()
    return jsonify(quote_detail(q))


@bp.delete("/quotes/<int:qid>")
@admin_required
def delete_quote(qid):
    q = get_or_404(Quote, qid)
    if q.status != "draft":
        raise ApiError("Only a draft can be deleted. Once sent, the client may already have it.", 409)
    db.session.delete(q)
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/quotes/<int:qid>/download")
@admin_required
def download_quote(qid):
    return _download(get_or_404(Quote, qid))


@bp.post("/quotes/<int:qid>/send")
@admin_required
def send_quote(qid):
    q = get_or_404(Quote, qid)
    sv.send_quote(q)
    db.session.commit()
    return jsonify(quote_detail(q))


@bp.post("/quotes/<int:qid>/status")
@admin_required
def set_quote_status(qid):
    """Record an answer the client gave outside the link (a call, a WhatsApp reply), or reopen a declined quote."""
    q = get_or_404(Quote, qid)
    action = body().get("action")
    if action in ("accept", "decline"):
        sv.respond_quote(q, action == "accept", body().get("note"), by_client=False)
    elif action == "reopen":
        sv.reopen_quote(q)
    else:
        raise ApiError("Unknown action.")
    db.session.commit()
    return jsonify(quote_detail(q))


@bp.post("/quotes/<int:qid>/duplicate")
@admin_required
def duplicate_quote(qid):
    c = sv.duplicate_quote(get_or_404(Quote, qid))
    db.session.commit()
    return jsonify(quote_detail(c)), 201


@bp.post("/quotes/<int:qid>/start-plan")
@admin_required
def start_plan(qid):
    q = get_or_404(Quote, qid)
    sv.start_plan_from_quote(q)
    db.session.commit()
    return jsonify(quote_detail(q))


@bp.post("/quotes/<int:qid>/convert")
@admin_required
def convert_quote(qid):
    q = get_or_404(Quote, qid)
    d = body()
    p = sv.convert_quote(q, revisions=_int(d, "revisions_included", q.revisions_included, 0, 50, "Revisions"),
                         advance_percent=_int(d, "advance_percent", q.advance_percent, 0, 100, "Advance"))
    db.session.commit()
    return jsonify(dict(quote=quote_detail(q), project_id=p.id))


# ---------- client side: the token is the only credential ----------

def _by_token(token) -> Quote:
    q = Quote.query.filter_by(token=token).first() if token and len(token) <= 64 else None
    if not q or q.status == "draft":
        raise ApiError("This link is not valid. Please check the link or contact the studio.", 404, "invalid")
    return q


@public.get("/q/<token>")
@rate_limit(120, 60, "quote")
def view_quote(token):
    q = _by_token(token)
    if not request.args.get("quiet"):  # background refreshes are not views
        sv.touch_quote(q)
        db.session.commit()
    return jsonify(client_quote_view(q))


@public.get("/q/<token>/download")
@rate_limit(30, 60, "quote_download")
def download_public_quote(token):
    return _download(_by_token(token))


@public.post("/q/<token>/accept")
@rate_limit(10, 60, "quote_reply")
def accept_quote(token):
    q = _by_token(token)
    sv.respond_quote(q, True, str((request.get_json(silent=True) or {}).get("note", "")))
    db.session.commit()
    return jsonify(client_quote_view(q))


@public.post("/q/<token>/decline")
@rate_limit(10, 60, "quote_reply")
def decline_quote(token):
    q = _by_token(token)
    sv.respond_quote(q, False, str((request.get_json(silent=True) or {}).get("note", "")))
    db.session.commit()
    return jsonify(client_quote_view(q))
