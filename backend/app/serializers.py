"""JSON shapes. Admin and client views are separate so internal fields never leak to clients."""
import re

from flask import current_app

from .models import ActivityLog, Download, ProjectFile, db
from .services import (invoice_advances, plan_months, brief_files, brief_is_new, plan_payments, PAYMENT_REMINDER_ENABLED, plan_payment_status, post_is_fresh, post_thread, post_unread, client_updates, quote_mode, quote_split, calendar_items, invoice_closing, plan_progress, post_state, invoice_upi, active_token, client_link, complimentary_value, designs, get_settings, inr, quote_lines,
                       quote_advance, quote_payment, quote_totals, render_template)


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


def file_dict(f: ProjectFile):
    return dict(id=f.id, kind=f.kind, name=f.original_name, label=f.label, mime=f.mime, size=f.size,
                width=f.width, height=f.height, created_at=iso(f.created_at))


def client_dict(c, with_stats=False):
    d = dict(id=c.id, name=c.name, company=c.company, email=c.email, phone=c.phone,
             whatsapp=c.whatsapp, billing_address=c.billing_address, gstin=c.gstin, notes=c.notes,
             display_name=c.display_name, created_at=iso(c.created_at))
    if with_stats:
        ps = c.projects
        d["stats"] = dict(
            total=len(ps),
            active=sum(1 for p in ps if p.status != "completed"),
            paid=sum(1 for p in ps if p.is_paid),
            pending_amount=sum(p.invoice.total for p in ps if p.invoice and p.invoice.status == "issued"),
        )
    return d


def project_total(p):
    if p.invoice and p.invoice.status != "void":
        return p.invoice.total
    from .services import compute_totals, invoice_lines
    return compute_totals(invoice_lines(p), p.discount, p.gst_enabled, p.gst_rate_bp)["total"]


def last_activity(p):
    a = ActivityLog.query.filter_by(project_id=p.id).order_by(ActivityLog.id.desc()).first()
    return iso(a.created_at) if a else iso(p.updated_at)


def project_summary(p, staff=False):
    return dict(id=p.id, code=p.code, name=p.name, project_type=p.project_type, status=p.status,
                client=dict(id=p.client.id, name=p.client.display_name),
                amount=0 if staff else p.amount, total=0 if staff else project_total(p),
                due_date=p.due_date.isoformat() if p.due_date else None,
                last_activity=last_activity(p), created_at=iso(p.created_at),
                pending_payment=False if staff else any(x.status == "submitted" for x in p.payments))


_MONEY_WORDS = ("invoice", "payment", "advance", "paid", "₹", "rs.", "quote", "quotation", "price")
_HIDDEN_EVENTS = ("invoice", "payment", "advance", "downloaded", "link_")


def _staff_visible_activity(rows):
    """What an employee may read in the log: the work, never the money or the client's links."""
    return [a for a in rows if not a.event.startswith(_HIDDEN_EVENTS)
            and not any(w in a.message.lower() for w in _MONEY_WORDS)]


def invoice_dict(inv):
    if not inv:
        return None
    return dict(id=inv.id, number=inv.number, subtotal=inv.subtotal, discount=inv.discount,
                tax_rate_bp=inv.tax_rate_bp, tax=inv.tax, total=inv.total, status=inv.status,
                advance_paid=inv.advance_paid, amount_due=inv.amount_due, notes=inv.notes,
                issued_at=iso(inv.issued_at), paid_at=iso(inv.paid_at),
                items=[dict(description=i.description, quantity=i.quantity, unit_price=i.unit_price,
                            amount=i.amount, note=i.note) for i in inv.items])


def payment_dict(pay, admin=False):
    d = dict(id=pay.id, kind="final", amount=pay.amount, reference=pay.reference, status=pay.status,
             provider=pay.provider, submitted_at=iso(pay.submitted_at), decided_at=iso(pay.decided_at),
             admin_note=pay.admin_note)
    if admin:
        d.update(project=dict(id=pay.project.id, code=pay.project.code, name=pay.project.name,
                              client=pay.project.client.display_name),
                 invoice_number=pay.invoice.number, proof_file_id=pay.proof_file_id)
    return d


