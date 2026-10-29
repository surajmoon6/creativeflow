"""A demo monthly client: a content calendar with designs, chat messages and a sign-in, to show how it looks.

Added and removed with `flask --app app seed-demo-calendar [--remove]`. It touches only what it creates.
"""
import calendar
import io
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import click
from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from . import services as sv
from .models import ActivityLog, Client, Comment, Notification, Plan, Project, Setting, User, db
from .seed import Clock, Upload

COMPANY = "Spice Route Café"
LOGIN = "neha@spiceroutecafe.example"
PASSWORD = "SpiceRoute-demo-26"
CAFE = "Spice Route Café"

PALETTES = [((178, 60, 38), (245, 170, 60)), ((24, 90, 110), (90, 200, 190)), ((84, 46, 120), (230, 120, 160)),
            ((30, 110, 70), (180, 220, 90)), ((150, 40, 60), (250, 140, 90)), ((40, 60, 130), (120, 170, 250))]


def _font(size):
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def design(title, sub, palette, kind="post", n=1):
    """A simple branded social creative: gradient, a big title and a footer."""
    w, h = (1080, 1920) if kind == "story" else (1080, 1080)
    (r1, g1, b1), (r2, g2, b2) = PALETTES[palette % len(PALETTES)]
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=(int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)))
    px.ellipse([w * 0.55, -h * 0.12, w * 1.25, h * 0.4], outline=(255, 255, 255), width=10)
    px.ellipse([-w * 0.2, h * 0.7, w * 0.35, h * 1.15], fill=(255, 255, 255))
    big = _font(118 if kind != "story" else 132)
    y = int(h * 0.22)
    for line in _wrap(px, title, big, w * 0.82):
        px.text((w * 0.09, y), line, font=big, fill="white")
        y += 138
    px.text((w * 0.09, y + 22), sub, font=_font(46), fill=(255, 244, 230))
    if kind == "reel":
        cx, cy = w * 0.5, h * 0.64
        px.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=(255, 255, 255))
        px.polygon([(cx - 26, cy - 44), (cx - 26, cy + 44), (cx + 50, cy)], fill=PALETTES[palette % len(PALETTES)][0])
    px.text((w * 0.09, h * 0.9), "SPICE ROUTE CAFE", font=_font(44), fill="white")
    if n > 1:
        px.text((w * 0.09, h * 0.84), f"Version {n}", font=_font(34), fill=(255, 244, 230))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# day, time, kind, title, subtitle, platforms, caption, what happens
POSTS = [
    (2, "11:00", "post", "Weekend Brunch is back", "Saturdays and Sundays, 10 am to 2 pm", ["Instagram", "Facebook"],
     "Slow mornings deserve a good table. Brunch is back every weekend at Spice Route Café. #NagpurFoodies #Brunch", "posted"),
    (4, "18:30", "reel", "Chai and samosa, the perfect pair", "A 20 second reel", ["Instagram", "Facebook"],
     "Rainy evening? You know what to order. ☕ #ChaiTime #Nagpur", "posted"),
    (6, "12:00", "carousel", "Meet our head chef", "Chef Anand's three signature dishes", ["Instagram", "LinkedIn"],
     "Meet the hands behind your favourite plates. Swipe to see his three signatures →", "posted"),
    (9, "17:00", "post", "Diwali special thali", "Five curries, three breads, two sweets", ["Instagram", "Facebook"],
     "Celebrate with the Diwali Special Thali, available till the 20th. Book your table today.", "posted"),
    (12, "19:00", "reel", "Behind the kitchen", "How our masala is ground fresh every morning", ["Instagram"],
     "Fresh masala, every single morning. This is why it tastes like home.", "posted-chat"),
    (14, "10:30", "story", "Monsoon menu is live", "Hot soups and crisp pakoras", ["Instagram", "Facebook"],
     "Tap to see the monsoon menu.", "posted"),
    (16, "13:00", "post", "Five stars, again", "What our guests are saying this month", ["Instagram", "Google Business"],
     "Thank you for the love, Nagpur. ⭐⭐⭐⭐⭐", "shared-seen"),
    (20, "18:00", "reel", "Filter coffee Fridays", "Every Friday, a free refill", ["Instagram", "Facebook"],
     "Friday just got better. Free filter coffee refill, all day. ☕", "shared-chat"),
    (23, "19:30", "post", "Live music night", "Saturday, 8 pm, no cover charge", ["Instagram", "Facebook"],
     "Good food, good music. Reserve your table for Saturday night. 🎶", "shared"),
    (25, "11:30", "carousel", "Diwali gift cards", "Give the gift of a great meal", ["Instagram", "Facebook"],
     "Not sure what to gift? A Spice Route gift card is never the wrong answer.", "shared-question"),
    (27, "12:00", "story", "Dessert of the week", "Warm gulab jamun with rabri", ["Instagram"], "Sweet endings.", "planned"),
    (29, "18:00", "post", "Year-end party bookings", "Tables fill up fast. Book early.", ["Instagram", "Facebook"],
     "", "planned-brief"),
]


