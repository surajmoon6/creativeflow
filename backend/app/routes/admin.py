import io
import re
from datetime import date, datetime

from flask import Blueprint, abort, g, jsonify, request, send_file

from .. import services as sv
from ..models import (STATUSES, ActivityLog, AdvancePayment, Client, Deliverable, Invoice, Notification, Payment,
                      Project, ProjectFile, ProjectVersion, Quote, ReviewToken, db, now)
from ..security import ApiError, admin_required, check_project_access, is_staff, team_required
from ..serializers import (advance_dict, client_dict, file_dict, invoice_detail, invoice_dict, iso, payment_dict, project_detail,
                           project_summary, quote_summary)
from ..storage import get_storage

bp = Blueprint("admin", __name__, url_prefix="/api")


def body():
    return request.get_json(silent=True) or {}


def get_or_404(model, id_):
    obj = db.session.get(model, id_)
    if not obj:
        raise ApiError("Not found.", 404, "not_found")
    return obj


def _str(d, key, maxlen, required=False, label=None):
    v = d.get(key)
    v = str(v).strip() if v is not None else ""
    if required and not v:
        raise ApiError(f"{label or key.replace('_', ' ').capitalize()} is required.")
    if len(v) > maxlen:
        raise ApiError(f"{label or key} is too long.")
    return v or None


def _int(d, key, default=0, lo=0, hi=10**10, label=None):
    v = d.get(key, default)
    if v in (None, ""):
        return default
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ApiError(f"{label or key.replace('_', ' ').capitalize()} must be a number.")
    if not lo <= v <= hi:
        raise ApiError(f"{label or key.replace('_', ' ').capitalize()} is out of range.")
    return v


def _date(d, key):
    v = d.get(key)
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ApiError("Invalid date.")


# ---------- dashboard ----------

@bp.get("/dashboard")
@admin_required
def dashboard():
    projects = Project.query.all()
    by = lambda *st: sum(1 for p in projects if p.status in st)  # noqa: E731
    month_start = datetime(now().year, now().month, 1)
    revenue = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0)).filter(
        Payment.status == "confirmed", Payment.decided_at >= month_start).scalar()
    revenue += db.session.query(db.func.coalesce(db.func.sum(AdvancePayment.amount), 0)).filter(
        AdvancePayment.status == "confirmed", AdvancePayment.decided_at >= month_start).scalar()
    outstanding = db.session.query(db.func.coalesce(db.func.sum(Invoice.total - Invoice.advance_paid), 0)).filter(
        Invoice.status == "issued").scalar()
    recent = Project.query.order_by(Project.updated_at.desc()).limit(8).all()
    needs = []
    for p in projects:
        if p.status == "revision_requested":
            needs.append(dict(project=project_summary(p), reason="Client requested changes"))
        elif any(x.status == "submitted" for x in p.payments):
            needs.append(dict(project=project_summary(p), reason="Payment to confirm"))
        elif p.status == "approved":
            needs.append(dict(project=project_summary(p), reason="Approved — add final files"))
        elif p.status == "finalization":
            needs.append(dict(project=project_summary(p), reason="Ready to issue invoice"))
    reminder_days = int(sv.setting("advance_reminder_days"))
    for p in projects:  # the advance is its own to-do, alongside whatever stage the work is in
        st = p.advance_status
        if st == "submitted":
            needs.append(dict(project=project_summary(p), reason="Advance to confirm"))
        elif st == "requested" and p.advance_requested_at and (now() - (p.advance_reminded_at or p.advance_requested_at)).days >= reminder_days:
            needs.append(dict(project=project_summary(p), reason=f"Advance of {sv.inr(p.advance_amount)} not paid. Send a reminder"))
    today = date.today()
    quotes = []
    for q in Quote.query.filter(Quote.status.in_(["sent", "accepted"])).order_by(Quote.id.desc()).all():
        days_left = (q.valid_until - today).days
        quiet_days = (now() - (q.last_viewed_at or q.sent_at or q.created_at)).days
        if q.status == "accepted":
            reason = None if q.project_id else "Accepted. Create the project"
        elif days_left < 0:
            reason = None
        elif days_left <= 3:
            reason = "Expires today" if days_left == 0 else f"Expires in {days_left} day{'s' if days_left > 1 else ''}"
        elif quiet_days >= 2:
            reason = "Viewed, no reply yet" if q.views else "Not opened yet"
        else:
            reason = None
        if reason:
            quotes.append(dict(quote_summary(q), reason=reason))
    return jsonify(
        quotes=quotes,
        stats=dict(
            active=sum(1 for p in projects if p.status != "completed"),
            in_review=by("review"),
            changes_requested=by("revision_requested"),
            payment_pending=by("payment_pending"),
            paid=by("paid"),
            delivered=by("delivered", "completed"),
            completed=by("completed"),
            projects_this_month=sum(1 for p in projects if p.created_at >= month_start),
            revenue_month=revenue,
            outstanding=outstanding,
        ),
        needs_attention=needs,
        recent=[project_summary(p) for p in recent],
    )