def advance_dict(a, admin=False):
    d = dict(id=a.id, kind="advance", amount=a.amount, reference=a.reference, status=a.status, provider="upi",
             submitted_at=iso(a.submitted_at), decided_at=iso(a.decided_at), admin_note=a.admin_note)
    if admin:
        p = a.project
        d.update(project=dict(id=p.id, code=p.code, name=p.name, client=p.client.display_name),
                 invoice_number=None, proof_file_id=a.proof_file_id)
    return d


def design_dict(d, versions):
    return dict(id=d.id, title=d.title, status=d.status, position=d.position, revisions_used=d.revisions_used,
                latest_version_id=d.latest_version.id if d.latest_version else None, versions=versions)


def advance_summary(p):
    return dict(amount=p.advance_amount, paid=p.advance_paid, status=p.advance_status,
                requested_at=iso(p.advance_requested_at), reminded_at=iso(p.advance_reminded_at),
                payments=[advance_dict(a, admin=True) for a in p.advances])


def version_dict(v, comments):
    return dict(id=v.id, number=v.label, deliverable_id=v.deliverable_id, status=v.status, note=v.note, created_at=iso(v.created_at),
                pages=len(v.preview_file_ids),
                comments=[dict(id=c.id, body=c.body, author=c.author, status=c.status,
                               is_extra=c.is_extra, created_at=iso(c.created_at))
                          for c in comments if c.version_id == v.id])


def token_dict(t):
    return dict(id=t.id, token=t.token, state=t.state, url=client_link(t), views=t.views,
                expires_at=iso(t.expires_at), revoked_at=iso(t.revoked_at),
                first_viewed_at=iso(t.first_viewed_at), last_viewed_at=iso(t.last_viewed_at),
                created_at=iso(t.created_at))


def project_detail(p, staff=False):
    files = {f.id: f for f in p.files}
    downloads = Download.query.filter_by(project_id=p.id).order_by(Download.id.desc()).all()
    activity = (ActivityLog.query.filter_by(project_id=p.id).order_by(ActivityLog.id.asc()).all())
    d = project_summary(p, staff)
    d.update(
        description=p.description, internal_notes=p.internal_notes, width=p.width, height=p.height,
        format=p.format, quantity=p.quantity, deliverable_types=p.deliverable_types,
        discount=p.discount, gst_enabled=p.gst_enabled, gst_rate_bp=p.gst_rate_bp,
        payment_terms=p.payment_terms, revisions_included=p.revisions_included,
        extra_revision_price=p.extra_revision_price, revisions_used=p.revisions_used,
        approved_version_id=p.approved_version_id, approved_at=iso(p.approved_at),
        advance=advance_summary(p),
        deliverables=[design_dict(x, [v.id for v in x.versions]) for x in designs(p)],
        paid_at=iso(p.paid_at), delivered_at=iso(p.delivered_at),
        delivery_expires_at=iso(p.delivery_expires_at), max_downloads=p.max_downloads,
        watermark=p.watermark, preview_rev=p.preview_rev,
        client=client_dict(p.client),
        versions=[dict(version_dict(v, p.comments), master=file_dict(files[v.master_file_id]))
                  for v in p.versions],
        finals=[file_dict(f) for f in p.final_files],
        review_links=[token_dict(t) for t in p.review_tokens],
        active_link=token_dict(active_token(p)) if active_token(p) else None,
        invoice=invoice_dict(p.invoice),
        payments=[payment_dict(x, admin=True) for x in p.payments],
        downloads=[dict(id=x.id, file=x.file.label or x.file.original_name, created_at=iso(x.created_at))
                   for x in downloads],
        activity=[dict(id=a.id, actor=a.actor, event=a.event, message=a.message,
                       created_at=iso(a.created_at)) for a in (_staff_visible_activity(activity) if staff else activity)],
    )
    if staff:  # no prices, contacts, payment records or client links
        d.update(discount=0, gst_enabled=False, gst_rate_bp=0, payment_terms=None, extra_revision_price=0,
                 advance=dict(amount=0, paid=0, status="none", requested_at=None, reminded_at=None, payments=[]),
                 review_links=[], active_link=None, invoice=None, payments=[], downloads=[],
                 client=dict(id=p.client.id, name=p.client.name, company=p.client.company, email=None, phone=None,
                             whatsapp=None, billing_address=None, gstin=None, notes=None,
                             display_name=p.client.display_name, created_at=iso(p.client.created_at)))
    return d