def _remove():
    row = db.session.get(Setting, "demo_calendar")
    if not row:
        click.echo("No demo calendar to remove.")
        return
    ids = row.value
    storage = Path(current_app.config["STORAGE_DIR"]) / "projects"
    User.query.filter_by(client_id=ids["client"]).delete()
    plan = Plan.query.filter_by(client_id=ids["client"]).first()
    p = db.session.get(Project, ids["project"])
    if plan:
        db.session.delete(plan)
        db.session.flush()
    if p:
        p.approved_version_id = None
        Comment.query.filter_by(project_id=p.id).delete()
        ActivityLog.query.filter_by(project_id=p.id).delete()
        Notification.query.filter_by(project_id=p.id).delete()
        db.session.flush()
        shutil.rmtree(storage / p.code, ignore_errors=True)
        db.session.delete(p)
    db.session.flush()
    c = db.session.get(Client, ids["client"])
    if c and not c.projects:
        db.session.delete(c)
    db.session.delete(row)
    db.session.commit()
    click.echo("Demo calendar removed.")


def run(remove=False):
    if remove:
        return _remove()
    if db.session.get(Setting, "demo_calendar") or Client.query.filter_by(company=COMPANY).first():
        raise click.ClickException("The demo calendar already exists. Remove it first with --remove.")
    today = date.today()
    ym = f"{today.year}-{today.month:02d}"
    last_day = calendar.monthrange(today.year, today.month)[1]
    clock = Clock()

    c = Client(name="Neha Kulkarni", company=COMPANY, email=LOGIN, phone="9800000000", notes="Demo client for the content calendar.")
    db.session.add(c)
    db.session.flush()
    plan = sv.save_plan(c, dict(name="Social media, monthly", monthly_price=1800000, start_date=today.replace(day=1), active=True,
                                revisions_per_post=2, client_approval=False, payment_reminder=True, inclusions=[dict(kind="post", count=5), dict(kind="reel", count=3),
                                                                    dict(kind="carousel", count=2), dict(kind="story", count=2)]))
    user = sv.create_client_login(c, "Neha Kulkarni", LOGIN, PASSWORD, True)
    project = plan.project
    base = datetime.combine(today.replace(day=1), datetime.min.time())

    def upload(d, sub, n=1, note=None, when=None, palette=0):
        data = design(d.title, sub, palette, d.kind, n)
        raw, ext, name = sv.read_upload(Upload(data, f"{d.kind}-{d.id}-v{n}.png"), sv.MASTER_EXTS)
        v = sv.add_version(project, raw, ext, name, note, design=d)
        db.session.flush()
        db.session.refresh(d)  # its versions list is cached; a request would load it fresh
        if when:
            clock.at(when)
        return v

    def say(d, side, name, text, when, seen=True):
        m = sv.add_message(d, side, name, text)
        db.session.flush()
        clock.at(when)
        m.seen_at = (when + timedelta(hours=1)) if seen else None
        return m

    ago = lambda days, hour: datetime.combine(today - timedelta(days=days), datetime.min.time()) + timedelta(hours=hour)
    for i, (day, hhmm, kind, title, sub, plats, caption, plan_for) in enumerate(POSTS):
        day = min(day, last_day)
        d = sv.add_post(plan, dict(title=title, kind=kind, scheduled_at=f"{ym}-{day:02d}T{hhmm}", platforms=plats, caption=caption,
                                   media_url="https://example.com/reel-preview" if kind == "reel" else ""))
        clock.at(base + timedelta(hours=9))
        sched = d.scheduled_at
        made = ago(max((today - sched.date()).days + 3, 1), 11)
        if plan_for == "planned-brief":  # the client has told the studio what they want; no design yet
            ref = Upload(design("Our menu", "Photo from the client", 3, "post"), "party-menu-photo.png")
            sv.save_brief(d, "Year-end party bookings: 3 packages, Rs 799, 999 and 1299 per person. Free dessert for groups of 10 or more. "
                             "Bookings on 98xxxxxx00. Please use our menu photo.", [ref], "Neha Kulkarni")
            db.session.flush()
            clock.at(ago(1, 16))
            continue
        if plan_for == "planned":
            continue
        v = upload(d, sub, 1, "First version, ready for you to see." if i % 2 == 0 else None, made, i)
        d.client_seen_version_id = v.id if plan_for in ("posted", "posted-chat", "shared-seen") else None
        if plan_for in ("posted", "posted-chat"):
            sv.set_posted(d, True)  # no client approval on this plan: sharing the design is enough
            d.posted_at = sched
            clock.at(made + timedelta(hours=5))
        if plan_for == "posted-chat":
            say(d, "client", "Neha Kulkarni", "Loved this one! Can we post it on Thursday evening?", made + timedelta(hours=3))
            say(d, "team", "Priya from the studio", "Thank you! Scheduled for Thursday, 7 pm. 🎉", made + timedelta(hours=4))
        if plan_for == "shared-chat":
            say(d, "client", "Neha Kulkarni", "Please make the price bigger and use the new logo.", ago(3, 15))
            say(d, "team", "Priya from the studio", "Done! The price is bigger and the new logo is in. Version 2 is up for you.", ago(2, 10), seen=False)
            upload(d, sub, 2, "Bigger price, new logo.", ago(2, 10), i)
            d.client_seen_version_id = None
        if plan_for == "shared-question":
            say(d, "client", "Neha Kulkarni", "Can we add 'Valid till 31 December' on the card? Also is it for dine-in only?", ago(0, 8), seen=False)
    db.session.flush()
    clock.at(datetime.now())
    db.session.add(Setting(key="demo_calendar", value=dict(client=c.id, project=project.id, user=user.id)))
    db.session.commit()
    click.echo(f"Demo calendar ready for {COMPANY}.\n  Client sign-in: {LOGIN}\n  Password: {PASSWORD}\n  Open /login and sign in as the client.")
