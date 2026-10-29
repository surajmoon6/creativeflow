"""Business logic: settings, files, versions, workflow transitions, invoices, payments, logging."""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import smtplib
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote as urlquote
from email.message import EmailMessage

from flask import current_app, g, has_request_context

from . import preview as pv
from werkzeug.security import generate_password_hash

from .models import (ActivityLog, AdvancePayment, Client, Comment, Deliverable, Download, Invoice, InvoiceItem,
                     Notification, Payment, Plan, Project, ProjectFile, ProjectVersion, Quote, QuoteItem, ReviewToken,
                     Setting, User, db, now)
from .security import ApiError, new_token
from .storage import get_storage

log = logging.getLogger("creativeflow")

# ---------- settings ----------

DEFAULT_SETTINGS = {
    "brand_name": "CreativeFlow Studio",
    "brand_color": "#4F46E5",
    "logo_file_id": None,
    "studio_email": "",
    "studio_phone": "",
    "studio_whatsapp": "",
    "studio_address": "",
    "studio_gstin": "",
    "currency": "INR",
    "gst_enabled_default": False,
    "gst_rate_bp_default": 1800,
    "default_revisions": 4,
    "default_extra_revision_price": 50000,
    "payment_terms": "Payable on approval of the final creative.",
    "preview_max_px": 1800,
    "preview_scale": 0.9,
    "watermark_text": "CLIENT REVIEW COPY",
    "watermark_opacity": 0.32,
    "review_link_expiry": "never",  # 24h | 3d | 7d | 30d | never
    "delivery_days": 30,  # 0 = never expires
    "max_downloads": 0,  # per file, 0 = unlimited
    "project_prefix": "CF-",
    "project_next": 1042,
    "invoice_prefix": "INV-",
    "invoice_next": 1042,
    "upi_id": "",
    "upi_payee_name": "",
    "upi_qr_file_id": None,
    "quote_advance_percent": 50,
    "advance_reminder_days": 2,
    "wa_advance": "Hi {client},\n\nA gentle reminder: please pay the advance of {amount} for {project} so we can "
                  "keep your work moving.\n\nYou can pay here in a minute:\n\n{link}\n\nThank you!",
    "quote_prefix": "QUO-",
    "quote_next": 1001,
    "quote_valid_days": 15,
    "quote_terms": "50% advance to start the work, balance on approval of the final creative.\n"
                   "The quoted number of revisions is included; extra revisions are charged separately.\n"
                   "Final files are delivered after full payment.",
    "invoice_closing": "Thank you for trusting {studio} with your creative work, {client}! It was a pleasure "
                       "bringing your ideas to life. Your final files are released the moment your payment is "
                       "confirmed. Any question about this invoice? Just message us, we're always happy to help.",
    "invoice_closing_paid": "Payment received. Thank you, {client}! It was a joy creating this with you. If you "
                            "loved the work, a kind word or a recommendation means the world to a creative studio "
                            "like ours. We can't wait to make something great together again.",
    "quote_closing": "Thank you for considering {studio}, {client}! We're excited about this project and will give "
                     "it our full attention, from the first draft to the final files. Accept this quote and we'll "
                     "get started right away. Your complimentary extras are included. We'd love to work with you.",
    "wa_quote": "Hi {client},\n\nThank you for your interest! Here is your quotation {number} for {project}: "
                "{total}, valid until {valid_until}.\n\nOpen it, accept with one tap, and we'll start right "
                "away:\n\n{link}\n\nLooking forward to working with you!",
    "wa_review": "Hi {client},\n\nYour creative for {project} is ready for review.\n\n"
                 "Please review the design and share any feedback through the project link:\n\n"
                 "{link}\n\nThank you.",
    "wa_payment": "Hi {client},\n\nThe creative has been approved and the project is now ready for "
                  "final delivery.\n\nYou can view the project summary and complete the final "
                  "delivery process here:\n\n{link}",
    "wa_delivery": "Hi {client},\n\nPayment has been received successfully.\n\nYour final creative "
                   "files are now available:\n\n{link}\n\nThank you.",
}
PUBLIC_SETTING_KEYS = {"brand_name", "brand_color", "studio_email", "studio_phone", "studio_whatsapp", "currency"}


def get_settings() -> dict:
    stored = {s.key: s.value for s in Setting.query.all()}
    return {k: stored.get(k, v) for k, v in DEFAULT_SETTINGS.items()}


def setting(key):
    s = db.session.get(Setting, key)
    return s.value if s else DEFAULT_SETTINGS[key]


def set_setting(key, value):
    s = db.session.get(Setting, key)
    if s:
        s.value = value
    else:
        db.session.add(Setting(key=key, value=value))


def _next_counter(prefix_key, next_key):
    n = setting(next_key)
    set_setting(next_key, n + 1)
    return f"{setting(prefix_key)}{n}"


def next_project_code():
    while True:
        code = _next_counter("project_prefix", "project_next")
        if not Project.query.filter_by(code=code).first():
            return code


def next_invoice_number():
    while True:
        num = _next_counter("invoice_prefix", "invoice_next")
        if not Invoice.query.filter_by(number=num).first():
            return num


# ---------- activity / notifications / email ----------

def log_activity(project, actor, event, message):
    who = g.get("user") if has_request_context() else None
    if who is not None and who.role == "staff":  # the owner can see which employee did what
        message = f"{message} (by {who.name})"
    db.session.add(ActivityLog(project_id=project.id if project else None, actor=actor,
                               event=event, message=message[:255]))


def notify_admin(project, event, message):
    db.session.add(Notification(project_id=project.id if project else None, event=event,
                                message=message[:255]))
    send_email(setting("studio_email"), f"[{project.code}] {message}", message)


def send_email(to, subject, body):
    """SMTP if configured via env, otherwise logged. Never breaks the workflow."""
    if not to:
        return
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.info("EMAIL (not sent, SMTP not configured) to=%s subject=%s", to, subject)
        return
    try:
        msg = EmailMessage()
        msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", ""))
        msg["To"], msg["Subject"] = to, subject
        msg.set_content(body)
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except Exception:  # noqa: BLE001
        log.exception("email failed")


def client_link(rt: ReviewToken | None, page=""):
    if not rt:
        return None
    base = current_app.config["PUBLIC_URL"]
    return f"{base}/r/{rt.token}{('/' + page) if page else ''}"


def email_client(project, subject, intro, page=""):
    rt = active_token(project)
    if project.client.email and rt:
        send_email(project.client.email, subject,
                   f"Hi {project.client.name},\n\n{intro}\n\n{client_link(rt, page)}\n\n"
                   f"{setting('brand_name')}")


# ---------- files ----------

MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
    "gif": "image/gif", "pdf": "application/pdf", "svg": "image/svg+xml", "zip": "application/zip",
    "mp4": "video/mp4", "mov": "video/quicktime", "psd": "image/vnd.adobe.photoshop",
    "ai": "application/postscript", "eps": "application/postscript", "tif": "image/tiff",
    "tiff": "image/tiff",
}
MASTER_EXTS = pv.PREVIEWABLE_EXTS
FINAL_EXTS = set(MIME)
PROOF_EXTS = {"png", "jpg", "jpeg", "webp", "pdf"}
LOGO_EXTS = {"png", "jpg", "jpeg", "webp"}
MAGIC = {
    "png": [b"\x89PNG\r\n\x1a\n"], "jpg": [b"\xff\xd8\xff"], "jpeg": [b"\xff\xd8\xff"],
    "pdf": [b"%PDF-"], "gif": [b"GIF87a", b"GIF89a"], "zip": [b"PK\x03\x04"],
    "webp": [b"RIFF"],
}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def safe_name(filename: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "", os.path.basename(filename or "")).strip() or "file"
    return name[:120]


def read_upload(upload, allowed: set) -> tuple[bytes, str, str]:
    if not upload or not upload.filename:
        raise ApiError("Choose a file to upload.")
    ext = _ext(upload.filename)
    if ext not in allowed:
        raise ApiError(f"Unsupported file type. Allowed: {', '.join(sorted(allowed)).upper()}.")
    data = upload.read()
    if not data:
        raise ApiError("The file is empty.")
    sigs = MAGIC.get(ext)
    if sigs and not any(data.startswith(s) for s in sigs):
        raise ApiError("The file contents don't match its extension.")
    if ext == "webp" and data[8:12] != b"WEBP":
        raise ApiError("The file contents don't match its extension.")
    return data, ext, safe_name(upload.filename)


def store_file(project, kind, data, ext, original_name, label=None, size_hint=True) -> ProjectFile:
    folder = project.code if project else "studio"
    key = f"projects/{folder}/{kind}/{uuid.uuid4().hex}.{ext}"
    get_storage().save_bytes(key, data)
    w, h = pv.image_size(data, ext) if size_hint else (None, None)
    f = ProjectFile(project=project, kind=kind, storage_key=key,
                    original_name=original_name, label=label, mime=MIME.get(ext, "application/octet-stream"),
                    size=len(data), width=w, height=h)
    db.session.add(f)
    db.session.flush()
    return f


# ---------- review links ----------

EXPIRY = {"24h": timedelta(hours=24), "3d": timedelta(days=3), "7d": timedelta(days=7),
          "30d": timedelta(days=30), "never": None}