def brand_dict():
    s = get_settings()
    return dict(name=s["brand_name"], color=s["brand_color"], email=s["studio_email"],
                phone=s["studio_phone"], whatsapp=s["studio_whatsapp"] or s["studio_phone"],
                address=s["studio_address"], gstin=s["studio_gstin"],
                has_logo=bool(s["logo_file_id"]))


def client_project_view(p, rt):
    """Exactly what the client may see. No internal notes, no file keys, no master ids."""
    s = get_settings()
    pending = next((x for x in p.payments if x.status == "submitted"), None)
    last_rejected = next((x for x in p.payments if x.status == "rejected"), None)
    confirmed = next((x for x in p.payments if x.status == "confirmed"), None)
    d = dict(
        code=p.code, name=p.name, project_type=p.project_type, status=p.status,
        client_name=p.client.display_name, width=p.width, height=p.height, format=p.format,
        brand=brand_dict(),
        revisions_included=p.revisions_included, revisions_used=p.revisions_used,
        extra_revision_price=p.extra_revision_price,
        watermarked=p.watermark, preview_rev=p.preview_rev,
        deliverables=[design_dict(x, [version_dict(v, [c for c in p.comments if c.author == "client"]) for v in x.versions])
                      for x in designs(p)],
        advance=_client_advance(p, s),
        approved_version_id=p.approved_version_id, approved_at=iso(p.approved_at),
        link_expires_at=iso(rt.expires_at),
        invoice=None, payment=None, delivery=None,
    )
    if p.invoice and p.invoice.status in ("issued", "paid"):
        inv = invoice_dict(p.invoice)
        inv.update(bill_to=dict(name=p.client.display_name, contact=p.client.name,
                                address=p.client.billing_address, gstin=p.client.gstin),
                   payment_terms=p.payment_terms or s["payment_terms"], closing=invoice_closing(p.invoice))
        d["invoice"] = inv
        d["payment"] = dict(
            upi_id=s["upi_id"] or None, payee=s["upi_payee_name"] or s["brand_name"],
            has_qr=bool(s["upi_id"] or s["upi_qr_file_id"]),
            pending=payment_dict(pending) if pending else None,
            last_rejected=payment_dict(last_rejected) if (last_rejected and not pending and not confirmed) else None,
            confirmed=payment_dict(confirmed) if confirmed else None,
        )
    if p.is_paid:
        counts = dict(db.session.query(Download.file_id, db.func.count(Download.id))
                      .filter_by(project_id=p.id).group_by(Download.file_id).all())
        d["delivery"] = dict(
            delivered_at=iso(p.delivered_at), paid_at=iso(p.paid_at),
            expires_at=iso(p.delivery_expires_at), max_downloads=p.max_downloads,
            files=[dict(file_dict(f), downloads=counts.get(f.id, 0)) for f in p.final_files],
        )
    return d


# ---------- quotations ----------

def quote_link(q):
    return f"{current_app.config['PUBLIC_URL']}/q/{q.token}"


def quote_share(q):
    link = quote_link(q)
    t = quote_totals(q)
    num = re.sub(r"\D", "", q.client.whatsapp or q.client.phone or "")
    if len(num) == 10:
        num = "91" + num
    return dict(
        link=link, whatsapp_number=num or None,
        message=render_template(get_settings()["wa_quote"], client=q.client.name, project=q.title,
                                link=link, number=q.number, total=inr(t["total"]),
                                valid_until=q.valid_until.strftime("%d %b %Y")))


def quote_summary(q):
    return dict(
        id=q.id, number=q.number, title=q.title, status=q.effective_status,
        client=dict(id=q.client.id, name=q.client.display_name), total=quote_totals(q)["total"],
        valid_until=q.valid_until.isoformat(), created_at=iso(q.created_at), sent_at=iso(q.sent_at),
        views=q.views, last_viewed_at=iso(q.last_viewed_at), responded_at=iso(q.responded_at),
        project_code=q.project.code if q.project else None)


