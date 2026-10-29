"""Database schema. Money is stored as integer paise; tax rates as basis points (1800 = 18%)."""
from datetime import date, datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint, event

db = SQLAlchemy()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


# Project lifecycle, in order.
STATUSES = [
    "brief_received", "in_design", "review", "revision_requested", "approved",
    "finalization", "payment_pending", "paid", "delivered", "completed",
]
PAID_STATUSES = {"paid", "delivered", "completed"}


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="admin")  # admin = the studio owner | staff = an employee
    active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    # role == "client": a login for someone at a client's company. They see only that client's content calendar.
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"))
    can_approve = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    clients = db.relationship("Client", secondary="user_clients", order_by="Client.name")

    @property
    def is_owner(self):
        return self.role == "admin"


class UserClient(db.Model):
    """Which clients an employee may work on. An employee sees nothing outside this list."""
    __tablename__ = "user_clients"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)


class Client(db.Model):
    __tablename__ = "clients"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    company = db.Column(db.String(160))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(30))
    whatsapp = db.Column(db.String(30))
    billing_address = db.Column(db.Text)
    gstin = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    projects = db.relationship("Project", back_populates="client", order_by="Project.id.desc()")

    @property
    def display_name(self):
        return self.company or self.name


class Project(db.Model):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_project_amount"),
        CheckConstraint("discount >= 0", name="ck_project_discount"),
        CheckConstraint("revisions_included >= 0", name="ck_project_revisions"),
    )
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    project_type = db.Column(db.String(80), nullable=False, default="Instagram Poster")
    description = db.Column(db.Text)
    internal_notes = db.Column(db.Text)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    format = db.Column(db.String(60))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    deliverable_types = db.Column(db.String(120))
    amount = db.Column(db.Integer, nullable=False, default=0)
    discount = db.Column(db.Integer, nullable=False, default=0)
    gst_enabled = db.Column(db.Boolean, nullable=False, default=False)
    gst_rate_bp = db.Column(db.Integer, nullable=False, default=1800)
    due_date = db.Column(db.Date)
    payment_terms = db.Column(db.String(255))
    revisions_included = db.Column(db.Integer, nullable=False, default=2)
    extra_revision_price = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="brief_received", index=True)
    # "retainer" = the long-running content calendar of a monthly client; its posts are designs that never lock the project
    kind = db.Column(db.String(20), nullable=False, default="project", server_default="project")
    approved_version_id = db.Column(db.Integer, db.ForeignKey("project_versions.id", use_alter=True))
    approved_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    delivery_expires_at = db.Column(db.DateTime)
    max_downloads = db.Column(db.Integer)  # per file; None = unlimited
    advance_amount = db.Column(db.Integer, nullable=False, default=0, server_default="0")  # paise the client pays up front
    advance_requested_at = db.Column(db.DateTime)
    advance_reminded_at = db.Column(db.DateTime)
    watermark = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    preview_rev = db.Column(db.Integer, nullable=False, default=0, server_default="0")  # bumps when previews are re-rendered
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now, nullable=False)

    client = db.relationship("Client", back_populates="projects")
    versions = db.relationship("ProjectVersion", back_populates="project",
                               foreign_keys="ProjectVersion.project_id",
                               order_by="ProjectVersion.number", cascade="all, delete-orphan")
    files = db.relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="project", order_by="Comment.id",
                               cascade="all, delete-orphan")
    review_tokens = db.relationship("ReviewToken", back_populates="project",
                                    order_by="ReviewToken.id.desc()", cascade="all, delete-orphan")
    invoice = db.relationship("Invoice", back_populates="project", uselist=False,
                              cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="project", order_by="Payment.id.desc()",
                               cascade="all, delete-orphan")
    deliverables = db.relationship("Deliverable", back_populates="project", order_by="Deliverable.position, Deliverable.id",
                                   cascade="all, delete-orphan")
    advances = db.relationship("AdvancePayment", back_populates="project", order_by="AdvancePayment.id.desc()",
                               cascade="all, delete-orphan")

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None

    @property
    def final_files(self):
        return [f for f in self.files if f.kind == "final"]

    @property
    def revisions_used(self):
        return sum(1 for c in self.comments if c.kind == "revision")

    @property
    def is_paid(self):
        return self.status in PAID_STATUSES

    @property
    def advance_paid(self):
        return sum(a.amount for a in self.advances if a.status == "confirmed")

    @property
    def advance_status(self):
        """none | requested | submitted | paid"""
        paid = self.advance_paid
        if paid and paid >= self.advance_amount:
            return "paid"
        if self.advance_amount <= 0:
            return "none"
        if any(a.status == "submitted" for a in self.advances):
            return "submitted"
        return "requested"