def active_token(project) -> ReviewToken | None:
    return next((t for t in project.review_tokens if t.state == "active"), None)


def create_review_link(project, expiry="never", expires_at=None) -> ReviewToken:
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", ""))
        except ValueError:
            raise ApiError("Invalid expiry date.")
        if exp <= now():
            raise ApiError("Expiry date must be in the future.")
    else:
        if expiry not in EXPIRY:
            raise ApiError("Invalid expiry option.")
        exp = now() + EXPIRY[expiry] if EXPIRY[expiry] else None
    rt = ReviewToken(project=project, token=new_token(), expires_at=exp)
    db.session.add(rt)
    db.session.flush()
    log_activity(project, "admin", "link_created", "Review link created")
    return rt


def revoke_link(rt: ReviewToken):
    if not rt.revoked_at:
        rt.revoked_at = now()
        log_activity(rt.project, "admin", "link_revoked", "Review link revoked")


def touch_link(rt: ReviewToken):
    """Count views without invasive tracking: no IPs, no fingerprints."""
    t = now()
    p = rt.project
    if not rt.first_viewed_at:
        rt.first_viewed_at = t
        log_activity(p, "client", "link_opened", "Client opened the review link")
    elif rt.last_viewed_at and t - rt.last_viewed_at > timedelta(minutes=30):
        log_activity(p, "client", "viewed", "Client viewed the project")
    rt.views += 1
    rt.last_viewed_at = t


# ---------- versions ----------

LOCKED_FOR_VERSIONS = {"approved", "finalization", "payment_pending", "paid", "delivered", "completed"}


def render_previews(project: Project, data: bytes, ext: str):
    """Previews for one master file, honouring the project's watermark switch."""
    s = get_settings()
    lines = [s["watermark_text"] or "CLIENT REVIEW COPY",
             f"{project.client.display_name.upper()} · #{project.code}", s["brand_name"].upper()]
    try:
        return pv.generate_previews(data, ext, lines, max_px=int(s["preview_max_px"]),
                                    scale=float(s["preview_scale"]), opacity=float(s["watermark_opacity"]),
                                    watermark=project.watermark)
    except pv.PreviewError as e:
        raise ApiError(str(e))


def rerender_previews(project: Project):
    """Rebuild every preview of a project from its masters with the current settings, in place."""
    storage = get_storage()
    rendered = []  # render everything before touching disk, so a failure can't leave a mix
    for v in project.versions:
        with storage.open(v.master.storage_key) as fh:
            data = fh.read()
        pages = render_previews(project, data, _ext(v.master.storage_key))
        rendered += [(db.session.get(ProjectFile, fid), page) for fid, page in zip(v.preview_file_ids, pages)]
    for f, (jpg, w, h) in rendered:
        storage.save_bytes(f.storage_key, jpg)
        f.size, f.width, f.height = len(jpg), w, h
    project.preview_rev += 1


def set_watermark(project: Project, enabled: bool):
    """Turn the client-preview watermark on or off, re-rendering every existing preview from its master.

    Previews are rewritten in place (same storage keys), so links and version history are untouched.
    """
    if project.watermark == enabled:
        return
    project.watermark = enabled
    rerender_previews(project)
    log_activity(project, "admin", "watermark",
                 "Watermark turned on — client previews are watermarked" if enabled
                 else "Watermark turned off — client sees clean previews")


# ---------- designs: the separate pieces of work inside one project ----------

PRE_APPROVAL = {"brief_received", "in_design", "review", "revision_requested", "approved"}


def designs(project: Project) -> list[Deliverable]:
    return Deliverable.query.filter_by(project_id=project.id).order_by(Deliverable.position, Deliverable.id).all()


def pick_design(project: Project, design_id: int | None = None, *, for_upload=True) -> Deliverable:
    """The design an action is about. With one design (or one obvious candidate) it need not be named."""
    ds = designs(project)
    if design_id is not None:
        d = next((x for x in ds if x.id == design_id), None)
        if not d:
            raise ApiError("That design isn't part of this project.", 404)
        return d
    if not ds:
        raise ApiError("Add a design to this project first.", 409)
    if len(ds) == 1:
        return ds[0]
    if for_upload:  # the studio: if only one design is waiting for a version, that is the one
        pool = [x for x in ds if x.status in ("pending", "changes_requested")]
        if len(pool) == 1:
            return pool[0]
    raise ApiError("Choose which design this is for.")  # the client always names it, so nothing is guessed


def sync_project_status(project: Project):
    """Before approval the project's status simply summarises its designs."""
    if project.kind == "retainer":  # a monthly client's calendar never "completes": posts come and go all month
        return
    if project.status not in PRE_APPROVAL:
        return
    st = [d.status for d in designs(project)]
    if not st or all(x == "pending" for x in st):
        new = project.status if project.status in ("brief_received", "in_design") else "in_design"
    elif "changes_requested" in st:
        new = "revision_requested"
    elif "review" in st:
        new = "review"
    elif all(x == "approved" for x in st):
        new = "finalization" if project.final_files else "approved"
    else:
        new = "in_design"
    project.status = new


def add_design(project: Project, title: str) -> Deliverable:
    title = (title or "").strip()
    if not title:
        raise ApiError("Give the design a name.")
    if len(title) > 200:
        raise ApiError("That name is too long.")
    if project.status not in PRE_APPROVAL:
        raise ApiError("Reopen the project before adding another design.", 409)
    ds = designs(project)
    d = Deliverable(project_id=project.id, title=title, position=(ds[-1].position + 1) if ds else 0, status="pending")
    db.session.add(d)
    db.session.flush()
    log_activity(project, "admin", "design_added", f"Design added: {title}")
    sync_project_status(project)
    return d


def rename_design(d: Deliverable, title: str):
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise ApiError("Give the design a name (up to 200 characters).")
    d.title = title


def remove_design(d: Deliverable):
    p = d.project
    if d.versions:
        raise ApiError("This design already has versions, so it can't be removed.", 409)
    if len(designs(p)) <= 1:
        raise ApiError("A project needs at least one design.", 409)
    if p.status not in PRE_APPROVAL:
        raise ApiError("Reopen the project before removing a design.", 409)
    log_activity(p, "admin", "design_removed", f"Design removed: {d.title}")
    db.session.delete(d)
    db.session.flush()
    sync_project_status(p)


def reopen_design(d: Deliverable):
    """Take one approved design back to work, voiding an unpaid invoice if the project had moved on."""
    p = d.project
    if p.is_paid:
        raise ApiError("This project is paid. Add a new design or project for extra work.", 409)
    if any(x.status == "submitted" for x in p.payments):
        raise ApiError("A payment is awaiting your confirmation. Resolve it first.", 409)
    if d.status != "approved":
        raise ApiError("Only an approved design can be reopened.", 409)
    for v in d.versions:
        if v.status == "approved":
            v.status = "superseded"
    d.status = "pending"
    if p.status in ("approved", "finalization", "payment_pending"):
        if p.invoice:
            p.invoice.status = "void"
        p.approved_version_id, p.approved_at = None, None
        p.status = "in_design"
    sync_project_status(p)
    log_activity(p, "admin", "reopened", f"Reopened for changes: {d.title}" if len(designs(p)) > 1 else "Project reopened for changes")


def add_version(project: Project, data: bytes, ext: str, name: str, note: str | None,
                design: Deliverable | int | None = None) -> ProjectVersion:
    if project.status in LOCKED_FOR_VERSIONS:
        raise ApiError("This creative is already approved. Reopen the project to upload a new version.", 409)
    d = design if isinstance(design, Deliverable) else pick_design(project, design)
    if d.project_id != project.id:
        raise ApiError("That design isn't part of this project.", 404)
    if d.status == "approved":
        raise ApiError("This design is already approved. Reopen it to upload a new version.", 409)
    multi = len(designs(project)) > 1
    pages = render_previews(project, data, ext)

    number = max((v.number for v in project.versions), default=0) + 1
    seq = max((v.label for v in d.versions), default=0) + 1
    master = store_file(project, "master", data, ext, name)
    preview_ids = []
    for i, (jpg, w, h) in enumerate(pages, 1):
        f = store_file(project, "preview", jpg, "jpg", f"v{number}-p{i}.jpg", size_hint=False)
        f.width, f.height = w, h
        preview_ids.append(f.id)

    mine = {v.id for v in d.versions}
    for v in d.versions:
        if v.status == "review":
            v.status = "superseded"
    for c in project.comments:
        if c.status == "open" and c.version_id in mine:
            c.status = "resolved"
    v = ProjectVersion(project=project, deliverable_id=d.id, number=number, seq=seq, master_file_id=master.id,
                       preview_file_ids=preview_ids, note=(note or "").strip()[:2000] or None)
    db.session.add(v)
    d.status = "review"
    db.session.flush()
    sync_project_status(project)
    of = f" of {d.title}" if multi else ""
    log_activity(project, "admin", "version_uploaded", f"Version {seq}{of} uploaded")
    log_activity(project, "system", "preview_generated",
                 f"Protected preview generated ({len(pages)} page{'s' if len(pages) > 1 else ''})")
    if not active_token(project):
        create_review_link(project, setting("review_link_expiry"))
    what = f"{d.title} ({project.name})" if multi else project.name
    email_client(project, f"{what} is ready for review", f"Version {seq} of {what} is ready for your review.")
    return v