def _bill_to(q):
    c = q.client
    return dict(name=c.display_name, contact=c.name, address=c.billing_address, gstin=c.gstin)


def quote_document(q):
    """What the quote itself shows. Identical for you and for the client."""
    return dict(
        number=q.number, title=q.title, issued_at=iso(q.sent_at or q.created_at),
        valid_until=q.valid_until.isoformat(), bill_to=_bill_to(q), items=quote_lines(q),
        totals=dict(quote_totals(q), complimentary_value=complimentary_value(q), advance=quote_advance(q), **quote_split(q)),
        mode=quote_mode(q),
        revisions_included=q.revisions_included, advance_percent=q.advance_percent,
        notes=q.notes, closing=q.closing, terms=q.terms, payment=quote_payment(q), brand=brand_dict(),
        sections=q.sections or [], billing=q.billing, discount_label=q.discount_label, scope_first=q.scope_first, recurring_start=q.recurring_start)


def quote_detail(q):
    return dict(
        quote_summary(q), stored_status=q.status, document=quote_document(q), client_id=q.client_id,
        discount=q.discount, gst_enabled=q.gst_enabled, gst_rate_bp=q.gst_rate_bp,
        first_viewed_at=iso(q.first_viewed_at), response_note=q.response_note,
        plan_inclusions=q.plan_inclusions or [], has_plan=bool(q.client.plan),
        project=dict(id=q.project.id, code=q.project.code, name=q.project.name) if q.project else None,
        events=list(q.events or []), share=quote_share(q))


def client_quote_view(q):
    """Exactly what the client may see. No events, no internal ids."""
    return dict(
        document=quote_document(q), status=q.effective_status, client_name=q.client.display_name,
        can_respond=q.effective_status == "sent", responded_at=iso(q.responded_at),
        response_note=q.response_note)


def _client_advance(p, s):
    """What the client needs to know about the advance, or None when none was asked for."""
    if p.advance_amount <= 0 and not p.advance_paid:
        return None
    pending = next((a for a in p.advances if a.status == "submitted"), None)
    rejected = next((a for a in p.advances if a.status == "rejected"), None)
    return dict(amount=p.advance_amount, paid=p.advance_paid, due=max(0, p.advance_amount - p.advance_paid),
                status=p.advance_status, upi_id=s["upi_id"] or None, payee=s["upi_payee_name"] or s["brand_name"],
                has_qr=bool(s["upi_id"]), pending=advance_dict(pending) if pending else None,
                last_rejected=advance_dict(rejected) if (rejected and not pending and p.advance_status != "paid") else None)


def invoice_link(inv):
    rt = active_token(inv.project)
    return client_link(rt, "invoice") if rt else None


def invoice_document(inv):
    """What the invoice itself shows: used for the studio's preview and for the PDF and image downloads."""
    p, s = inv.project, get_settings()
    c = p.client
    return dict(
        number=inv.number, status=inv.status, issued_at=iso(inv.issued_at), paid_at=iso(inv.paid_at),
        project=dict(name=p.name, code=p.code, project_type=p.project_type),
        bill_to=dict(name=c.display_name, contact=c.name, address=c.billing_address, gstin=c.gstin),
        items=[dict(description=i.description, quantity=i.quantity, unit_price=i.unit_price, amount=i.amount,
                    note=i.note) for i in inv.items],
        totals=dict(subtotal=inv.subtotal, discount=inv.discount, tax_rate_bp=inv.tax_rate_bp, tax=inv.tax,
                    total=inv.total, advance_paid=inv.advance_paid, amount_due=inv.amount_due),
        advances=[dict(amount=a["amount"], reference=a["reference"], received_on=a["received_on"]) for a in invoice_advances(p)],
        notes=inv.notes, closing=invoice_closing(inv), payment_terms=p.payment_terms or s["payment_terms"],
        payment=invoice_upi(inv),
        brand=brand_dict())