class ProjectFile(db.Model):
    """A stored object. kind: master (designer's working upload), preview, final, payment_proof, brand."""
    __tablename__ = "project_files"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    kind = db.Column(db.String(20), nullable=False)
    storage_key = db.Column(db.String(400), unique=True, nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    label = db.Column(db.String(120))
    mime = db.Column(db.String(100), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    project = db.relationship("Project", back_populates="files")


class ProjectVersion(db.Model):
    __tablename__ = "project_versions"
    __table_args__ = (UniqueConstraint("project_id", "number"),)
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    master_file_id = db.Column(db.Integer, db.ForeignKey("project_files.id"), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey("deliverables.id"))
    seq = db.Column(db.Integer)  # 1, 2, 3 ... within its design; `number` stays unique across the project
    preview_file_ids = db.Column(db.JSON, nullable=False, default=list)  # one per page
    note = db.Column(db.Text)
    # review | changes_requested | approved | superseded
    status = db.Column(db.String(30), nullable=False, default="review")
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    project = db.relationship("Project", back_populates="versions", foreign_keys=[project_id])
    master = db.relationship("ProjectFile", foreign_keys=[master_file_id])
    deliverable = db.relationship("Deliverable", back_populates="versions")

    @property
    def label(self):
        return self.seq or self.number


class ReviewToken(db.Model):
    __tablename__ = "review_tokens"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    views = db.Column(db.Integer, nullable=False, default=0)
    first_viewed_at = db.Column(db.DateTime)
    last_viewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    project = db.relationship("Project", back_populates="review_tokens")

    @property
    def state(self):
        if self.revoked_at:
            return "revoked"
        if self.expires_at and self.expires_at < now():
            return "expired"
        return "active"


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    version_id = db.Column(db.Integer, db.ForeignKey("project_versions.id"))
    author = db.Column(db.String(20), nullable=False)  # client | admin
    kind = db.Column(db.String(20), nullable=False, default="revision")  # revision (a change request) | note (a chat message)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")  # open | resolved
    is_extra = db.Column(db.Boolean, nullable=False, default=False)  # beyond included revisions
    deliverable_id = db.Column(db.Integer, db.ForeignKey("deliverables.id"), index=True)  # a chat message on one post
    author_name = db.Column(db.String(120))  # who wrote it, as the other side sees it
    seen_at = db.Column(db.DateTime)  # when the other side opened it
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    project = db.relationship("Project", back_populates="comments")
    version = db.relationship("ProjectVersion")


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True, nullable=False)
    number = db.Column(db.String(40), unique=True, nullable=False)
    subtotal = db.Column(db.Integer, nullable=False)
    discount = db.Column(db.Integer, nullable=False, default=0)
    tax_rate_bp = db.Column(db.Integer, nullable=False, default=0)
    tax = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False)
    advance_paid = db.Column(db.Integer, nullable=False, default=0, server_default="0")  # already received, so not due again
    status = db.Column(db.String(20), nullable=False, default="issued")  # issued | paid | void
    notes = db.Column(db.Text)  # shown on the invoice, written by the studio
    issued_at = db.Column(db.DateTime, default=now, nullable=False)
    paid_at = db.Column(db.DateTime)
    project = db.relationship("Project", back_populates="invoice")

    @property
    def amount_due(self):
        return max(0, self.total - self.advance_paid)
    items = db.relationship("InvoiceItem", back_populates="invoice", order_by="InvoiceItem.id",
                            cascade="all, delete-orphan")


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(60))  # e.g. "Included"
    invoice = db.relationship("Invoice", back_populates="items")