# ---------- client actions ----------

APPROVED_MSG = "Creative has already been approved. Contact the studio if additional changes are required."


def request_revision(project: Project, body: str, design_id: int | None = None) -> Comment:
    body = (body or "").strip()
    if project.status in LOCKED_FOR_VERSIONS:
        raise ApiError(APPROVED_MSG, 409, "already_approved")
    d = pick_design(project, design_id, for_upload=False)
    if d.status == "approved":
        raise ApiError(APPROVED_MSG, 409, "already_approved")
    if d.status != "review" or not d.latest_version:
        raise ApiError("The studio is preparing the next version. You'll get a link when it's ready.",
                       409, "not_in_review")
    if len(body) < 3:
        raise ApiError("Please describe what you'd like changed.")
    if len(body) > 4000:
        raise ApiError("Please keep the request under 4000 characters.")
    v = d.latest_version
    extra = d.revisions_used >= project.revisions_included
    c = Comment(project=project, version_id=v.id, author="client", kind="revision", body=body,
                is_extra=extra)
    db.session.add(c)
    v.status = "changes_requested"
    d.status = "changes_requested"
    sync_project_status(project)
    multi = len(designs(project)) > 1
    of = f" of {d.title}" if multi else ""
    log_activity(project, "client", "revision_requested",
                 f"Revision requested on version {v.label}{of}" + (" (additional revision)" if extra else ""))
    notify_admin(project, "revision_requested",
                 f"{project.client.display_name} requested changes on {d.title if multi else project.name}")
    return c


def approve(project: Project, version_id: int):
    if project.status in LOCKED_FOR_VERSIONS:
        raise ApiError("This creative is already approved.", 409, "already_approved")
    v = next((x for x in project.versions if x.id == version_id), None)
    if not v or not v.deliverable:
        raise ApiError("There is no version awaiting approval.", 409, "not_in_review")
    d = v.deliverable
    if d.status != "review":
        raise ApiError("There is no version awaiting approval.", 409, "not_in_review")
    if d.latest_version.id != v.id:
        raise ApiError("A newer version is available. Please review the latest version.", 409, "stale")
    _mark_approved(project, v, d, "client", f"Client approved version {v.label}{{of}}", notify=True)


def approve_for_client(d: Deliverable):
    """The client agreed outside the tool (a call, WhatsApp). Approve the design for them, quietly.

    Same result as their own approval, but nobody is notified and the client's page simply shows it as approved.
    Only the studio's private activity log records that it was done by the studio.
    """
    project = d.project
    if project.status in LOCKED_FOR_VERSIONS:
        raise ApiError("This creative is already approved.", 409, "already_approved")
    v = d.latest_version
    if not v or d.status not in ("review", "changes_requested"):
        raise ApiError("There is no version of this design to approve.", 409, "not_in_review")
    _mark_approved(project, v, d, "admin",
                   f"Studio approved version {v.label}{{of}} for the client (not shown to the client)", notify=False)


def _mark_approved(project: Project, v, d, actor: str, message: str, notify: bool):
    v.status = "approved"
    d.status = "approved"
    sync_project_status(project)
    multi = len(designs(project)) > 1
    of = f" of {d.title}" if multi else ""
    log_activity(project, actor, "approved" if actor == "client" else "approved_by_studio", message.format(of=of))
    last = project.status in ("approved", "finalization")  # that was the last design
    if last:
        project.approved_version_id = v.id
        project.approved_at = now()
    if notify:
        who = project.client.display_name
        notify_admin(project, "approved", f"{who} approved " + (f"all designs of {project.name}" if last and multi
                                                              else project.name if last else d.title))


# ---------- admin workflow ----------

def add_final(project: Project, data, ext, name, label) -> ProjectFile:
    if project.status not in ("approved", "finalization", "payment_pending", "paid", "delivered", "completed"):
        raise ApiError("Final files can be added once the client approves the creative.", 409)
    f = store_file(project, "final", data, ext, name, label=(label or "").strip()[:120] or None)
    if project.status == "approved":
        project.status = "finalization"
    log_activity(project, "admin", "final_uploaded", f"Final file added: {f.label or name}")
    return f


def remove_final(f: ProjectFile):
    p = f.project
    if p.is_paid:
        raise ApiError("Final files can't be removed after payment. Add a corrected file instead.", 409)
    if p.status == "payment_pending" and len(p.final_files) == 1:
        raise ApiError("The invoice is out and this is the only final file. Add the replacement first, "
                       "or reopen the project.", 409)
    get_storage().delete(f.storage_key)
    log_activity(p, "admin", "final_removed", f"Final file removed: {f.label or f.original_name}")
    db.session.delete(f)
    db.session.flush()
    if p.status == "finalization" and not p.final_files:
        p.status = "approved"


def invoice_lines(project: Project):
    lines = [dict(description=f"{project.project_type} — {project.name}", quantity=1,
                  unit_price=project.amount, amount=project.amount, note=None)]
    if project.revisions_included:
        lines.append(dict(description=f"Revisions ({project.revisions_included} included)",
                          quantity=1, unit_price=0, amount=0, note="Included"))
    extra = sum(1 for c in project.comments if c.kind == "revision" and c.is_extra)
    if extra and project.extra_revision_price:
        lines.append(dict(description="Additional revisions", quantity=extra,
                          unit_price=project.extra_revision_price,
                          amount=extra * project.extra_revision_price, note=None))
    return lines


def compute_totals(lines, discount, gst_enabled, rate_bp):
    subtotal = sum(l["amount"] for l in lines)
    discount = min(max(discount, 0), subtotal)
    taxable = subtotal - discount
    rate = rate_bp if gst_enabled else 0
    tax = (taxable * rate + 5000) // 10000  # round half up to the paisa
    return dict(subtotal=subtotal, discount=discount, tax_rate_bp=rate, tax=tax, total=taxable + tax)


def use_approved_files_as_finals(project: Project) -> int:
    """Copy each approved design's own file in as a final file, for studios whose uploads are already production quality."""
    n = 0
    for d in designs(project):
        v = next((x for x in reversed(d.versions) if x.status == "approved"), None)
        if not v or not v.master:
            continue
        with get_storage().open(v.master.storage_key) as fh:
            data = fh.read()
        add_final(project, data, _ext(v.master.storage_key), v.master.original_name, d.title)
        n += 1
    return n


def issue_invoice(project: Project, include_extra=True, use_approved=False) -> Invoice:
    if project.status not in ("approved", "finalization", "payment_pending"):
        raise ApiError("An invoice can be issued after the client approves the creative.", 409)
    if use_approved and not project.final_files:
        use_approved_files_as_finals(project)
    if not project.final_files:
        raise ApiError("Attach at least one final file before issuing the invoice.", 409)
    if any(p.status == "submitted" for p in project.payments):
        raise ApiError("A payment is awaiting your confirmation. Confirm or reject it first.", 409)
    lines = invoice_lines(project)
    if not include_extra:
        lines = [l for l in lines if l["description"] != "Additional revisions"]
    totals = compute_totals(lines, project.discount, project.gst_enabled, project.gst_rate_bp)
    inv = project.invoice
    if inv is None:
        inv = Invoice(project=project, number=next_invoice_number(), **totals)
        db.session.add(inv)
    else:
        for k, val in totals.items():
            setattr(inv, k, val)
        inv.items.clear()
        inv.issued_at = now()
    inv.status = "issued"
    inv.advance_paid = min(project.advance_paid, inv.total)
    for l in lines:
        inv.items.append(InvoiceItem(**l))
    project.status = "payment_pending"
    db.session.flush()
    log_activity(project, "admin", "invoice_generated", f"Invoice {inv.number} generated")
    if _settle_if_covered(project, inv):
        return inv
    email_client(project, f"Invoice {inv.number} — {project.name}",
                 "Your approved project is ready for final delivery. You can view the invoice and "
                 "complete the project here:", "invoice")
    return inv


def invoice_advances(project: Project) -> list[dict]:
    """The money the studio has confirmed on a project, oldest first: shown on its invoice with the payment screenshot."""
    rows = sorted((a for a in project.advances if a.status == "confirmed"), key=lambda a: (a.decided_at, a.id))
    return [dict(id=a.id, amount=a.amount, reference=a.reference, note=a.admin_note,
                 received_on=a.decided_at.date().isoformat(), proof_file_id=a.proof_file_id) for a in rows]


def issue_plan_invoice(plan: Plan) -> Invoice:
    """An invoice for a monthly client, taken from their accepted quote, with what they have already paid taken off."""
    project = plan.project
    if project.invoice:
        raise ApiError("This client already has an invoice.", 409)
    q = Quote.query.filter_by(client_id=plan.client_id, status="accepted", billing="monthly").order_by(Quote.id.desc()).first()
    lines = totals = None
    if q:
        quoted = quote_totals(q)
        lines = [dict(description=l["description"][:255], quantity=l["quantity"], unit_price=l["unit_price"], amount=l["amount"],
                      note="Included" if l["complimentary"] else None) for l in quote_lines(q) if l["amount"] or l["complimentary"]]
        if quoted["total"] == plan.monthly_price and sum(l["amount"] for l in lines) == quoted["subtotal"]:
            totals = {k: quoted[k] for k in ("subtotal", "discount", "tax_rate_bp", "tax", "total")}
    if totals is None:  # no matching quote: one line at the plan's price
        lines = [dict(description=plan.name, quantity=1, unit_price=plan.monthly_price, amount=plan.monthly_price, note=None)]
        totals = compute_totals(lines, 0, False, 0)
    project.payment_terms = "Balance payable towards the monthly package."
    inv = Invoice(project=project, number=next_invoice_number(), advance_paid=min(project.advance_paid, totals["total"]), **totals)
    inv.items = [InvoiceItem(**l) for l in lines]
    if inv.amount_due == 0:
        inv.status, inv.paid_at = "paid", now()
    db.session.add(inv)
    db.session.flush()
    log_activity(project, "admin", "invoice_generated", f"Invoice {inv.number} generated")
    return inv