# ---------- clients ----------

def _client_fields(d):
    name = _str(d, "name", 160, required=True, label="Client name")
    email = _str(d, "email", 255)
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ApiError("Enter a valid email address.")
    gstin = _str(d, "gstin", 20)
    if gstin and not re.match(r"^[0-9A-Z]{15}$", gstin.upper()):
        raise ApiError("GSTIN should be 15 characters.")
    return dict(name=name, company=_str(d, "company", 160), email=email,
                phone=_str(d, "phone", 30), whatsapp=_str(d, "whatsapp", 30),
                billing_address=_str(d, "billing_address", 1000),
                gstin=gstin.upper() if gstin else None, notes=_str(d, "notes", 4000))


@bp.get("/clients")
@admin_required
def list_clients():
    return jsonify([client_dict(c, with_stats=True) for c in Client.query.order_by(Client.name).all()])


@bp.post("/clients")
@admin_required
def create_client():
    c = Client(**_client_fields(body()))
    db.session.add(c)
    db.session.commit()
    return jsonify(client_dict(c, with_stats=True)), 201


@bp.get("/clients/<int:cid>")
@admin_required
def get_client(cid):
    c = get_or_404(Client, cid)
    d = client_dict(c, with_stats=True)
    d["projects"] = [project_summary(p) for p in c.projects]
    return jsonify(d)


@bp.put("/clients/<int:cid>")
@admin_required
def update_client(cid):
    c = get_or_404(Client, cid)
    for k, v in _client_fields(body()).items():
        setattr(c, k, v)
    db.session.commit()
    return jsonify(client_dict(c, with_stats=True))


# ---------- projects ----------

def _project_fields(d, partial=False):
    f = dict(
        name=_str(d, "name", 200, required=True, label="Project name"),
        project_type=_str(d, "project_type", 80, required=True, label="Project type"),
        description=_str(d, "description", 4000),
        internal_notes=_str(d, "internal_notes", 4000),
        width=_int(d, "width", None, 1, 50000) if d.get("width") not in (None, "") else None,
        height=_int(d, "height", None, 1, 50000) if d.get("height") not in (None, "") else None,
        format=_str(d, "format", 60),
        quantity=_int(d, "quantity", 1, 1, 1000),
        deliverable_types=_str(d, "deliverable_types", 120),
        amount=_int(d, "amount", 0, 0, 10**11, "Amount"),
        discount=_int(d, "discount", 0, 0, 10**11, "Discount"),
        gst_enabled=bool(d.get("gst_enabled")),
        gst_rate_bp=_int(d, "gst_rate_bp", sv.setting("gst_rate_bp_default"), 0, 5000, "GST rate"),
        due_date=_date(d, "due_date"),
        payment_terms=_str(d, "payment_terms", 255),
        revisions_included=_int(d, "revisions_included", sv.setting("default_revisions"), 0, 50,
                                "Included revisions"),
        extra_revision_price=_int(d, "extra_revision_price", 0, 0, 10**10, "Additional revision price"),
    )
    if f["discount"] > f["amount"]:
        raise ApiError("Discount can't be more than the project amount.")
    return f