def invoice_detail(inv):
    p = inv.project
    return dict(
        invoice_dict(inv), document=invoice_document(inv), gst_enabled=inv.tax_rate_bp > 0,
        gst_rate_bp=inv.tax_rate_bp or p.gst_rate_bp, link=invoice_link(inv),
        editable=inv.status == "issued" and not any(x.status == "submitted" for x in p.payments),
        advances=invoice_advances(p),
        project=dict(id=p.id, code=p.code, name=p.name, client=p.client.display_name),
        payments=[payment_dict(x) for x in p.payments if x.invoice_id == inv.id])


# ---------- monthly clients: the content calendar ----------

def _clock(dt):
    """A wall-clock time with no timezone, so the browser shows exactly what the team typed."""
    return dt.isoformat(timespec="minutes") if dt else None


def post_dict(d, for_client=False):
    p, v = d.project, d.latest_version
    ask = None
    if d.status == "changes_requested" and v:
        ask = next((c for c in reversed(p.comments) if c.kind == "revision" and c.version_id == v.id), None)
    out = dict(
        id=d.id, title=d.title, kind=d.kind, state=post_state(d), status=d.status, scheduled_at=_clock(d.scheduled_at),
        platforms=[x for x in (d.platforms or "").split(",") if x], caption=d.caption, media_url=d.media_url,
        posted_at=iso(d.posted_at), latest_version_id=v.id if v else None, version_number=v.label if v else None,
        pages=len(v.preview_file_ids) if v else 0, versions=len(d.versions), revisions_used=d.revisions_used,
        revisions_included=p.revisions_included, request=ask.body if ask else None,
        preview_rev=p.preview_rev, watermarked=p.watermark,
        unread=post_unread(d, "client" if for_client else "team"),
        brief=d.brief, brief_files=brief_files(d), brief_at=iso(d.brief_at), brief_by=d.brief_by)
    if for_client:
        out["fresh"] = post_is_fresh(d)
    else:
        out.update(project_id=p.id, brief_new=brief_is_new(d))
    return out


def thread_payload(d, for_client):
    """The chat on a post as one side sees it: `mine` marks that side's own messages."""
    out = []
    for r in post_thread(d):
        if r["type"] == "version":
            out.append(dict(type="version", id=r["id"], at=iso(r["at"]), number=r["number"], note=r["note"]))
        else:
            mine = r["team"] != for_client
            name = r["name"] or ("The studio" if r["team"] else "Client")
            out.append(dict(type="message", id=r["id"], at=iso(r["at"]), mine=mine, name=name, body=r["body"], changes=r["changes"]))
    return out


def calendar_payload(plan, ym, for_client=False):
    items = [post_dict(d, for_client) for d in calendar_items(plan, ym)]
    states = [i["state"] for i in items]
    return dict(
        month=ym, client=dict(id=plan.client.id, name=plan.client.display_name),
        plan=dict(id=plan.id, name=plan.name, active=plan.active, inclusions=plan.inclusions,
                  revisions_per_post=plan.revisions_per_post, client_approval=plan.client_approval),
        progress=plan_progress(plan, ym), items=items, months=plan_months(plan),
        counts={k: states.count(k) for k in ("planned", "brief", "review", "changes", "approved", "posted")})


def plan_detail(plan):
    """The owner's view of a plan, price included."""
    return dict(id=plan.id, name=plan.name, monthly_price=plan.monthly_price, active=plan.active,
                start_date=plan.start_date.isoformat() if plan.start_date else None,
                revisions_per_post=plan.revisions_per_post, inclusions=plan.inclusions, project_id=plan.project_id,
                client_approval=plan.client_approval, payment_reminder=plan.payment_reminder, payment=plan_payment_status(plan),
                payment_available=PAYMENT_REMINDER_ENABLED, payments=plan_payments(plan),
                invoice=dict(id=plan.project.invoice.id, number=plan.project.invoice.number) if plan.project and plan.project.invoice else None)


def login_dict(u):
    return dict(id=u.id, name=u.name, email=u.email, active=u.active, can_approve=u.can_approve,
                created_at=iso(u.created_at))