def _settle_if_covered(project: Project, inv: Invoice) -> bool:
    """When the advance already covers the whole invoice, it is paid: release the files."""
    if inv.amount_due != 0:
        return False
    t = now()
    inv.status, inv.paid_at = "paid", t
    project.status, project.paid_at = "paid", t
    release_delivery(project, t)
    log_activity(project, "system", "payment_verified", "Paid in full by the advance")
    email_client(project, f"Paid in full — {project.name}",
                 "Your payment is complete. Your final creative files are now available:", "delivery")
    return True


def edit_invoice(inv: Invoice, f: dict) -> Invoice:
    """Change what an issued invoice says: lines, discount, GST and notes. A paid invoice is a record and stays as it is."""
    project = inv.project
    if inv.status != "issued":
        raise ApiError("This invoice is already paid, so it can't be edited.", 409)
    if any(p.status == "submitted" for p in project.payments):
        raise ApiError("A payment is waiting for your confirmation. Confirm or reject it first, then edit.", 409)
    totals = compute_totals(f["items"], f["discount"], f["gst_enabled"], f["gst_rate_bp"])
    if totals["total"] < inv.advance_paid:
        raise ApiError(f"The client already paid {inr(inv.advance_paid)} as an advance, so the total can't be lower than that.", 409)
    for k, val in totals.items():
        setattr(inv, k, val)
    inv.items.clear()
    for l in f["items"]:
        inv.items.append(InvoiceItem(**l))
    inv.notes = f["notes"]
    db.session.flush()
    log_activity(project, "admin", "invoice_edited", f"Invoice {inv.number} edited, total now {inr(inv.total)}")
    _settle_if_covered(project, inv)
    return inv


def invoice_upi(inv: Invoice) -> dict | None:
    """UPI details to pay what is still due on an invoice, or None when it is paid or UPI isn't set up."""
    s = get_settings()
    if inv.status != "issued" or not s["upi_id"] or inv.amount_due <= 0:
        return None
    payee = s["upi_payee_name"] or s["brand_name"]
    uri = upi_uri(s["upi_id"], payee, inv.amount_due, f"{inv.project.code} {inv.number}")
    return dict(upi_id=s["upi_id"], payee=payee, uri=uri,
                qr="data:image/png;base64," + base64.b64encode(qr_png(uri, scale=5, border=1)).decode())


UTR_RE = re.compile(r"^[A-Za-z0-9]{6,35}$")


def submit_payment(project: Project, reference: str, proof=None) -> Payment:
    if project.is_paid:
        raise ApiError("Payment for this project has already been received.", 409, "already_paid")
    inv = project.invoice
    if project.status != "payment_pending" or not inv or inv.status != "issued":
        raise ApiError("The invoice for this project isn't ready yet.", 409, "no_invoice")
    if any(p.status == "submitted" for p in project.payments):
        raise ApiError("Your payment details were already submitted. The studio will confirm shortly.",
                       409, "already_submitted")
    reference, proof_id = _payment_evidence(project, reference, proof)
    pay = Payment(project=project, invoice_id=inv.id, amount=inv.amount_due, reference=reference,
                  proof_file_id=proof_id)
    db.session.add(pay)
    log_activity(project, "client", "payment_initiated",
                 f"Client submitted UPI payment details ({_evidence_text(reference, proof_id)})")
    notify_admin(project, "payment_submitted",
                 f"Payment submitted for {project.name} — please confirm")
    return pay


def confirm_payment(pay: Payment):
    if pay.status != "submitted":
        raise ApiError("This payment has already been processed.", 409)
    p = pay.project
    if p.status != "payment_pending":
        raise ApiError("Project is not awaiting payment.", 409)
    t = now()
    pay.status, pay.decided_at = "confirmed", t
    pay.invoice.status, pay.invoice.paid_at = "paid", t
    p.status, p.paid_at = "paid", t
    release_delivery(p, t)
    log_activity(p, "admin", "payment_verified",
                 f"Payment verified by studio ({_evidence_text(pay.reference, pay.proof_file_id)})")
    email_client(p, f"Payment received — {p.name}",
                 "Payment has been received successfully. Your final creative files are now available:",
                 "delivery")


def release_delivery(p: Project, t):
    days = int(setting("delivery_days") or 0)
    p.delivery_expires_at = t + timedelta(days=days) if days else None
    p.max_downloads = int(setting("max_downloads") or 0) or None


def reject_payment(pay: Payment, note: str | None):
    if pay.status != "submitted":
        raise ApiError("This payment has already been processed.", 409)
    pay.status, pay.decided_at = "rejected", now()
    pay.admin_note = (note or "").strip()[:255] or None
    log_activity(pay.project, "admin", "payment_rejected",
                 f"Payment ({_evidence_text(pay.reference, pay.proof_file_id)}) could not be matched")


def reopen(project: Project):
    if project.status not in ("approved", "finalization", "payment_pending"):
        raise ApiError("Only approved, unpaid projects can be reopened.", 409)
    for d in designs(project):
        if d.status == "approved":
            reopen_design(d)


def start_design(project: Project):
    if project.status != "brief_received":
        raise ApiError("Project is already in progress.", 409)
    project.status = "in_design"
    log_activity(project, "admin", "status", "Design started")


def complete(project: Project):
    if project.status not in ("paid", "delivered"):
        raise ApiError("Only paid projects can be marked complete.", 409)
    project.status = "completed"
    log_activity(project, "admin", "completed", "Project marked complete")


# ---------- advance payment ----------

def set_advance(project: Project, amount: int):
    """Ask for an advance (paise). 0 removes the request. Never lowered below what was already received."""
    if amount < 0:
        raise ApiError("The advance can't be negative.")
    if project.advance_paid and amount < project.advance_paid:
        raise ApiError("The client already paid more than that as advance.", 409)
    if amount and not active_token(project):  # the client needs a link to pay it, even before the first design
        create_review_link(project, setting("review_link_expiry"))
    if amount == project.advance_amount:
        return
    project.advance_amount = amount
    project.advance_requested_at = now() if amount else None
    log_activity(project, "admin", "advance_set",
                 f"Advance of {inr(amount)} requested" if amount else "Advance request removed")


def _payment_evidence(project: Project, reference: str, proof) -> tuple[str, int | None]:
    """A payment is shown by a UTR, a screenshot, or both. Returns (reference, proof file id)."""
    reference = re.sub(r"\s+", "", reference or "")
    has_proof = bool(proof and proof.filename)
    if reference and not UTR_RE.match(reference):
        raise ApiError("That doesn't look like a UPI transaction ID (UTR): 6 to 35 letters or numbers. "
                       "You can also upload a screenshot of the payment instead.")
    if not reference and not has_proof:
        raise ApiError("Upload a screenshot of the payment, or enter the UPI transaction ID (UTR).")
    proof_id = None
    if has_proof:
        data, ext, name = read_upload(proof, PROOF_EXTS)
        if len(data) > 10 * 1024 * 1024:
            raise ApiError("Screenshot must be under 10 MB.")
        proof_id = store_file(project, "payment_proof", data, ext, name).id
    return reference, proof_id


def _evidence_text(reference: str, proof_id) -> str:
    return " + ".join(x for x in (f"ref {reference}" if reference else "", "screenshot" if proof_id else "") if x)


def submit_advance(project: Project, reference: str, proof=None) -> AdvancePayment:
    if project.advance_amount <= 0:
        raise ApiError("No advance is due on this project.", 409, "no_advance")
    if project.advance_status == "paid":
        raise ApiError("The advance has already been received. Thank you!", 409, "already_paid")
    if any(a.status == "submitted" for a in project.advances):
        raise ApiError("Your payment details were already submitted. The studio will confirm shortly.",
                       409, "already_submitted")
    reference, proof_id = _payment_evidence(project, reference, proof)
    a = AdvancePayment(project=project, amount=project.advance_amount - project.advance_paid, reference=reference,
                       proof_file_id=proof_id)
    db.session.add(a)
    log_activity(project, "client", "advance_submitted",
                 f"Client submitted advance payment details ({_evidence_text(reference, proof_id)})")
    notify_admin(project, "advance_submitted", f"Advance submitted for {project.name}, please confirm")
    return a


def confirm_advance(a: AdvancePayment):
    if a.status != "submitted":
        raise ApiError("This payment has already been processed.", 409)
    a.status, a.decided_at = "confirmed", now()
    log_activity(a.project, "admin", "advance_verified",
                 f"Advance received ({_evidence_text(a.reference, a.proof_file_id)})")