@bp.get("/projects")
@team_required
def list_projects():
    q = Project.query.filter(Project.kind != "retainer")  # a monthly client's calendar lives under Calendar
    if is_staff():
        ids = [c.id for c in g.user.clients]
        q = q.filter(Project.client_id.in_(ids or [0]))
    status = request.args.get("status")
    if status in STATUSES:
        q = q.filter_by(status=status)
    if request.args.get("client_id"):
        q = q.filter_by(client_id=_int(request.args, "client_id", 0, 0, label="Client"))
    return jsonify([project_summary(p, is_staff()) for p in q.order_by(Project.updated_at.desc()).all()])


@bp.post("/projects")
@admin_required
def create_project():
    d = body()
    client = get_or_404(Client, _int(d, "client_id", 0, 1, label="Client"))
    p = Project(client=client, code=sv.next_project_code(), **_project_fields(d))
    db.session.add(p)
    db.session.flush()
    sv.log_activity(p, "admin", "created", "Project created")
    db.session.commit()
    return jsonify(project_detail(p)), 201


def _share(p):
    s = sv.get_settings()
    rt = sv.active_token(p)
    out = {}
    for kind, page, tpl in (("review", "", "wa_review"), ("payment", "invoice", "wa_payment"),
                            ("delivery", "delivery", "wa_delivery"), ("advance", "advance", "wa_advance")):
        link = sv.client_link(rt, page)
        out[kind] = dict(link=link, message=sv.render_template(
            s[tpl], client=p.client.name, project=p.name, link=link or "",
            amount=sv.inr(max(0, p.advance_amount - p.advance_paid))) if link else None)
    num = re.sub(r"\D", "", p.client.whatsapp or p.client.phone or "")
    if len(num) == 10:
        num = "91" + num
    out["whatsapp_number"] = num or None
    return out


@bp.get("/projects/<int:pid>")
@team_required
def get_project(pid):
    p = get_or_404(Project, pid)
    check_project_access(p)
    if is_staff():
        none = dict(link=None, message=None)
        return jsonify(dict(project_detail(p, staff=True),
                            share=dict(review=none, payment=none, delivery=none, advance=none, whatsapp_number=None)))
    d = project_detail(p)
    d["share"] = _share(p)
    return jsonify(d)


@bp.put("/projects/<int:pid>")
@admin_required
def update_project(pid):
    p = get_or_404(Project, pid)
    d = body()
    fields = _project_fields(d)
    commercial = {"amount", "discount", "gst_enabled", "gst_rate_bp", "revisions_included",
                  "extra_revision_price"}
    changed = any(getattr(p, k) != fields[k] for k in commercial)
    if p.is_paid and changed:
        raise ApiError("Commercial details can't change after payment.", 409)
    if p.status == "payment_pending" and changed:
        raise ApiError("An invoice has been issued. Reopen the project to change the price, "
                       "then issue the invoice again.", 409)
    new_client = _int(d, "client_id", 0, 0, label="Client")
    if new_client and new_client != p.client_id:
        if p.status not in ("brief_received", "in_design"):
            raise ApiError("The client can't be changed once review has started.", 409)
        p.client = get_or_404(Client, new_client)
    for k, v in fields.items():
        setattr(p, k, v)
    sv.log_activity(p, "admin", "updated", "Project details updated")
    db.session.commit()
    return get_project(pid)


@bp.post("/projects/<int:pid>/actions/<action>")
@admin_required
def project_action(pid, action):
    p = get_or_404(Project, pid)
    actions = {"start_design": sv.start_design, "reopen": sv.reopen, "complete": sv.complete}
    if action not in actions:
        abort(404)
    actions[action](p)
    db.session.commit()
    return get_project(pid)


