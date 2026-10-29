"""Demo data: one project in every interesting stage, built through the real workflow functions."""
import io
import shutil
from datetime import date, timedelta
from pathlib import Path

import click
import pymupdf
from flask import current_app
from PIL import Image, ImageDraw, ImageFont
from werkzeug.security import generate_password_hash

from . import services as sv
from .models import (ActivityLog, Client, Comment, Download, Invoice, Notification, Payment, Project,
                     ProjectVersion, ReviewToken, User, db, now)

DEMO_EMAIL = "admin@creativeflow.local"
DEMO_PASSWORD = "creativeflow-demo"


def poster(w, h, bg, accent, title, sub, date_text, date_size, fmt="PNG"):
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    u = min(w, h)
    d.rectangle([0, int(h * 0.68), w, h], fill=accent)
    d.ellipse([int(w * 0.62), int(h * 0.08), int(w * 1.1), int(h * 0.08) + int(w * 0.48)],
              outline=accent, width=max(4, u // 60))
    d.text((int(w * 0.07), int(h * 0.12)), title, font=ImageFont.load_default(size=u // 9),
           fill="white", spacing=u // 40)
    d.text((int(w * 0.07), int(h * 0.55)), sub, font=ImageFont.load_default(size=u // 26),
           fill=(230, 230, 240))
    d.text((int(w * 0.07), int(h * 0.74)), date_text, font=ImageFont.load_default(size=date_size),
           fill=bg)
    d.text((int(w * 0.07), int(h * 0.92)), "Register: www.example.in",
           font=ImageFont.load_default(size=u // 34), fill=bg)
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def pdf_from_pages(pages_png):
    doc = pymupdf.open()
    for png in pages_png:
        im = Image.open(io.BytesIO(png))
        page = doc.new_page(width=im.width * 0.5, height=im.height * 0.5)
        page.insert_image(page.rect, stream=png)
    return doc.tobytes()


class Upload(io.BytesIO):
    """Mimics a werkzeug FileStorage enough for services.read_upload."""
    def __init__(self, data, filename):
        super().__init__(data)
        self.filename = filename


class Clock:
    """Back-dates rows created during each step so the demo timeline looks real."""
    MODELS = [(ActivityLog, "created_at"), (ProjectVersion, "created_at"), (Comment, "created_at"),
              (Payment, "submitted_at"), (Download, "created_at"), (Notification, "created_at"),
              (ReviewToken, "created_at"), (Invoice, "issued_at")]

    def __init__(self):
        self.marks = {m: self._max(m) for m, _ in self.MODELS}

    @staticmethod
    def _max(model):
        return db.session.query(db.func.coalesce(db.func.max(model.id), 0)).scalar()

    def at(self, when):
        db.session.flush()
        for model, col in self.MODELS:
            mark = self.marks[model]
            for row in model.query.filter(model.id > mark).all():
                setattr(row, col, when)
            self.marks[model] = self._max(model)


def run(reset=False):
    if reset:
        db.drop_all()
        db.create_all()
        storage = Path(current_app.config["STORAGE_DIR"]) / "projects"
        shutil.rmtree(storage, ignore_errors=True)
    if Project.query.count():
        click.echo("Database already has projects. Use --reset to start over.")
        return

    if not User.query.filter_by(email=DEMO_EMAIL).first():
        db.session.add(User(email=DEMO_EMAIL, name="Studio Admin",
                            password_hash=generate_password_hash(DEMO_PASSWORD)))
    for k, v in dict(brand_name="CreativeFlow Studio", studio_email="", studio_phone="+91 98220 00000",
                     studio_address="Dharampeth, Nagpur, Maharashtra 440010",
                     upi_id="creativeflow@okaxis", upi_payee_name="CreativeFlow Studio").items():
        sv.set_setting(k, v)

    t0 = now() - timedelta(days=6)
    clock = Clock()

    def client(**kw):
        c = Client(**kw)
        db.session.add(c)
        db.session.flush()
        return c

    abc = client(name="Rohit Deshmukh", company="ABC Events", email="rohit@abcevents.example",
                 phone="9822012345", whatsapp="9822012345",
                 billing_address="Civil Lines, Nagpur, Maharashtra 440001", gstin="27ABCDE1234F1Z5")
    vcc = client(name="Sneha Kulkarni", company="Vidarbha Cycling Club", email="sneha@vcc.example",
                 whatsapp="9890011122")
    wild = client(name="Amit Patil", company="Wild Trails", email="amit@wildtrails.example",
                  whatsapp="9764400011")
    sweets = client(name="Kavita Sharma", company="Sharma Sweets", whatsapp="9011223344")
    pace = client(name="Neha Joshi", company="Pace Labs", email="neha@pacelabs.example",
                  whatsapp="9123456780", billing_address="IT Park, Nagpur 440022", gstin="27PQRSX6789K1Z2")

    def project(c, **kw):
        defaults = dict(quantity=1, revisions_included=2, extra_revision_price=50000,
                        payment_terms=sv.setting("payment_terms"))
        defaults.update(kw)
        p = Project(client=c, code=sv.next_project_code(), **defaults)
        db.session.add(p)
        db.session.flush()
        sv.log_activity(p, "admin", "created", "Project created")
        return p

    def version(p, data, name, note=None):
        data, ext, name = sv.read_upload(Upload(data, name), sv.MASTER_EXTS)
        return sv.add_version(p, data, ext, name, note)

    def final(p, data, name, label):
        data, ext, name = sv.read_upload(Upload(data, name), sv.FINAL_EXTS)
        return sv.add_final(p, data, ext, name, label)

    def view(p):
        sv.touch_link(sv.active_token(p))

    navy, gold = (18, 32, 70), (240, 180, 40)

    # 1. Nagpur Marathon — the spec's journey, ending at Payment Pending.
    p1 = project(abc, name="Nagpur Marathon 2026", project_type="Instagram Poster", width=1080,
                 height=1350, format="JPG + PNG", deliverable_types="JPG, PNG", amount=150000,
                 gst_enabled=True, gst_rate_bp=1800, due_date=date.today() + timedelta(days=3),
                 description="Main announcement poster for the 2026 edition.")
    clock.at(t0)
    version(p1, poster(1080, 1350, navy, gold, "NAGPUR\nMARATHON\n2026", "Run the Orange City",
                       "12 OCTOBER", 70), "poster-final.png")
    clock.at(t0 + timedelta(hours=1, minutes=20))
    view(p1)
    clock.at(t0 + timedelta(hours=1, minutes=30))
    sv.request_revision(p1, "Please make the date larger.")
    clock.at(t0 + timedelta(hours=2, minutes=10))
    v2 = version(p1, poster(1080, 1350, navy, gold, "NAGPUR\nMARATHON\n2026", "Run the Orange City",
                            "12 OCTOBER", 120), "poster-final-v2.png", "Date enlarged as requested.")
    clock.at(t0 + timedelta(hours=4))
    view(p1)
    sv.approve(p1, v2.id)
    clock.at(t0 + timedelta(hours=5, minutes=10))
    big = poster(1080, 1350, navy, gold, "NAGPUR\nMARATHON\n2026", "Run the Orange City", "12 OCTOBER", 120)
    final(p1, poster(1080, 1350, navy, gold, "NAGPUR\nMARATHON\n2026", "Run the Orange City",
                     "12 OCTOBER", 120, "JPEG"), "nagpur-marathon-poster.jpg", "Instagram Poster JPG")
    final(p1, big, "nagpur-marathon-poster.png", "Instagram Poster PNG")
    sv.issue_invoice(p1)
    clock.at(t0 + timedelta(hours=5, minutes=15))

    # 2. Cyclothon banner — in review, client has looked once.
    p2 = project(vcc, name="Orange City Cyclothon", project_type="Event Banner", width=1920, height=1080,
                 format="JPG", deliverable_types="JPG", amount=250000,
                 due_date=date.today() + timedelta(days=5))
    clock.at(t0 + timedelta(days=4))
    version(p2, poster(1920, 1080, (20, 70, 60), (250, 120, 60), "ORANGE CITY\nCYCLOTHON",
                       "50 km · 25 km · 10 km", "19 OCTOBER · 6 AM", 80), "cyclothon-banner.png")
    clock.at(t0 + timedelta(days=4, hours=2))
    view(p2)
    clock.at(t0 + timedelta(days=5))

    # 3. Trail run flyer (PDF, 2 pages) — revision requested.
    p3 = project(wild, name="Tadoba Trail Run Flyer", project_type="Flyer (A5, 2 pages)", width=1240,
                 height=1748, format="PDF", deliverable_types="Print PDF", amount=320000, gst_enabled=True,
                 gst_rate_bp=1800, due_date=date.today() + timedelta(days=2))
    clock.at(t0 + timedelta(days=2))
    pdf = pdf_from_pages([
        poster(1240, 1748, (30, 50, 30), (200, 160, 60), "TADOBA\nTRAIL RUN", "21K · 10K · 5K", "2 NOVEMBER", 90),
        poster(1240, 1748, (30, 50, 30), (200, 160, 60), "ROUTE &\nRULES", "Aid stations every 5 km",
               "REPORTING 5:30 AM", 70),
    ])
    version(p3, pdf, "tadoba-flyer.pdf")
    clock.at(t0 + timedelta(days=2, hours=3))
    view(p3)
    sv.request_revision(p3, "Can we use a darker green on page 1 and add the sponsor logo strip at the bottom?")
    clock.at(t0 + timedelta(days=3))

    # 4. Diwali creative — paid, not yet downloaded.
    p4 = project(sweets, name="Diwali Offer Creative", project_type="Instagram Post", width=1080,
                 height=1080, format="JPG", deliverable_types="JPG", amount=120000, revisions_included=1)
    clock.at(t0 + timedelta(days=1))
    v = version(p4, poster(1080, 1080, (110, 20, 40), (250, 190, 60), "DIWALI\nSPECIAL", "Kaju katli · Motichoor",
                           "20% OFF", 120), "diwali-offer.png")
    clock.at(t0 + timedelta(days=1, hours=2))
    view(p4)
    sv.approve(p4, v.id)
    final(p4, poster(1080, 1080, (110, 20, 40), (250, 190, 60), "DIWALI\nSPECIAL", "Kaju katli · Motichoor",
                     "20% OFF", 120, "JPEG"), "diwali-offer.jpg", "Instagram Post JPG")
    sv.issue_invoice(p4)
    clock.at(t0 + timedelta(days=1, hours=3))
    pay = sv.submit_payment(p4, "426815093317")
    clock.at(t0 + timedelta(days=1, hours=5))
    sv.confirm_payment(pay)
    pay.decided_at = t0 + timedelta(days=1, hours=6)
    p4.paid_at = pay.decided_at
    clock.at(t0 + timedelta(days=1, hours=6))

    # 5. Corporate brochure — completed and downloaded.
    p5 = project(pace, name="Corporate Run Brochure", project_type="Brochure (4 pages)", width=1240,
                 height=1748, format="PDF", deliverable_types="Print PDF, PNG", amount=600000,
                 gst_enabled=True, gst_rate_bp=1800, discount=50000)
    clock.at(t0 - timedelta(days=10))
    pages = [poster(1240, 1748, (25, 25, 35), (90, 200, 220), t, s, d, 80) for t, s, d in [
        ("PACE LABS\nCORPORATE RUN", "Annual wellness run", "15 SEPTEMBER"),
        ("WHY WE\nRUN", "Health · Team · Community", "5K FOR ALL"),
        ("ROUTE", "Futala Lake loop", "START 6:00 AM"),
        ("SEE YOU\nTHERE", "Register by 10 Sept", "PACELABS.IN")]]
    v = version(p5, pdf_from_pages(pages), "pacelabs-brochure.pdf")
    clock.at(t0 - timedelta(days=9))
    view(p5)
    sv.approve(p5, v.id)
    final(p5, pdf_from_pages(pages), "pacelabs-brochure-print.pdf", "Print PDF")
    final(p5, pages[0], "pacelabs-cover.png", "Cover PNG")
    sv.issue_invoice(p5)
    clock.at(t0 - timedelta(days=9, hours=-2))
    pay = sv.submit_payment(p5, "HDFC0042339911")
    sv.confirm_payment(pay)
    pay.decided_at = t0 - timedelta(days=8)
    clock.at(t0 - timedelta(days=8))
    for f in p5.final_files:
        sv.record_download(p5, f)
    clock.at(t0 - timedelta(days=8, hours=-1))
    sv.complete(p5)
    clock.at(t0 - timedelta(days=7))

    # 6. Brief only.
    project(sweets, name="Republic Day Social Pack", project_type="Social Media Pack", width=1080,
            height=1080, format="JPG", quantity=5, deliverable_types="JPG", amount=400000,
            due_date=date.today() + timedelta(days=14), description="5 posts for 26 January.")
    clock.at(now() - timedelta(hours=3))

    Notification.query.update({"read_at": None})
    db.session.commit()

    base = current_app.config["PUBLIC_URL"]
    click.echo("\nDemo data ready.\n")
    click.echo(f"  Admin login:  {DEMO_EMAIL} / {DEMO_PASSWORD}  (change it before going live)\n")
    for p in Project.query.order_by(Project.id).all():
        rt = sv.active_token(p)
        click.echo(f"  {p.code}  {p.status:<20} {p.name:<28} {base}/r/{rt.token}" if rt else
                   f"  {p.code}  {p.status:<20} {p.name}")
    click.echo("")