def reject_advance(a: AdvancePayment, note: str | None):
    if a.status != "submitted":
        raise ApiError("This payment has already been processed.", 409)
    a.status, a.decided_at = "rejected", now()
    a.admin_note = (note or "").strip()[:255] or None
    log_activity(a.project, "admin", "advance_rejected", f"Advance payment ({_evidence_text(a.reference, a.proof_file_id)}) could not be matched")


def record_advance_received(project: Project, note: str | None = None) -> AdvancePayment:
    """The client paid by cash, a call or a transfer you already saw. Records it as received."""
    if project.advance_amount <= 0:
        raise ApiError("No advance is due on this project.", 409)
    if project.advance_status == "paid":
        raise ApiError("The advance has already been received.", 409)
    for a in project.advances:  # a client-submitted reference being confirmed this way
        if a.status == "submitted":
            confirm_advance(a)
            return a
    a = AdvancePayment(project=project, amount=project.advance_amount - project.advance_paid,
                       reference=(note or "recorded").replace(" ", "")[:30] or "recorded", status="confirmed", decided_at=now())
    db.session.add(a)
    log_activity(project, "admin", "advance_verified", "Advance marked as received")
    return a


def remind_advance(project: Project):
    if project.advance_status not in ("requested",):
        raise ApiError("There is no unpaid advance to remind about.", 409)
    project.advance_reminded_at = now()
    log_activity(project, "admin", "advance_reminder", "Advance reminder sent to the client")


def delivery_block_reason(project: Project, f: ProjectFile | None) -> str | None:
    """Every final-file request goes through this. None means allowed."""
    if not project.is_paid:
        return "Final files are available after payment confirmation."
    if not f or f.project_id != project.id or f.kind != "final":
        return "File not found."
    if project.delivery_expires_at and project.delivery_expires_at < now():
        return "This delivery link has expired. Please contact the studio for a new link."
    if project.max_downloads:
        used = Download.query.filter_by(project_id=project.id, file_id=f.id).count()
        if used >= project.max_downloads:
            return "The download limit for this file has been reached. Please contact the studio."
    return None


def record_download(project: Project, f: ProjectFile):
    db.session.add(Download(project_id=project.id, file_id=f.id))
    log_activity(project, "client", "downloaded", f"Final file downloaded: {f.label or f.original_name}")
    if project.status == "paid":
        project.status = "delivered"
        project.delivered_at = now()
        notify_admin(project, "delivered", f"{project.client.display_name} downloaded the final files "
                                            f"for {project.name}")


# ---------- quotations ----------