@bp.post("/projects/<int:pid>/versions")
@team_required
def upload_version(pid):
    p = get_or_404(Project, pid)
    check_project_access(p)
    data, ext, name = sv.read_upload(request.files.get("file"), sv.MASTER_EXTS)
    design = _int(request.form, "deliverable_id", 0, 0, label="Design") or None
    sv.add_version(p, data, ext, name, request.form.get("note"), design=design)
    db.session.commit()
    return get_project(pid)


# ---------- designs and advance ----------

@bp.post("/projects/<int:pid>/deliverables")
@team_required
def add_design(pid):
    p = get_or_404(Project, pid)
    check_project_access(p)
    sv.add_design(p, body().get("title"))
    db.session.commit()
    return get_project(pid)


@bp.put("/deliverables/<int:did>")
@team_required
def rename_design(did):
    d = get_or_404(Deliverable, did)
    check_project_access(d.project)
    sv.rename_design(d, body().get("title"))
    db.session.commit()
    return get_project(d.project_id)


@bp.delete("/deliverables/<int:did>")
@team_required
def remove_design(did):
    d = get_or_404(Deliverable, did)
    check_project_access(d.project)
    pid = d.project_id
    sv.remove_design(d)
    db.session.commit()
    return get_project(pid)


@bp.post("/deliverables/<int:did>/approve")
@admin_required
def approve_design_for_client(did):
    d = get_or_404(Deliverable, did)
    sv.approve_for_client(d)
    db.session.commit()
    return get_project(d.project_id)


@bp.post("/deliverables/<int:did>/reopen")
@admin_required
def reopen_design(did):
    d = get_or_404(Deliverable, did)
    sv.reopen_design(d)
    db.session.commit()
    return get_project(d.project_id)


@bp.post("/projects/<int:pid>/advance")
@admin_required
def set_advance(pid):
    p = get_or_404(Project, pid)
    sv.set_advance(p, _int(body(), "amount", 0, 0, 10**11, "Advance"))
    db.session.commit()
    return get_project(pid)


@bp.post("/projects/<int:pid>/advance/received")
@admin_required
def advance_received(pid):
    p = get_or_404(Project, pid)
    sv.record_advance_received(p, body().get("note"))
    db.session.commit()
    return get_project(pid)


@bp.post("/projects/<int:pid>/advance/remind")
@admin_required
def advance_remind(pid):
    p = get_or_404(Project, pid)
    sv.remind_advance(p)
    db.session.commit()
    return get_project(pid)


@bp.post("/advances/<int:aid>/<decision>")
@admin_required
def decide_advance(aid, decision):
    a = get_or_404(AdvancePayment, aid)
    if decision == "confirm":
        sv.confirm_advance(a)
    elif decision == "reject":
        sv.reject_advance(a, body().get("note"))
    else:
        abort(404)
    db.session.commit()
    return jsonify(advance_dict(a, admin=True))


@bp.post("/projects/<int:pid>/watermark")
@admin_required
def set_watermark(pid):
    p = get_or_404(Project, pid)
    enabled = body().get("enabled")
    if not isinstance(enabled, bool):
        raise ApiError("Send enabled as true or false.")
    sv.set_watermark(p, enabled)
    db.session.commit()
    return get_project(pid)


@bp.post("/projects/<int:pid>/finals")
@team_required
def upload_final(pid):
    p = get_or_404(Project, pid)
    check_project_access(p)
    data, ext, name = sv.read_upload(request.files.get("file"), sv.FINAL_EXTS)
    sv.add_final(p, data, ext, name, request.form.get("label"))
    db.session.commit()
    return get_project(pid)


@bp.delete("/files/<int:fid>")
@team_required
def delete_final(fid):
    f = get_or_404(ProjectFile, fid)
    check_project_access(f.project)
    if f.kind != "final":
        raise ApiError("Only final files can be removed.", 409)
    pid = f.project_id
    sv.remove_final(f)
    db.session.commit()
    return get_project(pid)