class Payment(db.Model):
    """A client-submitted payment. Only an admin confirmation moves it to 'confirmed'."""
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    provider = db.Column(db.String(20), nullable=False, default="upi")
    amount = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(64), nullable=False)  # UTR
    proof_file_id = db.Column(db.Integer, db.ForeignKey("project_files.id"))
    # submitted | confirmed | rejected
    status = db.Column(db.String(20), nullable=False, default="submitted")
    admin_note = db.Column(db.String(255))
    submitted_at = db.Column(db.DateTime, default=now, nullable=False)
    decided_at = db.Column(db.DateTime)
    project = db.relationship("Project", back_populates="payments")
    invoice = db.relationship("Invoice")


class Download(db.Model):
    __tablename__ = "downloads"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("project_files.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    file = db.relationship("ProjectFile")


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    actor = db.Column(db.String(20), nullable=False)  # admin | client | system
    event = db.Column(db.String(60), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False, index=True)
    project = db.relationship("Project")


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))
    quote_id = db.Column(db.Integer)
    event = db.Column(db.String(60), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    project = db.relationship("Project")


# draft -> sent -> accepted | declined. "expired" is derived from valid_until, never stored.
QUOTE_STATUSES = ["draft", "sent", "accepted", "declined"]


class Quote(db.Model):
    __tablename__ = "quotes"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    discount = db.Column(db.Integer, nullable=False, default=0)
    gst_enabled = db.Column(db.Boolean, nullable=False, default=False)
    gst_rate_bp = db.Column(db.Integer, nullable=False, default=1800)
    revisions_included = db.Column(db.Integer, nullable=False, default=2, server_default="2")  # per design
    advance_percent = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    notes = db.Column(db.Text)
    closing = db.Column(db.Text)  # the friendly sign-off at the end of the quote
    terms = db.Column(db.Text)
    # Scope of work: [{"title": "...", "lines": ["# subheading", "a bullet", "> a note"]}]
    sections = db.Column(db.JSON, nullable=False, default=list)
    billing = db.Column(db.String(10), nullable=False, default="once", server_default="once")  # once | monthly
    scope_first = db.Column(db.Boolean, nullable=False, default=True, server_default="1")  # scope of work above the pricing
    recurring_start = db.Column(db.String(10), nullable=False, default="now", server_default="now")  # now | launch (monthly fee begins after delivery)
    discount_label = db.Column(db.String(80))  # e.g. "Special client discount"
    # For a monthly quote: what the plan includes each month, used when the accepted quote starts the plan
    plan_inclusions = db.Column(db.JSON, nullable=False, default=list)
    valid_until = db.Column(db.Date, nullable=False)
    sent_at = db.Column(db.DateTime)
    first_viewed_at = db.Column(db.DateTime)
    last_viewed_at = db.Column(db.DateTime)
    views = db.Column(db.Integer, nullable=False, default=0)
    responded_at = db.Column(db.DateTime)
    response_note = db.Column(db.String(1000))
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))
    events = db.Column(db.JSON, nullable=False, default=list)  # [{at, text}], newest last
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now, nullable=False)
    client = db.relationship("Client")
    project = db.relationship("Project")
    items = db.relationship("QuoteItem", back_populates="quote", order_by="QuoteItem.id",
                            cascade="all, delete-orphan")

    @property
    def effective_status(self):
        if self.status == "sent" and self.valid_until < date.today():
            return "expired"
        return self.status


class QuoteItem(db.Model):
    __tablename__ = "quote_items"
    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey("quotes.id"), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Integer, nullable=False)  # for a complimentary item this is its value, shown but not charged
    complimentary = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    detail = db.Column(db.Text)  # a few lines under the description: what this line covers
    period = db.Column(db.String(10), nullable=False, default="once", server_default="once")  # once | monthly
    list_price = db.Column(db.Integer)  # the standard price each, shown crossed out beside a special offer price
    quote = db.relationship("Quote", back_populates="items")