def inr(paise) -> str:
    """12345600 -> '₹1,23,456' (Indian digit grouping, decimals only when needed)."""
    rupees, p = divmod(int(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail, parts = digits[:-3], digits[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts + [tail])
    return f"₹{digits}" + (f".{p:02d}" if p else "")


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_template(template: str, **values) -> str:
    """Fill {placeholders}; an unknown or malformed one is left as typed instead of breaking the page."""
    try:
        return template.format_map(_Safe(values))
    except (IndexError, ValueError, KeyError, AttributeError):
        return template


def upi_uri(upi_id: str, payee: str, amount_paise: int | None = None, note: str | None = None) -> str:
    """The link a UPI app understands. Without an amount the payer types it in."""
    uri = f"upi://pay?pa={urlquote(upi_id, safe='@.')}&pn={urlquote(payee)}"
    if amount_paise is not None:
        uri += f"&am={amount_paise / 100:.2f}"
    uri += "&cu=INR"
    if note:
        uri += f"&tn={urlquote(note[:50])}"
    return uri


def qr_png(text: str, scale: int = 6, border: int = 2) -> bytes:
    import segno
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()


def quote_payment(q: "Quote") -> dict | None:
    """Pay-by-UPI details for a quote (no amount: the studio and client agree the advance), or None if UPI isn't set up."""
    s = get_settings()
    if not s["upi_id"]:
        return None
    payee = s["upi_payee_name"] or s["brand_name"]
    uri = upi_uri(s["upi_id"], payee, note=q.number)
    png = qr_png(uri, scale=5, border=1)
    return dict(upi_id=s["upi_id"], payee=payee, uri=uri, qr="data:image/png;base64," + base64.b64encode(png).decode())


def next_quote_number():
    while True:
        num = _next_counter("quote_prefix", "quote_next")
        if not Quote.query.filter_by(number=num).first():
            return num


def quote_lines(q: Quote):
    """A complimentary line keeps its value (so the client sees what they are getting) but costs nothing."""
    return [dict(description=i.description, quantity=i.quantity, unit_price=i.unit_price,
                 complimentary=i.complimentary, value=i.quantity * i.unit_price, detail=i.detail, period=i.period,
                 list_price=i.list_price if i.list_price and i.list_price > i.unit_price else None,
                 amount=0 if i.complimentary else i.quantity * i.unit_price) for i in q.items]


def quote_mode(q: Quote) -> str:
    """once | monthly | mixed (one-time lines and monthly lines on the same quote)."""
    periods = {i.period for i in q.items if not i.complimentary}
    if periods == {"once", "monthly"}:
        return "mixed"
    return "monthly" if (periods == {"monthly"} or q.billing == "monthly") else "once"


def quote_split(q: Quote) -> dict:
    """What recurs every month and what is paid once. The first payment is the one-time fees plus the first month."""
    lines = quote_lines(q)
    save = lambda ls: sum((l["list_price"] - l["unit_price"]) * l["quantity"] for l in ls if l["list_price"] and not l["complimentary"])
    return dict(recurring=sum(l["amount"] for l in lines if l["period"] == "monthly"),
                one_time=sum(l["amount"] for l in lines if l["period"] != "monthly"),
                savings_monthly=save([l for l in lines if l["period"] == "monthly"]),
                savings_once=save([l for l in lines if l["period"] != "monthly"]))


def complimentary_value(q: Quote) -> int:
    return sum(i.quantity * i.unit_price for i in q.items if i.complimentary)


def invoice_closing(inv: Invoice) -> str:
    """The sign-off at the foot of an invoice: a thank-you while it is open, a warmer one once it is paid."""
    if inv.project.kind == "retainer":  # a monthly client gets no final files, so the usual sign-off doesn't fit
        return ""
    key = "invoice_closing_paid" if inv.status == "paid" else "invoice_closing"
    return render_template(setting(key), client=inv.project.client.display_name, studio=setting("brand_name"))


def default_closing(client_name: str) -> str:
    return render_template(setting("quote_closing"), client=client_name, studio=setting("brand_name"))


def quote_totals(q: Quote):
    lines = quote_lines(q)
    if q.recurring_start == "launch" and quote_mode(q) == "mixed":  # the monthly fee begins later, so the first payment is the one-time fees only
        lines = [l for l in lines if l["period"] != "monthly"]
    return compute_totals(lines, q.discount, q.gst_enabled, q.gst_rate_bp)


def quote_event(q: Quote, text: str):
    q.events = [*(q.events or []), dict(at=now().isoformat() + "Z", text=text[:300])]


def notify_quote(q: Quote, event: str, message: str):
    db.session.add(Notification(quote_id=q.id, event=event, message=message[:255]))
    send_email(setting("studio_email"), f"[{q.number}] {message}", message)


def save_quote(q: Quote, f: dict):
    q.client, q.title = f["client"], f["title"]
    q.discount, q.gst_enabled, q.gst_rate_bp = f["discount"], f["gst_enabled"], f["gst_rate_bp"]
    q.notes, q.terms, q.valid_until = f["notes"], f["terms"], f["valid_until"]
    q.closing = f["closing"]
    q.revisions_included, q.advance_percent = f["revisions_included"], f["advance_percent"]
    q.sections, q.billing = f.get("sections") or [], f.get("billing") or "once"
    q.discount_label, q.plan_inclusions = f.get("discount_label"), f.get("plan_inclusions") or []
    q.scope_first = f.get("scope_first", True)
    q.recurring_start = f.get("recurring_start") or "now"
    q.items.clear()
    for it in f["items"]:
        q.items.append(QuoteItem(**it))


def create_quote(f: dict) -> Quote:
    q = Quote(number=next_quote_number(), token=new_token(), status="draft", events=[])
    save_quote(q, f)
    db.session.add(q)
    db.session.flush()
    quote_event(q, "Quote created")
    return q


def update_quote(q: Quote, f: dict):
    if q.status in ("accepted", "declined"):
        raise ApiError(f"This quote was {q.status}. Duplicate it to make a new one.", 409)
    save_quote(q, f)
    quote_event(q, "Quote edited")


def send_quote(q: Quote):
    """Marks it as sent the first time it is shared. Sharing again later changes nothing."""
    if q.status == "draft":
        q.status, q.sent_at = "sent", now()
        quote_event(q, "Quote sent to client")


def touch_quote(q: Quote):
    t = now()
    if not q.first_viewed_at:
        q.first_viewed_at = t
        quote_event(q, "Client opened the quote")
        notify_quote(q, "quote_viewed", f"{q.client.display_name} opened quotation {q.number}")
    q.views += 1
    q.last_viewed_at = t


def respond_quote(q: Quote, accept: bool, note: str | None, *, by_client=True):
    if q.status == "accepted":
        raise ApiError("This quote has already been accepted.", 409, "already_responded")
    if q.status == "declined":
        raise ApiError("This quote was declined. Please contact the studio.", 409, "already_responded")
    if q.status == "draft":
        raise ApiError("This quote hasn't been sent yet.", 409, "not_sent")
    if q.effective_status == "expired":
        raise ApiError("This quote has expired. Please contact the studio for an updated quote.", 409, "expired")
    note = (note or "").strip()[:1000] or None
    q.status = "accepted" if accept else "declined"
    q.responded_at, q.response_note = now(), note
    who = "Client" if by_client else "You"
    quote_event(q, f"{who} {'accepted' if accept else 'declined'} the quote" + (f': "{note}"' if note else ""))
    if by_client:
        notify_quote(q, "quote_accepted" if accept else "quote_declined",
                     f"{q.client.display_name} {'accepted' if accept else 'declined'} quotation {q.number}")


def reopen_quote(q: Quote):
    if q.status != "declined":
        raise ApiError("Only a declined quote can be reopened.", 409)
    q.status, q.responded_at, q.response_note = "sent", None, None
    quote_event(q, "Quote reopened")


def quote_advance(q: Quote, percent: int | None = None) -> int:
    """The advance (paise) a quote asks for: a share of the full total, GST included."""
    pct = q.advance_percent if percent is None else percent
    return round(quote_totals(q)["total"] * pct / 100)


def design_titles(q: Quote) -> list[str]:
    """One design per thing the client ordered. Several of the same item become 'Post (1 of 3)' and so on."""
    out = []
    for i in q.items:
        if 1 < i.quantity <= 12:
            out += [f"{i.description} ({n} of {i.quantity})" for n in range(1, i.quantity + 1)]
        else:
            out.append(i.description)
    return [t[:200] for t in out]


def convert_quote(q: Quote, revisions: int | None = None, advance_percent: int | None = None) -> Project:
    if q.project_id:
        raise ApiError("A project was already created from this quote.", 409)
    if q.status != "accepted":
        raise ApiError("Only an accepted quote can start a project.", 409)
    revisions = q.revisions_included if revisions is None else revisions
    if not 0 <= revisions <= 50:
        raise ApiError("Revisions per design should be between 0 and 50.")
    if advance_percent is not None and not 0 <= advance_percent <= 100:
        raise ApiError("The advance should be between 0 and 100 percent.")
    totals = quote_totals(q)
    lines = quote_lines(q)
    p = Project(
        client=q.client, code=next_project_code(), name=q.title,
        project_type=(lines[0]["description"][:80] if len(lines) == 1 else "Design package"),
        description="\n".join(f"{l['description']} × {l['quantity']}" + (" (complimentary)" if l["complimentary"] else "")
                             for l in lines)
                    + f"\n\nFrom quotation {q.number}.",
        amount=totals["subtotal"], discount=totals["discount"], gst_enabled=q.gst_enabled,
        gst_rate_bp=q.gst_rate_bp, payment_terms=setting("payment_terms"),
        revisions_included=revisions,
        extra_revision_price=int(setting("default_extra_revision_price")),
    )
    db.session.add(p)
    db.session.flush()
    Deliverable.query.filter_by(project_id=p.id).delete()  # the placeholder first design
    for n, title in enumerate(design_titles(q)):
        db.session.add(Deliverable(project_id=p.id, title=title, position=n, status="pending"))
    db.session.flush()
    advance = quote_advance(q, advance_percent)
    if advance:
        p.advance_amount, p.advance_requested_at = advance, now()
        create_review_link(p, setting("review_link_expiry"))
    q.project_id = p.id
    log_activity(p, "admin", "created", f"Project created from quotation {q.number}")
    if advance:
        log_activity(p, "admin", "advance_set", f"Advance of {inr(advance)} requested")
    quote_event(q, f"Project {p.code} created")
    return p


def duplicate_quote(q: Quote) -> Quote:
    f = dict(client=q.client, title=q.title, discount=q.discount, gst_enabled=q.gst_enabled,
             gst_rate_bp=q.gst_rate_bp, notes=q.notes, terms=q.terms, closing=q.closing,
             revisions_included=q.revisions_included, advance_percent=q.advance_percent,
             sections=q.sections, billing=q.billing, discount_label=q.discount_label, plan_inclusions=q.plan_inclusions,
             scope_first=q.scope_first, valid_until=date.today() + timedelta(days=int(setting("quote_valid_days"))),
             items=[dict(description=i.description, quantity=i.quantity, unit_price=i.unit_price,
                         complimentary=i.complimentary, detail=i.detail, period=i.period, list_price=i.list_price) for i in q.items])
    c = create_quote(f)
    quote_event(c, f"Copied from {q.number}")
    return c


# ---------- monthly clients: plans, the content calendar, client logins ----------

POST_KINDS = {"post": "Post", "carousel": "Carousel", "reel": "Reel", "story": "Story"}
PLATFORMS = ("Instagram", "Facebook", "LinkedIn", "YouTube", "X", "WhatsApp", "Google Business")


def _month(ym: str) -> tuple[datetime, datetime]:
    """First instant of a month and of the next one, from 'YYYY-MM'."""
    try:
        y, m = (int(x) for x in ym.split("-"))
        start = datetime(y, m, 1)
    except (ValueError, AttributeError):
        raise ApiError("Choose a month like 2026-10.")
    return start, datetime(y + (m == 12), m % 12 + 1, 1)


def _when(v) -> datetime:
    """'2026-10-10' or '2026-10-10T18:00' as the studio's wall-clock time; a bare date means 10:00."""
    try:
        s = str(v).strip().replace(" ", "T")
        return datetime.fromisoformat(s if "T" in s else s + "T10:00")
    except ValueError:
        raise ApiError("Choose a date and time for the post.")


def clean_platforms(v) -> str | None:
    items = [str(x).strip() for x in (v if isinstance(v, list) else str(v or "").split(",")) if str(x).strip()]
    bad = [x for x in items if x not in PLATFORMS]
    if bad:
        raise ApiError(f"Unknown platform: {bad[0]}.")
    return ",".join(dict.fromkeys(items)) or None


def clean_inclusions(v) -> list[dict]:
    out = []
    for row in v if isinstance(v, list) else []:
        kind, count = str((row or {}).get("kind", "")), (row or {}).get("count")
        if kind not in POST_KINDS or not str(count).isdigit() or not 0 <= int(count) <= 500:
            raise ApiError("Each plan line needs a type (post, carousel, reel, story) and a count from 0 to 500.")
        if int(count):
            out.append(dict(kind=kind, count=int(count)))
    return out


def save_plan(client: Client, f: dict) -> Plan:
    """Set up or change a monthly client's plan. The first save also creates their content project."""
    plan = client.plan or Plan(client=client)
    plan.name, plan.monthly_price, plan.start_date = f["name"], f["monthly_price"], f["start_date"]
    plan.active, plan.revisions_per_post, plan.inclusions = f["active"], f["revisions_per_post"], f["inclusions"]
    for k in ("client_approval", "payment_reminder"):
        if k in f:
            setattr(plan, k, bool(f[k]))
    db.session.add(plan)
    db.session.flush()
    if not plan.project:
        plan.project = Project(client=client, code=next_project_code(), name=f"{client.display_name} content calendar",
                               project_type="Monthly content", kind="retainer", status="in_design",
                               revisions_included=plan.revisions_per_post, extra_revision_price=0, amount=0)
        db.session.add(plan.project)
        db.session.flush()
        log_activity(plan.project, "admin", "created", "Monthly plan started")
    else:
        plan.project.revisions_included = plan.revisions_per_post
    return plan


def _post_fields(f: dict) -> dict:
    kind = str(f.get("kind") or "post")
    if kind not in POST_KINDS:
        raise ApiError("Choose a type: post, carousel, reel or story.")
    title = str(f.get("title") or "").strip()
    when = _when(f.get("scheduled_at"))
    if not title:  # a planned slot needs no name yet: "Reel, 5 Nov"
        if not when:
            raise ApiError("Give the post a title or a date.")
        title = f"{POST_KINDS[kind]}, {when.day} {when:%b}"
    url = str(f.get("media_url") or "").strip()
    if url and not re.match(r"^https?://", url, re.I):
        raise ApiError("The video link must start with http:// or https://.")
    return dict(title=title[:200], kind=kind, scheduled_at=when,
                platforms=clean_platforms(f.get("platforms")), caption=(str(f.get("caption") or "").strip()[:4000] or None),
                media_url=url[:500] or None)


def add_post(plan: Plan, f: dict) -> Deliverable:
    if not plan.active:
        raise ApiError("This plan is switched off.", 409)
    p = plan.project
    ds = designs(p)
    d = Deliverable(project_id=p.id, position=(ds[-1].position + 1) if ds else 0, status="pending", **_post_fields(f))
    db.session.add(d)
    db.session.flush()
    log_activity(p, "admin", "post_added", f"Post planned: {d.title} ({d.scheduled_at:%d %b})")
    return d


def update_post(d: Deliverable, f: dict) -> Deliverable:
    for k, v in _post_fields(f).items():
        setattr(d, k, v)
    return d


def remove_post(d: Deliverable):
    if d.versions:
        raise ApiError("This post already has designs, so it can't be removed.", 409)
    log_activity(d.project, "admin", "post_removed", f"Post removed: {d.title}")
    db.session.delete(d)


def set_posted(d: Deliverable, posted: bool):
    if posted and d.status != "approved":
        plan = Plan.query.filter_by(project_id=d.project_id).first()
        if plan and not plan.client_approval and d.latest_version and d.status in ("review", "changes_requested"):
            approve_for_client(d)  # no client approval for this plan: sharing the design is enough, so mark it done quietly
        else:
            raise ApiError("Only an approved post can be marked as posted.", 409)
    d.posted_at = now() if posted else None
    log_activity(d.project, "admin", "post_posted" if posted else "post_unposted",
                 f"{d.title} marked as {'posted' if posted else 'not posted'}")


def has_brief(d: Deliverable) -> bool:
    return bool((d.brief or "").strip() or d.brief_file_ids)


def post_state(d: Deliverable) -> str:
    """planned | brief | review | changes | approved | posted: what a calendar tile shows."""
    if d.posted_at:
        return "posted"
    if d.status == "pending" and has_brief(d):
        return "brief"  # the client has sent what they want; the studio has not shared a design yet
    return {"pending": "planned", "review": "review", "changes_requested": "changes", "approved": "approved"}[d.status]


def plan_months(plan: Plan) -> list[dict]:
    """The months that have something planned, oldest first, so the calendar can open on one that is not empty."""
    counts: dict[str, int] = {}
    for d in designs(plan.project):
        if d.scheduled_at:
            counts[_ym(d.scheduled_at.date())] = counts.get(_ym(d.scheduled_at.date()), 0) + 1
    return [dict(month=m, count=n) for m, n in sorted(counts.items())]


def calendar_items(plan: Plan, ym: str) -> list[Deliverable]:
    start, end = _month(ym)
    return [d for d in designs(plan.project) if d.scheduled_at and start <= d.scheduled_at < end]


def plan_progress(plan: Plan, ym: str) -> list[dict]:
    """For each kind in the plan: how many are included, planned, approved and posted this month."""
    items = calendar_items(plan, ym)
    kinds = [i["kind"] for i in plan.inclusions] + [d.kind for d in items if d.kind not in {i["kind"] for i in plan.inclusions}]
    rows = []
    for k in dict.fromkeys(kinds):
        mine = [d for d in items if d.kind == k]
        rows.append(dict(kind=k, label=POST_KINDS[k], included=next((i["count"] for i in plan.inclusions if i["kind"] == k), 0),
                         planned=len(mine), approved=sum(1 for d in mine if d.status == "approved"),
                         made=sum(1 for d in mine if d.status != "pending"),  # a design has been shared
                         posted=sum(1 for d in mine if d.posted_at)))
    return rows


# ---------- the conversation on one post ----------

def _is_team_comment(c: Comment) -> bool:
    return c.author != "client"


def _post_comments(d: Deliverable) -> list[Comment]:
    """Chat messages on this post, plus the change requests the client made on any of its versions."""
    ids = {v.id for v in d.versions}
    return [c for c in d.project.comments if c.deliverable_id == d.id or (c.kind == "revision" and c.version_id in ids)]


def post_unread(d: Deliverable, side: str) -> int:
    """Messages the given side has not opened yet: 'client' counts the team's, 'team' counts the client's."""
    want_team = side == "client"
    n = sum(1 for c in _post_comments(d) if _is_team_comment(c) == want_team and c.seen_at is None)
    return n + (1 if side == "team" and brief_is_new(d) else 0)


def brief_is_new(d: Deliverable) -> bool:
    """A brief your team has not opened yet (or one the client changed since)."""
    return bool(d.brief_at and has_brief(d) and (d.brief_seen_at is None or d.brief_seen_at < d.brief_at))


def post_is_fresh(d: Deliverable) -> bool:
    """A creative the client has not opened yet, waiting for their review."""
    v = d.latest_version
    return bool(v) and d.status == "review" and d.client_seen_version_id != v.id


def post_thread(d: Deliverable) -> list[dict]:
    """Everything said and shown on a post, oldest first: new versions from the team and messages from both sides."""
    rows = [dict(type="version", at=v.created_at, number=v.label, note=v.note, id=-v.id) for v in d.versions]
    for c in _post_comments(d):
        rows.append(dict(type="message", at=c.created_at, id=c.id, team=_is_team_comment(c), name=c.author_name,
                         body=c.body, changes=c.kind == "revision"))
    return sorted(rows, key=lambda r: (r["at"], r["id"]))


def mark_thread_seen(d: Deliverable, side: str):
    """Opening a post marks the other side's messages as read; a client opening it also clears its 'new' flag."""
    want_team = side == "client"
    for c in _post_comments(d):
        if _is_team_comment(c) == want_team and c.seen_at is None:
            c.seen_at = now()
    if side == "team" and brief_is_new(d):
        d.brief_seen_at = now()
    if side == "client" and d.latest_version:
        d.client_seen_version_id = d.latest_version.id


def add_message(d: Deliverable, side: str, name: str, text: str) -> Comment:
    text = (text or "").strip()
    if not text:
        raise ApiError("Write a message first.")
    if len(text) > 2000:
        raise ApiError("Please keep a message under 2000 characters.")
    p = d.project
    c = Comment(project=p, deliverable_id=d.id, version_id=d.latest_version.id if d.latest_version else None,
                author="client" if side == "client" else "admin", kind="note", body=text, status="resolved",
                author_name=(name or "").strip()[:120] or None)
    db.session.add(c)
    snippet = text if len(text) <= 80 else text[:77] + "..."
    if side == "client":
        log_activity(p, "client", "message", f"{d.title}: {snippet}")
        notify_admin(p, "client_message", f"{p.client.display_name} wrote on {d.title}: {snippet}")
    else:
        log_activity(p, "admin", "message", f"Replied on {d.title}: {snippet}")
    return c


def client_updates(plan: Plan, limit: int = 8) -> list[dict]:
    """What is new for a client, newest first: designs the team added and messages the team wrote."""
    ev = []
    for d in designs(plan.project):
        if d.versions:
            v = d.versions[-1]
            if d.status in ("review", "changes_requested", "approved"):
                ev.append(dict(kind="creative", post_id=d.id, title=d.title, text=(f"New {POST_KINDS[d.kind].lower()} to review" if plan.client_approval else f"New {POST_KINDS[d.kind].lower()} is ready to view") if d.status == "review" else f"Version {v.label} added",
                               at=v.created_at, new=post_is_fresh(d)))
        for c in _post_comments(d):
            if _is_team_comment(c):
                ev.append(dict(kind="message", post_id=d.id, title=d.title, text=c.body, name=c.author_name, at=c.created_at, new=c.seen_at is None))
    ev.sort(key=lambda e: e["at"], reverse=True)
    return ev[:limit]


# ---------- money received from a monthly client ----------

def record_plan_payment(plan: Plan, amount: int, received_on: date, reference: str = "", note: str | None = None, proof=None) -> AdvancePayment:
    """Money a monthly client has paid you (UPI, IMPS, cash...). Stored with the plan and counted in your revenue."""
    if not 0 < amount <= 10**10:
        raise ApiError("Enter the amount you received.")
    if received_on > date.today() + timedelta(days=1):
        raise ApiError("The date of a payment you have received can't be in the future.")
    project = plan.project
    proof_id = None
    if proof is not None and getattr(proof, "filename", None):
        data, ext, name = read_upload(proof, PROOF_EXTS)
        if len(data) > 10 * 1024 * 1024:
            raise ApiError("Screenshot must be under 10 MB.")
        proof_id = store_file(project, "payment_proof", data, ext, name).id
    when = datetime.combine(received_on, datetime.min.time()) + timedelta(hours=12)
    a = AdvancePayment(project=project, amount=amount, reference=re.sub(r"\s+", "", reference or "")[:64], status="confirmed",
                       proof_file_id=proof_id, admin_note=(note or "").strip()[:255] or None, submitted_at=when, decided_at=when)
    db.session.add(a)
    log_activity(project, "admin", "plan_payment", f"Payment of {inr(amount)} received on {received_on:%d %b %Y}")
    return a


def plan_payments(plan: Plan) -> list[dict]:
    rows = [a for a in (plan.project.advances if plan.project else []) if a.status == "confirmed"]
    return [dict(id=a.id, amount=a.amount, reference=a.reference, note=a.admin_note, received_on=a.decided_at.date().isoformat(),
                 proof_file_id=a.proof_file_id) for a in sorted(rows, key=lambda a: (a.decided_at, a.id), reverse=True)]


# ---------- what the client wants in a post (their brief) ----------

BRIEF_FILE_EXTS = {"png", "jpg", "jpeg", "webp", "pdf"}
MAX_BRIEF_FILES = 8


def brief_files(d: Deliverable) -> list[dict]:
    out = []
    for fid in d.brief_file_ids or []:
        f = db.session.get(ProjectFile, fid)
        if f:
            out.append(dict(id=f.id, name=f.original_name, image=f.mime.startswith("image/")))
    return out


def save_brief(d: Deliverable, text: str, uploads: list, name: str, base: str | None = None):
    """The client writes down what they want in this post and attaches photos or a PDF. Allowed until the studio shares a design."""
    if d.status != "pending" or d.posted_at:
        raise ApiError("The studio has already started on this post. Please tell us what to change in the chat.", 409, "brief_closed")
    if base is not None and (d.brief_at.isoformat() + "Z" if d.brief_at else "") != base:
        # another person on the same login saved it after this person opened it: don't overwrite theirs without them knowing
        raise ApiError("Someone on your account just updated this. Their version is shown now. Please check it, then press Update.", 409, "brief_changed")
    text = (text or "").strip()
    uploads = [u for u in uploads if u is not None and getattr(u, "filename", None)]
    if len(text) > 4000:
        raise ApiError("Please keep it under 4000 characters.")
    ids = list(d.brief_file_ids or [])
    if len(ids) + len(uploads) > MAX_BRIEF_FILES:
        raise ApiError(f"You can attach up to {MAX_BRIEF_FILES} files to a post.")
    if not text and not uploads and not ids:
        raise ApiError("Write what you would like in this post, or attach a photo.")
    for u in uploads:
        data, ext, fname = read_upload(u, BRIEF_FILE_EXTS)
        if len(data) > 10 * 1024 * 1024:
            raise ApiError("Each file must be under 10 MB.")
        ids.append(store_file(d.project, "client_ref", data, ext, fname).id)
    d.brief, d.brief_file_ids = text or None, ids
    d.brief_at, d.brief_by, d.brief_seen_at = now(), (name or "").strip()[:120] or None, None
    log_activity(d.project, "client", "brief_sent", f"{d.title}: the client sent their content")
    notify_admin(d.project, "brief_sent", f"{d.project.client.display_name} sent their content for {d.title}")


def remove_brief_file(d: Deliverable, fid: int):
    if d.status != "pending" or d.posted_at:
        raise ApiError("The studio has already started on this post.", 409, "brief_closed")
    if fid not in (d.brief_file_ids or []):
        raise ApiError("File not found.", 404, "not_found")
    d.brief_file_ids = [i for i in d.brief_file_ids if i != fid]
    d.brief_at = now()


def team_attention(plans) -> list[dict]:
    """Posts where the client has said something your team has not opened yet: a brief or a message."""
    out = []
    for plan in plans:
        for d in designs(plan.project):
            if d.posted_at:
                continue
            new_brief = brief_is_new(d)
            msgs = [c for c in _post_comments(d) if not _is_team_comment(c) and c.seen_at is None]
            if not new_brief and not msgs:
                continue
            at = max(([d.brief_at] if new_brief else []) + [c.created_at for c in msgs])
            text = (d.brief if new_brief else msgs[-1].body) or "Attached files"
            out.append(dict(client_id=plan.client_id, client=plan.client.display_name, post_id=d.id, title=d.title, kind=d.kind,
                            scheduled_at=d.scheduled_at.isoformat(timespec="minutes") if d.scheduled_at else None,
                            what="brief" if new_brief else "message", count=len(msgs) + (1 if new_brief else 0),
                            text=text[:140], at=at.isoformat() + "Z"))
    return sorted(out, key=lambda r: r["at"], reverse=True)


# ---------- the month-end payment reminder ----------

PAYMENT_REMINDER_ENABLED = False  # parked for now: nothing shows to clients and the switch is hidden. Set True to bring it back.
REMIND_DAYS = 5  # the reminder shows this many days before the month ends
OVERDUE_DAYS = 10  # and for this many days into the next month, if the last one is still unpaid


def _ym(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _month_end(ym: str) -> date:
    import calendar as cal
    y, m = (int(x) for x in ym.split("-"))
    return date(y, m, cal.monthrange(y, m)[1])


def plan_payment_status(plan: Plan, today: date | None = None) -> dict:
    """Where this month's payment stands: which month the reminder is about, whether it is showing, and whether it is settled."""
    today = today or date.today()
    cur = _ym(today)
    prev = _ym(today.replace(day=1) - timedelta(days=1))
    paid = lambda ym: bool(plan.paid_through and plan.paid_through >= ym)
    started = lambda ym: not plan.start_date or plan.start_date <= _month_end(ym)
    month, overdue = cur, False
    if not paid(prev) and started(prev) and today.day <= OVERDUE_DAYS and plan.payment_reminder:
        month, overdue = prev, True
    due = _month_end(month)
    opens = due - timedelta(days=REMIND_DAYS)
    showing = bool(PAYMENT_REMINDER_ENABLED and plan.payment_reminder and plan.active and started(month) and not paid(month) and (overdue or today >= opens))
    return dict(month=month, label=datetime.strptime(month, "%Y-%m").strftime("%B %Y"), due_date=due.isoformat(),
                opens=opens.isoformat(), days_left=(due - today).days, overdue=overdue, paid=paid(month),
                claimed=plan.pay_claimed == month, showing=showing)


def plan_payment(plan: Plan, today: date | None = None) -> dict | None:
    """What the client's page shows when a payment is due, with UPI details when they are set up. None when nothing is due."""
    st = plan_payment_status(plan, today)
    if not st["showing"] or plan.monthly_price <= 0:
        return None
    s = get_settings()
    upi = None
    if s["upi_id"]:
        payee = s["upi_payee_name"] or s["brand_name"]
        uri = upi_uri(s["upi_id"], payee, plan.monthly_price, f"{plan.client.display_name} {st['month']}"[:50])
        upi = dict(upi_id=s["upi_id"], payee=payee, uri=uri,
                   qr="data:image/png;base64," + base64.b64encode(qr_png(uri, scale=5, border=1)).decode())
    return dict(st, amount=plan.monthly_price, upi=upi)


def claim_plan_payment(plan: Plan):
    """The client says they have paid. It only tells the studio; the studio marks the month as paid once it has the money."""
    pay = plan_payment(plan)
    if not pay:
        raise ApiError("There is no payment due right now.", 409)
    if plan.pay_claimed == pay["month"]:
        return
    plan.pay_claimed = pay["month"]
    notify_admin(plan.project, "payment_claimed", f"{plan.client.display_name} says they have paid {inr(plan.monthly_price)} for {pay['label']}")
    log_activity(plan.project, "client", "payment_claimed", f"Client says {pay['label']} is paid")


def mark_plan_paid(plan: Plan, paid: bool):
    st = plan_payment_status(plan)
    month = st["month"]
    if paid:
        plan.paid_through = max(plan.paid_through or "", month)
        plan.pay_claimed = None
    elif plan.paid_through and plan.paid_through >= month:
        y, m = (int(x) for x in month.split("-"))
        plan.paid_through = _ym(date(y, m, 1) - timedelta(days=1))
    log_activity(plan.project, "admin", "plan_paid" if paid else "plan_unpaid", f"{st['label']} marked as {'paid' if paid else 'not paid'}")


def create_client_login(client: Client, name: str, email: str, password: str, can_approve: bool) -> User:
    email = (email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ApiError("Enter a valid email address.")
    if User.query.filter_by(email=email).first():
        raise ApiError("There is already an account with this email.", 409)
    if len(password or "") < 10:
        raise ApiError("The password must be at least 10 characters.")
    if not (name or "").strip():
        raise ApiError("Name is required.")
    u = User(email=email, name=name.strip()[:120], role="client", client_id=client.id, can_approve=can_approve,
             active=True, password_hash=generate_password_hash(password))
    db.session.add(u)
    db.session.flush()
    return u


def clean_sections(v) -> list[dict]:
    """The scope of work. In a section's lines, '# ' starts a subheading and '> ' a note; anything else is a bullet."""
    if not isinstance(v, list):
        return []
    if len(v) > 12:
        raise ApiError("A quote can have up to 12 scope sections.")
    out = []
    for s in v:
        title = str((s or {}).get("title") or "").strip()
        raw = (s or {}).get("lines")
        lines = [str(x).strip() for x in (raw if isinstance(raw, list) else str(raw or "").splitlines()) if str(x).strip()]
        if not title and not lines:
            continue
        if not title:
            raise ApiError("Give each scope section a title.")
        if len(title) > 120 or len(lines) > 40 or any(len(x) > 400 for x in lines):
            raise ApiError("A scope section is too long. Keep titles under 120 and lines under 400 characters.")
        part = str((s or {}).get("part"))  # scope of work, a block after the pricing, or a closing page
        part = part if part in ("after", "appendix") else "scope"
        tone = str((s or {}).get("tone"))  # how it is styled: an advantage, a caution, or the page's title
        out.append(dict(title=title, lines=lines, part=part, tone=tone if tone in ("gain", "caution", "title") else None))
    return out


def start_plan_from_quote(q: Quote) -> Plan:
    """An accepted monthly quote becomes the client's monthly plan: its total is the price, its deliverables the inclusions."""
    if q.status != "accepted":
        raise ApiError("Only an accepted quote can start a monthly plan.", 409)
    if q.billing != "monthly":
        raise ApiError("This quote is not a monthly quote.", 409)
    if q.client.plan:
        raise ApiError("This client already has a monthly plan. Change it from the client's page.", 409)
    plan = save_plan(q.client, dict(name=q.title[:120], monthly_price=quote_totals(q)["total"], start_date=date.today(),
                                    active=True, revisions_per_post=q.revisions_included,
                                    inclusions=clean_inclusions(q.plan_inclusions)))
    quote_event(q, "Monthly plan started")
    return plan