@bp.post("/projects/<int:pid>/review-links")
@admin_required
def new_review_link(pid):
    p = get_or_404(Project, pid)
    d = body()
    if d.get("revoke_existing", True):
        for t in p.review_tokens:
            if t.state == "active":
                sv.revoke_link(t)
    sv.create_review_link(p, d.get("expiry", "never"), d.get("expires_at"))
    db.session.commit()
    return get_project(pid)


@bp.post("/review-links/<int:tid>/revoke")
@admin_required
def revoke_review_link(tid):
    t = get_or_404(ReviewToken, tid)
    sv.revoke_link(t)
    db.session.commit()
    return get_project(t.project_id)


@bp.post("/projects/<int:pid>/invoice")
@admin_required
def issue_invoice(pid):
    p = get_or_404(Project, pid)
    sv.issue_invoice(p, include_extra=body().get("include_extra", True),
                     use_approved=bool(body().get("use_approved_files")))
    db.session.commit()
    return get_project(pid)


@bp.get("/projects/<int:pid>/invoice-preview")
@admin_required
def invoice_preview(pid):
    p = get_or_404(Project, pid)
    lines = sv.invoice_lines(p)
    return jsonify(dict(items=lines, **sv.compute_totals(lines, p.discount, p.gst_enabled, p.gst_rate_bp)))


@bp.post("/payments/<int:pay_id>/<decision>")
@admin_required
def decide_payment(pay_id, decision):
    pay = get_or_404(Payment, pay_id)
    if decision == "confirm":
        sv.confirm_payment(pay)
    elif decision == "reject":
        sv.reject_payment(pay, body().get("note"))
    else:
        abort(404)
    db.session.commit()
    return jsonify(payment_dict(pay, admin=True))


# ---------- admin file access (previews, masters, finals, proofs) ----------

@bp.get("/admin/files/<int:fid>")
@team_required
def admin_file(fid):
    f = get_or_404(ProjectFile, fid)
    if is_staff():  # design work yes; payment proofs, brand files and anything outside their clients no
        if not f.project or f.kind not in ("master", "preview", "final", "client_ref"):
            raise ApiError("Not found.", 404, "not_found")
        check_project_access(f.project)
    inline = request.args.get("inline") == "1" and f.mime in ("image/png", "image/jpeg", "image/webp")
    resp = send_file(get_storage().local_path(f.storage_key), mimetype=f.mime if inline else
                     "application/octet-stream", as_attachment=not inline, download_name=f.original_name)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/admin/versions/<int:vid>/pages/<int:page>")