class Deliverable(db.Model):
    """One design inside a project (a banner, a standee, a post...). Each has its own versions and approval."""
    __tablename__ = "deliverables"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    # pending (no version yet) | review | changes_requested | approved
    status = db.Column(db.String(20), nullable=False, default="pending")
    # content-calendar fields (only used by a monthly client's posts)
    kind = db.Column(db.String(20), nullable=False, default="post", server_default="post")  # post | carousel | reel | story
    scheduled_at = db.Column(db.DateTime)  # the studio's wall-clock time, not UTC
    platforms = db.Column(db.String(160))  # comma separated: Instagram,Facebook
    caption = db.Column(db.Text)
    media_url = db.Column(db.String(500))  # a reel's video link until real video upload exists
    posted_at = db.Column(db.DateTime)
    client_seen_version_id = db.Column(db.Integer)  # the newest version the client has opened, to flag a new one
    # what the client wants in this post: their own words and the photos or documents they attach
    brief = db.Column(db.Text)
    brief_file_ids = db.Column(db.JSON, nullable=False, default=list)
    brief_at = db.Column(db.DateTime)
    brief_by = db.Column(db.String(120))
    brief_seen_at = db.Column(db.DateTime)  # when your team opened it
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    project = db.relationship("Project", back_populates="deliverables")
    versions = db.relationship("ProjectVersion", back_populates="deliverable", order_by="ProjectVersion.number")

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None

    @property
    def revisions_used(self):
        ids = {v.id for v in self.versions}
        return sum(1 for c in self.project.comments if c.kind == "revision" and c.version_id in ids)


@event.listens_for(Project, "after_insert")
def _first_design(mapper, connection, target):
    """Every project starts with one design named after it; a quote's items replace it with several."""
    connection.execute(Deliverable.__table__.insert().values(
        project_id=target.id, title=(target.name or "Design")[:200], position=0, status="pending", created_at=now()))


class AdvancePayment(db.Model):
    """The advance a client pays before the work goes on. Only the studio's confirmation counts."""
    __tablename__ = "advance_payments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(64), nullable=False)  # UTR; empty when the client sent a screenshot only
    proof_file_id = db.Column(db.Integer, db.ForeignKey("project_files.id"))
    status = db.Column(db.String(20), nullable=False, default="submitted")  # submitted | confirmed | rejected
    admin_note = db.Column(db.String(255))
    submitted_at = db.Column(db.DateTime, default=now, nullable=False)
    decided_at = db.Column(db.DateTime)
    project = db.relationship("Project", back_populates="advances")


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.JSON)


class Plan(db.Model):
    """A monthly client's retainer: what they pay each month and what that includes."""
    __tablename__ = "plans"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), unique=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))
    name = db.Column(db.String(120), nullable=False, default="Monthly plan")
    monthly_price = db.Column(db.Integer, nullable=False, default=0)  # paise; the owner's number only
    start_date = db.Column(db.Date)
    active = db.Column(db.Boolean, nullable=False, default=True)
    revisions_per_post = db.Column(db.Integer, nullable=False, default=2)
    inclusions = db.Column(db.JSON, nullable=False, default=list)  # [{"kind": "post", "count": 12}, ...]
    client_approval = db.Column(db.Boolean, nullable=False, default=False, server_default="0")  # off: the client only views and chats
    payment_reminder = db.Column(db.Boolean, nullable=False, default=False, server_default="0")  # month-end reminder on the client's page
    paid_through = db.Column(db.String(7))  # the last month marked as paid, "2026-10"
    pay_claimed = db.Column(db.String(7))  # the month the client says they have paid, until you confirm
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    client = db.relationship("Client", backref=db.backref("plan", uselist=False))
    project = db.relationship("Project", foreign_keys=[project_id])