@team_required
def admin_preview(vid, page):
    v = get_or_404(ProjectVersion, vid)
    check_project_access(v.project)
    if not 1 <= page <= len(v.preview_file_ids):
        abort(404)
    f = get_or_404(ProjectFile, v.preview_file_ids[page - 1])
    resp = send_file(get_storage().local_path(f.storage_key), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-cache"  # revalidate: the watermark can be switched at any time
    return resp


# ---------- lists ----------

@bp.get("/invoices")
@admin_required
def list_invoices():
    out = []
    for inv in Invoice.query.order_by(Invoice.id.desc()).all():
        d = invoice_dict(inv)
        d["project"] = dict(id=inv.project.id, code=inv.project.code, name=inv.project.name,
                            client=inv.project.client.display_name)
        out.append(d)
    return jsonify(out)


MAX_INVOICE_ITEMS = 30


def _invoice_fields(d):
    raw = d.get("items")
    if not isinstance(raw, list) or not raw:
        raise ApiError("Add at least one line.")
    if len(raw) > MAX_INVOICE_ITEMS:
        raise ApiError(f"An invoice can have up to {MAX_INVOICE_ITEMS} lines.")
    items = []
    for r in raw:
        r = r if isinstance(r, dict) else {}
        qty = _int(r, "quantity", 1, 1, 10000, "Quantity")
        price = _int(r, "unit_price", 0, 0, 10**10, "Price")
        items.append(dict(description=_str(r, "description", 255, required=True, label="Line description"),
                          quantity=qty, unit_price=price, amount=qty * price, note=_str(r, "note", 60)))
    subtotal = sum(i["amount"] for i in items)
    discount = _int(d, "discount", 0, 0, 10**11, "Discount")
    if discount > subtotal:
        raise ApiError("Discount can't be more than the invoice subtotal.")
    return dict(items=items, discount=discount, gst_enabled=bool(d.get("gst_enabled")),
                gst_rate_bp=_int(d, "gst_rate_bp", sv.setting("gst_rate_bp_default"), 0, 5000, "GST rate"),
                notes=_str(d, "notes", 2000))


@bp.get("/invoices/<int:iid>")
@admin_required
def get_invoice(iid):
    return jsonify(invoice_detail(get_or_404(Invoice, iid)))


@bp.put("/invoices/<int:iid>")
@admin_required
def edit_invoice(iid):
    inv = get_or_404(Invoice, iid)
    sv.edit_invoice(inv, _invoice_fields(body()))
    db.session.commit()
    return jsonify(invoice_detail(inv))


@bp.get("/invoices/<int:iid>/download")
@admin_required
def download_invoice(iid):
    from ..invoice_render import filename, render_pdf, render_png
    inv = get_or_404(Invoice, iid)
    fmt = (request.args.get("format") or "pdf").lower()
    if fmt not in ("pdf", "png"):
        raise ApiError("Choose pdf or png.")
    data = render_pdf(inv) if fmt == "pdf" else render_png(inv)
    resp = send_file(io.BytesIO(data), mimetype="application/pdf" if fmt == "pdf" else "image/png",
                     as_attachment=True, download_name=filename(inv, fmt))
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/payments")
@admin_required
def list_payments():
    q, a = Payment.query, AdvancePayment.query
    if request.args.get("status"):
        q, a = q.filter_by(status=request.args["status"]), a.filter_by(status=request.args["status"])
    rows = [payment_dict(x, admin=True) for x in q.all()] + [advance_dict(x, admin=True) for x in a.all()]
    return jsonify(sorted(rows, key=lambda r: r["submitted_at"], reverse=True))


@bp.get("/files")
@admin_required
def list_files():
    q = ProjectFile.query.filter(ProjectFile.kind.in_(["master", "final"]))
    out = []
    for f in q.order_by(ProjectFile.id.desc()).limit(500).all():
        d = file_dict(f)
        d["project"] = dict(id=f.project.id, code=f.project.code, name=f.project.name,
                            client=f.project.client.display_name) if f.project else None
        out.append(d)
    return jsonify(out)


@bp.get("/activity")
@admin_required
def list_activity():
    limit = _int(request.args, "limit", 200, 1, 1000, label="Limit")
    q = ActivityLog.query
    if request.args.get("project_id"):
        q = q.filter_by(project_id=_int(request.args, "project_id", 0, 0, label="Project"))
    rows = q.order_by(ActivityLog.id.desc()).limit(limit).all()
    return jsonify([dict(id=a.id, actor=a.actor, event=a.event, message=a.message,
                         created_at=iso(a.created_at),
                         project=dict(id=a.project.id, code=a.project.code, name=a.project.name)
                         if a.project else None) for a in rows])


@bp.get("/notifications")
@admin_required
def list_notifications():
    rows = Notification.query.order_by(Notification.id.desc()).limit(50).all()
    return jsonify(dict(
        unread=Notification.query.filter_by(read_at=None).count(),
        items=[dict(id=n.id, event=n.event, message=n.message, read=bool(n.read_at),
                    created_at=iso(n.created_at), project_id=n.project_id, quote_id=n.quote_id,
                    client_id=n.project.client_id if n.project else None) for n in rows]))


@bp.post("/notifications/read")
@admin_required
def read_notifications():
    Notification.query.filter_by(read_at=None).update({"read_at": now()})
    db.session.commit()
    return jsonify(ok=True)


# ---------- settings ----------

SETTING_RULES = {
    "brand_name": (str, 1, 80), "brand_color": (str, 4, 7), "studio_email": (str, 0, 255),
    "studio_phone": (str, 0, 30), "studio_whatsapp": (str, 0, 30), "studio_address": (str, 0, 500), "studio_gstin": (str, 0, 20),
    "currency": (str, 3, 3), "gst_enabled_default": (bool, None, None),
    "gst_rate_bp_default": (int, 0, 5000), "default_revisions": (int, 0, 50),
    "default_extra_revision_price": (int, 0, 10**10), "payment_terms": (str, 0, 255),
    "preview_max_px": (int, 300, 2400), "preview_scale": (float, 0.2, 0.95),
    "watermark_text": (str, 1, 60), "watermark_opacity": (float, 0.08, 0.85),
    "review_link_expiry": (str, 2, 5), "delivery_days": (int, 0, 3650), "max_downloads": (int, 0, 1000),
    "project_prefix": (str, 1, 10), "project_next": (int, 1, 10**8),
    "invoice_prefix": (str, 1, 10), "invoice_next": (int, 1, 10**8),
    "upi_id": (str, 0, 80), "upi_payee_name": (str, 0, 80),
    "wa_review": (str, 10, 1500), "wa_payment": (str, 10, 1500), "wa_delivery": (str, 10, 1500),
    "wa_quote": (str, 10, 1500), "quote_prefix": (str, 1, 10), "quote_next": (int, 1, 10**8),
    "quote_valid_days": (int, 1, 365), "quote_terms": (str, 0, 2000), "quote_closing": (str, 0, 1500),
    "invoice_closing": (str, 0, 1500), "invoice_closing_paid": (str, 0, 1500),
    "wa_advance": (str, 10, 1500), "quote_advance_percent": (int, 0, 100), "advance_reminder_days": (int, 1, 60),
}


@bp.get("/settings")
@admin_required
def get_settings():
    return jsonify(sv.get_settings())


@bp.put("/settings")
@admin_required
def update_settings():
    d = body()
    for key, val in d.items():
        if key not in SETTING_RULES:
            continue
        typ, lo, hi = SETTING_RULES[key]
        try:
            val = typ(val) if typ is not bool else bool(val)
        except (TypeError, ValueError):
            raise ApiError(f"Invalid value for {key}.")
        if typ is str:
            val = val.strip()
            if not lo <= len(val) <= hi:
                raise ApiError(f"{key.replace('_', ' ').capitalize()} has an invalid length.")
        elif typ in (int, float) and not lo <= val <= hi:
            raise ApiError(f"{key.replace('_', ' ').capitalize()} is out of range.")
        if key == "brand_color" and not re.match(r"^#[0-9a-fA-F]{6}$", val):
            raise ApiError("Brand color must be a hex color like #4F46E5.")
        if key == "review_link_expiry" and val not in sv.EXPIRY:
            raise ApiError("Invalid review link expiry.")
        if key == "upi_id" and val and not re.match(r"^[\w.\-]{2,}@[A-Za-z]{2,}$", val):
            raise ApiError("UPI ID should look like name@bank.")
        if key.startswith("wa_") and "{link}" not in val:
            raise ApiError("WhatsApp templates must include {link}.")
        sv.set_setting(key, val)
    db.session.commit()
    return jsonify(sv.get_settings())


@bp.post("/settings/<kind>")
@admin_required
def upload_setting_image(kind):
    if kind not in ("logo", "upi_qr"):
        abort(404)
    data, ext, name = sv.read_upload(request.files.get("file"), sv.LOGO_EXTS)
    if len(data) > 5 * 1024 * 1024:
        raise ApiError("Image must be under 5 MB.")
    f = sv.store_file(None, "brand", data, ext, name)
    sv.set_setting("logo_file_id" if kind == "logo" else "upi_qr_file_id", f.id)
    db.session.commit()
    return jsonify(sv.get_settings())


@bp.delete("/settings/<kind>")
@admin_required
def clear_setting_image(kind):
    if kind not in ("logo", "upi_qr"):
        abort(404)
    sv.set_setting("logo_file_id" if kind == "logo" else "upi_qr_file_id", None)
    db.session.commit()
    return jsonify(sv.get_settings())
