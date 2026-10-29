"""Showcase data: a believable studio history (past clients, work in every stage) to demo to new clients.

Additive only: it never touches existing rows. Everything it creates is recorded in the `showcase`
setting, so `flask --app app seed-showcase --remove` takes it all out again.
Every project is walked through the real workflow functions, with timestamps back-dated.
"""
import io
import random
import shutil
import zipfile
from datetime import timedelta
from pathlib import Path

import click
from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from . import services as sv
from .models import (ActivityLog, Client, Download, Notification, Project, Quote, QuoteItem, Setting, db, now)
from .security import new_token
from .seed import Clock, Upload

# ---------------------------------------------------------------- designs

def _font(px):
    return ImageFont.load_default(size=max(10, int(px)))


def _clean(text):
    """The built-in font has no rupee sign, en dash or accents."""
    return (text.replace("₹", "Rs.").replace("–", "-").replace("É", "E").replace("é", "e")) if isinstance(text, str) else text


def _fit(d, text, px, max_w):
    """Largest font (up to px) whose widest line fits max_w."""
    while px > 12:
        f = _font(px)
        box = d.multiline_textbbox((0, 0), text, font=f, spacing=int(px * 0.2))
        if box[2] - box[0] <= max_w:
            return f
        px *= 0.94
    return _font(px)


def _grad(w, h, top, bottom):
    img = Image.new("RGB", (w, h), top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bottom)))
    return img


def art(look, w, h, v=1):
    """One creative. `v` is the version number: later versions tweak it the way a real revision would."""
    s = look["style"]
    bg, bg2, acc, ink = look["pal"]
    alts = look.get("alts")
    if alts and v > 1:
        acc = alts[(v - 2) % len(alts)]
    u = min(w, h)
    big = 1 + 0.07 * (v - 1)  # the emphasised line grows a little in each revision
    img = _grad(w, h, bg, bg2)
    d = ImageDraw.Draw(img)
    T, SUB, LINE, FOOT = (_clean(look.get(k, "")) for k in ("title", "sub", "line", "foot"))

    def text(xy, t, px, fill, max_w, **kw):
        d.text(xy, t, font=_fit(d, t, px, max_w), fill=fill, **kw)

    def mtext(xy, t, px, fill, max_w, **kw):
        f = _fit(d, t, px, max_w)
        d.multiline_text(xy, t, font=f, fill=fill, spacing=int(f.size * 0.2), **kw)

    if s == "center":  # festive / offer posts
        cx, cy, r = w // 2, int(h * 0.465), int(u * 0.28)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=acc)
        d.ellipse([cx - int(r * 1.12), cy - int(r * 1.12), cx + int(r * 1.12), cy + int(r * 1.12)],
                  outline=acc, width=max(3, u // 140))
        mtext((cx, cy), T, u / 8, bg, int(r * 1.55), anchor="mm", align="center")
        text((cx, int(h * 0.085)), SUB, u / 26, ink, int(w * 0.86), anchor="mm")
        text((cx, int(h * 0.895)), LINE, u / 13 * big, acc, int(w * 0.86), anchor="mm")
        text((cx, int(h * 0.965)), FOOT, u / 40, ink, int(w * 0.9), anchor="mm")

    elif s == "split":  # offers, ads
        px = int(w * 0.56)
        d.rectangle([px, 0, w, h], fill=acc)
        for i in range(-h, w, max(24, u // 18)):
            d.line([(px + i, h), (px + i + h, 0)], fill=bg2, width=max(2, u // 220))
        cr = int(w * 0.17)
        cx, cy = int(w * 0.78), int(h * 0.3)
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=bg, width=max(6, u // 40))
        lw = int(w * 0.46)
        mtext((int(w * 0.06), int(h * 0.12)), T, u / 8.5, ink, lw)
        text((int(w * 0.06), int(h * 0.56)), SUB, u / 26, ink, lw)
        d.rectangle([0, int(h * 0.7), px, int(h * 0.84)], fill=acc)
        text((int(w * 0.06), int(h * 0.77)), LINE, u / 13 * big, bg, int(w * 0.46), anchor="lm")
        text((int(w * 0.06), int(h * 0.93)), FOOT, u / 38, ink, lw)

    elif s == "banner":  # wide banners, hoardings
        m = u // 20
        d.rectangle([m, m, w - m, h - m], outline=acc, width=max(3, u // 160))
        cx, cy = int(w * 0.78), int(h * 0.5)
        for rr in (0.4, 0.29):
            r = int(h * rr)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=acc, width=max(3, u // 90))
        r = int(h * 0.17)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=acc)
        mtext((cx, cy), _clean(look.get("badge", "")), u / 11, bg, int(r * 1.5), anchor="mm", align="center")
        lw = int(w * 0.5)
        mtext((int(w * 0.08), int(h * 0.18)), T, u / 7.5, ink, lw)
        text((int(w * 0.08), int(h * 0.6)), SUB, u / 20, ink, lw)
        text((int(w * 0.08), int(h * 0.74)), LINE, u / 12 * big, acc, lw)
        text((int(w * 0.08), int(h * 0.88)), FOOT, u / 34, ink, lw)

    elif s == "menu":
        text((w // 2, int(h * 0.09)), T, u / 11, acc, int(w * 0.8), anchor="mm")
        text((w // 2, int(h * 0.15)), SUB, u / 34, ink, int(w * 0.6), anchor="mm")
        d.line([(int(w * 0.2), int(h * 0.185)), (int(w * 0.8), int(h * 0.185))], fill=acc, width=max(2, u // 400))
        items = look["items"]
        half = (len(items) + 1) // 2
        for col, chunk in enumerate((items[:half], items[half:])):
            x = int(w * (0.07 if col == 0 else 0.54))
            for i, (name, price) in enumerate(chunk):
                y = int(h * 0.25) + i * int(h * 0.085)
                d.text((x, y), _clean(name), font=_font(u / 29), fill=ink)
                d.text((x + int(w * 0.39), y), _clean(price), font=_font(u / 29), fill=acc, anchor="ra")
        text((w // 2, int(h * 0.95)), FOOT, u / 40, ink, int(w * 0.8), anchor="mm")

    elif s == "logo":
        cx, cy, r = w // 2, int(h * 0.42), int(u * 0.22)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=acc)
        text((cx, cy), _clean(look["mono"]), r * 1.1, bg, int(r * 1.35), anchor="mm")
        text((cx, int(h * 0.72)), T, u / 11, ink, int(w * 0.86), anchor="mm")
        text((cx, int(h * 0.8)), SUB, u / 36, acc, int(w * 0.8), anchor="mm")

    elif s == "invite":
        m = u // 22
        d.rectangle([m, m, w - m, h - m], outline=acc, width=max(3, u // 180))
        d.rectangle([m * 2, m * 2, w - m * 2, h - m * 2], outline=acc, width=max(1, u // 420))
        text((w // 2, int(h * 0.17)), SUB, u / 28, acc, int(w * 0.7), anchor="mm")
        mtext((w // 2, int(h * 0.42)), T, u / 9, ink, int(w * 0.7), anchor="mm", align="center")
        text((w // 2, int(h * 0.64)), LINE, u / 18 * big, acc, int(w * 0.7), anchor="mm")
        text((w // 2, int(h * 0.76)), FOOT, u / 32, ink, int(w * 0.7), anchor="mm")

    elif s == "page":  # brochure / catalogue / lookbook pages
        d.rectangle([0, 0, w, int(h * 0.16)], fill=acc)
        text((int(w * 0.07), int(h * 0.08)), T, u / 13, bg, int(w * 0.86), anchor="lm")
        d.rectangle([int(w * 0.07), int(h * 0.22), int(w * 0.93), int(h * 0.5)], fill=bg2)
        d.ellipse([int(w * 0.64), int(h * 0.25), int(w * 0.64) + int(w * 0.24), int(h * 0.25) + int(w * 0.24)], fill=acc)
        text((int(w * 0.1), int(h * 0.27)), SUB, u / 20, ink, int(w * 0.5))
        for i, row in enumerate(look.get("items", [])):
            y = int(h * 0.58) + i * int(h * 0.08)
            d.ellipse([int(w * 0.08), y + 8, int(w * 0.08) + 18, y + 26], fill=acc)
            text((int(w * 0.12), y), _clean(row), u / 26, ink, int(w * 0.8))
        text((int(w * 0.07), int(h * 0.94)), FOOT, u / 40, ink, int(w * 0.86))

    elif s == "cover":  # brochure covers
        d.rectangle([0, int(h * 0.66), w, h], fill=acc)
        cr = int(w * 0.25)
        cx, cy = int(w * 0.9), int(h * 0.2)
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=acc, width=max(6, u // 60))
        lw = int(w * 0.5)
        mtext((int(w * 0.08), int(h * 0.12)), T, u / 9, ink, lw)
        text((int(w * 0.08), int(h * 0.5)), SUB, u / 24, ink, int(w * 0.84))
        text((int(w * 0.08), int(h * 0.74)), LINE, u / 14 * big, bg, int(w * 0.84))
        text((int(w * 0.08), int(h * 0.92)), FOOT, u / 38, bg, int(w * 0.84))
    return img


def png(img):
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def jpg(img):
    b = io.BytesIO()
    img.save(b, "JPEG", quality=88)
    return b.getvalue()


def pdf_of(images):
    """Print-style PDF, JPEG-compressed so seeded files stay small."""
    import pymupdf
    doc = pymupdf.open()
    for im in images:
        page = doc.new_page(width=im.width * 0.5, height=im.height * 0.5)
        page.insert_image(page.rect, stream=jpg(im))
    return doc.tobytes(deflate=True)


# ---------------------------------------------------------------- data

JEWEL = ((70, 12, 32), (118, 24, 50), (226, 178, 74), (255, 243, 214))
TEAL = ((232, 246, 246), (196, 230, 235), (22, 140, 152), (14, 62, 72))
CAFE = ((250, 242, 230), (240, 226, 204), (150, 84, 40), (60, 36, 22))
NAVY = ((16, 28, 64), (28, 48, 104), (240, 180, 40), (240, 244, 255))
GREEN = ((16, 56, 44), (28, 88, 66), (236, 190, 70), (238, 250, 240))
ROSE = ((252, 236, 238), (246, 214, 222), (186, 52, 92), (74, 24, 44))
IVORY = ((253, 249, 238), (246, 238, 214), (166, 112, 40), (66, 44, 20))
CHARCOAL = ((24, 26, 32), (44, 48, 58), (255, 94, 58), (244, 244, 246))
SKY = ((228, 242, 255), (190, 222, 250), (36, 112, 214), (16, 40, 84))
MUSTARD = ((255, 246, 214), (252, 232, 166), (214, 92, 30), (74, 36, 14))

CLIENTS = {
    "bhosale": dict(name="Anand Bhosale", company="Bhosale Jewellers", email="anand@bhosalejewellers.example",
                    whatsapp="9822145671", billing_address="Mahal Road, Sitabuldi, Nagpur 440012", gstin="27AAKFB4821L1ZP"),
    "smilecare": dict(name="Dr. Meera Kapoor", company="SmileCare Dental Clinic", email="meera@smilecare.example",
                      whatsapp="9890234100", billing_address="Ramdaspeth, Nagpur 440010", gstin="27AAOPK7712D1Z8"),
    "brew": dict(name="Priya Menon", company="Brew & Bloom Café", email="priya@brewandbloom.example",
                 whatsapp="9763011842", billing_address="Dharampeth, Nagpur 440010", gstin="27ABRPM3350E1ZK"),
    "raut": dict(name="Sandeep Raut", company="Raut Realty", email="sandeep@rautrealty.example",
                 whatsapp="9422678310", billing_address="Wardha Road, Nagpur 440025", gstin="27AAFCR9034B1ZX"),
    "ishi": dict(name="Ishita Agrawal", company="Ishi Boutique", email="ishita@ishiboutique.example",
                 whatsapp="9970123456", billing_address="Sadar, Nagpur 440001"),
    "fitzone": dict(name="Farhan Sheikh", company="FitZone Gym", email="farhan@fitzone.example",
                    whatsapp="9021887766", billing_address="Manish Nagar, Nagpur 440015", gstin="27AAGFF2218K1ZD"),
    "sprouts": dict(name="Tanvi Deshpande", company="Little Sprouts Preschool", email="tanvi@littlesprouts.example",
                    whatsapp="9158002233", billing_address="Bajaj Nagar, Nagpur 440010"),
    "gadkari": dict(name="Manoj Gadkari", company="Gadkari Coaching Classes", email="manoj@gadkariclasses.example",
                    whatsapp="9860554433", billing_address="Laxmi Nagar, Nagpur 440022"),
    "thakre": dict(name="Pooja Thakre", company=None, email="pooja.thakre@mail.example", whatsapp="9604113355"),
}

IG_POST, IG_POSTER, BANNER = ("Instagram Post", (1080, 1080)), ("Instagram Poster", (1080, 1350)), ("Event Banner", (1920, 1080))


def P(client, name, kind, size, amount, stage, ago, look=None, **kw):
    """One project. `ago` = days ago the last event happened. Amount in rupees."""
    return dict(client=client, name=name, type=kind, size=size, amount=amount, stage=stage, ago=ago,
                look=look, **kw)


def L(style, pal, title="", sub="", line="", foot="", **kw):
    return dict(style=style, pal=pal, title=title, sub=sub, line=line, foot=foot, **kw)


SPECS = [
    # ---------- completed work: the track record
    P("fitzone", "New Year Membership Offer", *IG_POST, 1500, "completed", 262,
      L("center", CHARCOAL, "NEW YEAR\nNEW YOU", "FITZONE GYM · MANISH NAGAR", "FLAT 30% OFF", "Valid till 31 January · Call 90218 87766"), gst=True),
    P("ishi", "Boutique Logo", "Logo Design", (1080, 1080), 6500, "completed", 225,
      L("logo", ROSE, "ISHI BOUTIQUE", "DESIGNER WEAR · NAGPUR", mono="I", alts=[(120, 64, 140), (186, 52, 92)]), rounds=2,
      revs=["Can we try a softer pink? The first one feels too bold for a boutique.",
            "Love the colour. Please make the monogram letter slightly smaller inside the circle."], finals="logo"),
    P("smilecare", "Clinic Brochure", "Brochure (4 pages)", (1240, 1748), 9000, "completed", 214,
      pages=[L("cover", TEAL, "SMILECARE\nDENTAL CLINIC", "Gentle care for the whole family", "BOOK A VISIT", "Ramdaspeth, Nagpur"),
             L("page", TEAL, "OUR TREATMENTS", "Everything under one roof", items=["Root canal & fillings", "Braces and aligners", "Teeth whitening", "Kids' dentistry"], foot="smilecare.example"),
             L("page", TEAL, "MEET THE DOCTORS", "20+ years of experience", items=["Dr. Meera Kapoor, BDS, MDS", "Dr. Arjun Rao, Orthodontist", "Painless, modern treatment"], foot="smilecare.example"),
             L("cover", TEAL, "VISIT US", "Mon–Sat · 10 AM to 8 PM", "CALL 98902 34100", "Ramdaspeth, Nagpur 440010")],
      rounds=1, revs=["Please add the clinic timings on the last page and use the second logo version."], gst=True),
    P("thakre", "Wedding Invitation Card", "Invitation", (1080, 1350), 3500, "completed", 196,
      L("invite", IVORY, "POOJA\n&\nVARUN", "TOGETHER WITH THEIR FAMILIES", "21 FEBRUARY 2026", "Hotel Centre Point, Ramdaspeth · 7:30 PM"), rounds=1,
      revs=["Can the date be bigger and in gold? Also change the venue name to 'Hotel Centre Point'."]),
    P("ishi", "Holi Special Offer Post", *IG_POST, 1000, "completed", 206,
      L("center", ROSE, "HOLI\nSALE", "ISHI BOUTIQUE", "UP TO 40% OFF", "4–8 March · Sadar, Nagpur")),
    P("raut", "Green Valley Plots Brochure", "Brochure (6 pages)", (1240, 1748), 14000, "completed", 168,
      pages=[L("cover", GREEN, "GREEN VALLEY\nPLOTS", "NA-converted · Clear title · Wardha Road", "FROM ₹18 LAKH", "Raut Realty"),
             L("page", GREEN, "LOCATION", "10 minutes from the airport", items=["Wide 30 ft internal roads", "Water and drainage ready", "Near school and hospital"], foot="Raut Realty"),
             L("page", GREEN, "PLOT SIZES", "1000 to 2400 sq ft", items=["1000 sq ft  ·  ₹18 lakh", "1500 sq ft  ·  ₹26 lakh", "2400 sq ft  ·  ₹41 lakh"], foot="Raut Realty"),
             L("page", GREEN, "AMENITIES", "Built for families", items=["Landscaped garden", "24x7 security", "Street lighting"], foot="Raut Realty"),
             L("page", GREEN, "PAYMENT PLAN", "Bank loan assistance", items=["10% booking", "Balance on registry", "All major banks approved"], foot="Raut Realty"),
             L("cover", GREEN, "BOOK YOUR\nSITE VISIT", "Free pick-up from the city", "CALL 94226 78310", "Raut Realty · Wardha Road")],
      rounds=3, revs=["Please change the cover photo area to a lighter colour, it looks too dark in print.",
                      "Add the RERA number on every page and fix the price on page 3.",
                      "One more thing: swap pages 4 and 5. Sorry for the late change."], gst=True),
    P("bhosale", "Akshaya Tritiya Offer Banner", *BANNER, 3500, "completed", 160,
      L("banner", JEWEL, "AKSHAYA\nTRITIYA", "Gold · Diamond · Silver", "ZERO MAKING CHARGES", "Bhosale Jewellers · Mahal Road, Sitabuldi", badge="19\nAPR"), gst=True),
    P("brew", "Café Logo & Brand Kit", "Logo & Branding", (1080, 1080), 12000, "completed", 128,
      L("logo", CAFE, "BREW & BLOOM", "CAFÉ · BAKERY · DHARAMPETH", mono="B&B", alts=[(60, 110, 70), (150, 84, 40)]), rounds=2,
      revs=["The brown feels heavy. Can we see a green option too?",
            "Green is better! Please use the dark green with the cream background."], finals="logo", gst=True),
    P("brew", "Menu Card (2 pages)", "Menu", (1240, 1748), 4500, "completed", 100,
      pages=[L("menu", CAFE, "BREW & BLOOM", "COFFEE & BAKES", items=[("Cappuccino", "150"), ("Cold Coffee", "170"), ("Filter Coffee", "90"), ("Hazelnut Latte", "190"),
                                                                       ("Masala Chai", "60"), ("Iced Tea", "120"), ("Brownie", "130"), ("Cheesecake", "180")], foot="Dharampeth · Open 8 AM to 11 PM"),
             L("menu", CAFE, "ALL DAY EATS", "FRESH · LOCAL", items=[("Avocado Toast", "220"), ("Club Sandwich", "210"), ("Pasta Alfredo", "260"), ("Margherita Pizza", "280"),
                                                                    ("Veg Burger", "180"), ("Fries", "110"), ("Garlic Bread", "140"), ("Garden Salad", "190")], foot="GST extra as applicable")],
      rounds=1, revs=["Please increase the price font a little, our customers find it hard to read."], gst=True),
    P("sprouts", "Admission Open Poster 2026-27", *IG_POSTER, 1800, "completed", 84,
      L("center", SKY, "ADMISSIONS\nOPEN", "LITTLE SPROUTS PRESCHOOL", "2026 – 27", "Playgroup · Nursery · Jr. KG · Bajaj Nagar"), rounds=1,
      revs=["Can you add 'Limited seats' and our phone number at the bottom?"]),
    P("gadkari", "NEET Results Banner", *BANNER, 3200, "completed", 70,
      L("banner", NAVY, "OUR STARS\nNEET 2026", "Proud results from Gadkari Classes", "47 SELECTIONS", "Admissions open · Laxmi Nagar, Nagpur", badge="AIR\n312"), rounds=1,
      revs=["Please add 'Congratulations toppers' and make the 47 bigger."]),
    P("fitzone", "Monsoon Fitness Offer", *BANNER, 2200, "completed", 56,
      L("split", CHARCOAL, "MONSOON\nFIT PLAN", "3 months · Free trainer sessions", "₹2,999 ONLY", "FitZone Gym · Manish Nagar"), gst=True),
    P("bhosale", "Rakhi Collection Post Pack", "Social Media Pack (5 posts)", (1080, 1080), 4800, "completed", 40,
      L("center", JEWEL, "RAKHI\nGIFTING", "BHOSALE JEWELLERS", "SILVER FROM ₹1,999", "Mahal Road, Sitabuldi"), rounds=1,
      revs=["Looks good! Please change the offer price to ₹1,799 on all five posts."], gst=True, reject_first=True),
    P("raut", "Skyline Heights Hoarding", "Hoarding (30 × 15 ft)", (1920, 960), 6500, "completed", 31,
      L("banner", NAVY, "SKYLINE\nHEIGHTS", "2 & 3 BHK · RERA registered", "FROM ₹54 LAKH", "Raut Realty · Wardha Road · 94226 78310", badge="NEW\nLAUNCH"), rounds=1,
      revs=["Make the 'From ₹54 lakh' much bigger, it should be readable from the road."], gst=True),
    P("sprouts", "Teachers' Day Greeting", *IG_POST, 900, "completed", 27,
      L("center", SKY, "HAPPY\nTEACHERS' DAY", "LITTLE SPROUTS PRESCHOOL", "5 SEPTEMBER", "With love from our little sprouts")),
    P("brew", "Ganesh Chaturthi Special Menu", *IG_POSTER, 1800, "completed", 17,
      L("center", MUSTARD, "FESTIVE\nTHALI", "BREW & BLOOM CAFÉ", "₹299 ONLY", "14–24 September · Dharampeth"), gst=True),
    P("smilecare", "Dental Camp Flyer", "Flyer (A5)", (1240, 1748), 2500, "delivered", 9,
      L("split", TEAL, "FREE DENTAL\nCHECK-UP CAMP", "Sunday 20 September · 10 AM to 4 PM", "FREE FOR ALL", "SmileCare Dental Clinic · Ramdaspeth"), gst=True),

    # ---------- work in progress: every stage
    P("fitzone", "Festive Fitness Challenge", *IG_POSTER, 2000, "payment_pending", 1,
      L("split", CHARCOAL, "30 DAY\nCHALLENGE", "Win a year's free membership", "JOIN FROM 12 OCT", "FitZone Gym · Manish Nagar"), rounds=1, gst=True, pay_submitted=True,
      revs=["Can we add a prize line: 'Top 3 win free memberships'?"]),
    P("raut", "Skyline Heights Possession Brochure", "Brochure (4 pages)", (1240, 1748), 16000, "paid", 1,
      pages=[L("cover", NAVY, "SKYLINE\nHEIGHTS", "Possession from December 2026", "BOOK YOUR HOME", "Raut Realty · Wardha Road"),
             L("page", NAVY, "FLOOR PLANS", "2 & 3 BHK", items=["2 BHK · 1050 sq ft", "3 BHK · 1480 sq ft", "Vastu compliant"], foot="Raut Realty"),
             L("page", NAVY, "AMENITIES", "Everything within the campus", items=["Clubhouse & gym", "Children's play area", "Covered parking"], foot="Raut Realty"),
             L("cover", NAVY, "VISIT THE\nSAMPLE FLAT", "Open all days · 10 AM to 7 PM", "CALL 94226 78310", "Raut Realty")],
      rounds=1, gst=True, revs=["Please add the possession date on the cover and a QR for the location."]),
    P("smilecare", "Dental Camp Standee", "Standee (3 × 6 ft)", (1080, 1920), 2200, "finalization", 1,
      L("split", TEAL, "SMILE\nCAMP", "Free scaling for first 50 patients", "20 OCT", "SmileCare Dental Clinic"), gst=True),
    P("thakre", "Engagement Invitation", "Invitation", (1080, 1350), 3000, "approved", 1,
      L("invite", ROSE, "POOJA\n&\nVARUN", "ENGAGEMENT CEREMONY", "15 NOVEMBER 2026", "The Orchid Lawns, Wardha Road · 6 PM")),
    P("bhosale", "Diwali Jewellery Collection Banner", *BANNER, 4500, "review", 1,
      L("banner", JEWEL, "DIWALI\nCOLLECTION", "New gold & diamond designs", "ADVANCE BOOKING OPEN", "Bhosale Jewellers · Mahal Road, Sitabuldi", badge="DHAN\nTERAS"), gst=True),
    P("sprouts", "Annual Day Invitation", *IG_POSTER, 2500, "review", 1,
      L("invite", SKY, "ANNUAL DAY\n2026", "LITTLE SPROUTS PRESCHOOL", "12 DECEMBER · 5 PM", "Chief guest: Dr. Rekha Joshi · Bajaj Nagar"), rounds=1,
      revs=["Please add 'Parents are requested to be seated by 4:45 PM' at the bottom."]),
    P("brew", "Winter Menu Update", "Menu", (1240, 1748), 3800, "revision_requested", 1,
      pages=[L("menu", CAFE, "WINTER MENU", "BREW & BLOOM", items=[("Hot Chocolate", "170"), ("Pumpkin Latte", "210"), ("Mulled Chai", "90"), ("Soup of the Day", "160"),
                                                                  ("Mac & Cheese", "260"), ("Apple Crumble", "190"), ("Cinnamon Roll", "140"), ("Tiramisu", "220")], foot="Available from 1 November")],
      rounds=1, gst=True, revs=["Can you move 'Hot Chocolate' to the top? And please make the heading brown, not orange."]),
    P("gadkari", "JEE Batch Admission Flyer", "Flyer (A5)", (1240, 1748), 2800, "design", 1,
      L("split", NAVY, "JEE 2027\nBATCH", "Admissions open", "BATCH STARTS 1 NOV", "Gadkari Classes · Laxmi Nagar")),
    P("ishi", "Navratri Collection Lookbook", "Lookbook (6 pages)", (1240, 1748), 7500, "brief", 0,
      L("cover", ROSE, "NAVRATRI\nEDIT", "", "", "")),
]


# Projects that started from a formal quote (the small WhatsApp-deal posts did not).
QUOTED = {"Clinic Brochure", "Boutique Logo", "Green Valley Plots Brochure", "Akshaya Tritiya Offer Banner",
          "Café Logo & Brand Kit", "Menu Card (2 pages)", "Rakhi Collection Post Pack", "Skyline Heights Hoarding",
          "NEET Results Banner", "Wedding Invitation Card", "Dental Camp Flyer", "Skyline Heights Possession Brochure",
          "Festive Fitness Challenge", "Engagement Invitation", "Diwali Jewellery Collection Banner", "Annual Day Invitation"}

# Quotes that did not (yet) become projects. `sent`/`views` are days ago / view count; `valid` is days from sent.
PIPELINE = [
    dict(client="bhosale", title="Dhanteras Social Media Pack", items=[("Social media post design", 5, 1100), ("Story and reel covers", 3, 600)], gst=True,
         state="sent", sent=6, views=3, valid=15),
    dict(client="fitzone", title="Diwali Membership Campaign", items=[("Instagram poster", 2, 1800), ("Event banner", 1, 3500)], gst=True,
         state="sent", sent=3, views=0, valid=15),
    dict(client="smilecare", title="Clinic Banner and Social Pack", items=[("Clinic banner", 1, 3500), ("Social media post design", 4, 1000)], gst=True,
         state="sent", sent=13, views=1, valid=15),
    dict(client="brew", title="Festive Packaging Labels", items=[("Label design (4 variants)", 4, 1500), ("Print-ready files", 1, 1000)], gst=True,
         state="accepted", sent=4, views=2, valid=15, accepted=1, note="Looks good, please start this week."),
    dict(client="gadkari", title="Results Banner and Hoarding", items=[("Results banner", 1, 3200), ("Hoarding design", 1, 6500)], gst=False,
         state="sent", sent=0.2, views=0, valid=15),
    dict(client="sprouts", title="Admission Campaign 2027", items=[("Admission poster", 1, 1800), ("Social media post design", 3, 900), ("Flyer (A5)", 1, 2200)], gst=False,
         state="draft", sent=0, views=0, valid=15),
    dict(client="raut", title="Brochure 2027 Edition", items=[("Brochure (8 pages)", 1, 16000)], gst=True,
         state="declined", sent=42, views=2, valid=15, answered=40, note="Postponing the campaign to January."),
    dict(client="ishi", title="Reels Cover Pack", items=[("Reel cover design", 10, 400)], gst=False,
         state="declined", sent=72, views=1, valid=15, answered=70, note="Went with a cheaper option."),
    dict(client="bhosale", title="Hoarding for Wedding Season", items=[("Hoarding design (30 x 15 ft)", 1, 7500)], gst=True,
         state="declined", sent=122, views=3, valid=15, answered=118, note="Budget not approved yet."),
    dict(client="gadkari", title="Annual Brochure", items=[("Brochure (6 pages)", 1, 11000)], gst=False,
         state="declined", sent=95, views=2, valid=15, answered=92, note="We'll do it in-house this year."),
    dict(client="ishi", title="Lookbook Layout", items=[("Lookbook design (8 pages)", 1, 9500)], gst=False,
         state="sent", sent=22, views=2, valid=15),
    dict(client="fitzone", title="Summer Offer Banner Set", items=[("Banner design", 3, 2200)], gst=True,
         state="sent", sent=62, views=0, valid=15),
    dict(client="smilecare", title="Clinic Signage Design", items=[("Signboard design", 1, 5500), ("Window vinyl artwork", 1, 2500)], gst=True,
         state="sent", sent=47, views=1, valid=15),
]


# Quotes that include a free Instagram story (shown as FREE with its Rs. 100 value).
FREE_STORY = {"Dhanteras Social Media Pack", "Diwali Membership Campaign", "Festive Packaging Labels", "Clinic Banner and Social Pack",
              "Results Banner and Hoarding", "Admission Campaign 2027", "Green Valley Plots Brochure", "Akshaya Tritiya Offer Banner",
              "Café Logo & Brand Kit", "Rakhi Collection Post Pack", "Diwali Jewellery Collection Banner", "Festive Fitness Challenge"}
FREE_ITEM = ("Instagram story design", 1, 100, True)


def _quote_items(spec):
    """Line items that add up to the project's amount."""
    amt, pages = spec["amount"], spec.get("pages")
    if "Social Media Pack" in spec["type"] and amt % 5 == 0:
        return [("Social media post design", 5, amt // 5)]
    if pages and len(pages) > 1:
        cover = int(amt * 0.4) // 100 * 100
        return [("Cover design", 1, cover), (f"Inner pages ({len(pages) - 1} pages)", 1, amt - cover)]
    if amt >= 6000:
        main = int(amt * 0.75) // 100 * 100
        return [("Concept and design", 1, main), ("Final files and two revisions", 1, amt - main)]
    return [(f"{spec['type']} design", 1, amt)]


def _make_quote(client, title, items, gst, created, valid_until, notes=None):
    q = Quote(number=sv.next_quote_number(), token=new_token(), client=client, title=title, status="draft",
              gst_enabled=gst, gst_rate_bp=1800, notes=notes, terms=sv.setting("quote_terms"),
              closing=sv.default_closing(client.name),
              valid_until=valid_until, created_at=created, updated_at=created, events=[])
    for d, n, price, *free in items:
        q.items.append(QuoteItem(description=d, quantity=n, unit_price=price * 100, complimentary=bool(free and free[0])))
    if title in FREE_STORY:
        q.items.append(QuoteItem(description=FREE_ITEM[0], quantity=1, unit_price=FREE_ITEM[2] * 100, complimentary=True))
    db.session.add(q)
    db.session.flush()
    _qev(q, created, "Quote created")
    return q


def _qev(q, at, text):
    q.events = [*q.events, dict(at=at.isoformat() + "Z", text=text)]


def _quote_story(q, sent, views, answered=None, accepted=None, note=None, project=None, rng=None):
    """Sent at `sent`, opened `views` times, optionally answered. All times explicit."""
    q.status, q.sent_at = "sent", sent
    _qev(q, sent, "Quote sent to client")
    if views:
        t = sent + timedelta(hours=rng.uniform(1, 6))
        q.first_viewed_at = t
        _qev(q, t, "Client opened the quote")
        q.views, q.last_viewed_at = views, min(t + timedelta(hours=rng.uniform(0, 40) * (views > 1)), now())
    if answered or accepted:
        t = accepted or answered
        q.status = "accepted" if accepted else "declined"
        q.responded_at, q.response_note = t, note
        _qev(q, t, f"Client {'accepted' if accepted else 'declined'} the quote" + (f': "{note}"' if note else ""))
    if project:
        q.project_id = project.id
        _qev(q, project.created_at, f"Project {project.code} created")


def _quotes(made, stories, clients, T, ids):
    """Quotations: one behind each quoted project, plus a pipeline in every state."""
    rng = random.Random("quotes")
    ts = []  # (created, builder) so numbering follows time

    for spec, times in stories:
        if spec["name"] not in QUOTED:
            continue
        p, start = made[spec["name"]], times[0][1]
        accepted = start - timedelta(hours=rng.uniform(2, 20))
        created = accepted - timedelta(days=rng.uniform(1.5, 4))
        sent = created + timedelta(hours=rng.uniform(1, 5))

        def build(spec=spec, p=p, created=created, sent=sent, accepted=accepted):
            q = _make_quote(clients[spec["client"]], spec["name"], _quote_items(spec), bool(spec.get("gst")), created,
                            sent.date() + timedelta(days=15), notes="Delivery within 5 working days of approval.")
            q.discount = p.discount
            _quote_story(q, sent, rng.randint(1, 4), accepted=accepted, project=p, rng=rng)
            return q
        ts.append((created, build))

    for d in PIPELINE:
        sent = T - timedelta(days=d["sent"])
        created = sent - timedelta(hours=rng.uniform(1, 20)) if d["state"] != "draft" else T - timedelta(hours=5)

        def build(d=d, created=created, sent=sent):
            q = _make_quote(clients[d["client"]], d["title"], d["items"], d["gst"], created,
                            sent.date() + timedelta(days=d["valid"]), notes=d.get("notes"))
            if d["state"] != "draft":
                kw = {}
                if d["state"] == "accepted":
                    kw["accepted"] = T - timedelta(days=d["accepted"], hours=rng.uniform(0, 5))
                if d["state"] == "declined":
                    kw["answered"] = T - timedelta(days=d["answered"])
                _quote_story(q, sent, d["views"], note=d.get("note"), rng=rng, **kw)
                if d["state"] == "accepted":  # recent news: the bell shows it
                    db.session.add(Notification(quote_id=q.id, event="quote_accepted", created_at=q.responded_at,
                                                message=f"{q.client.display_name} accepted quotation {q.number}"))
            return q
        ts.append((created, build))

    for _, build in sorted(ts, key=lambda x: x[0]):
        ids["quotes"].append(build().id)


# ---------------------------------------------------------------- story engine

GAPS = dict(first=(1, 4), view=(1, 6), revision=(0.5, 4), version=(18, 30), approve=(1, 5), finals=(1, 3), invoice=(0.2, 1),
            submit=(3, 40), reject=(2, 10), confirm=(1, 6), download=(1, 20), complete=(24, 120), design=(2, 6))


def plan(spec):
    """Event list with hours-from-start. Pure and deterministic."""
    rng = random.Random(spec["name"])
    st, rounds = spec["stage"], spec.get("rounds", 0)
    ev, t = [("created", 0.0)], 0.0

    def add(name, gap=None):
        nonlocal t
        t += rng.uniform(*GAPS[gap or name])
        ev.append((name, t))

    def version():
        add("version", "first" if len(ev) == 1 else None)

    if st == "brief":
        return ev
    if st == "design":
        add("design")
        return ev
    for _ in range(rounds):
        version()
        add("view")
        add("revision")
    if st == "revision_requested":
        return ev
    version()
    add("view")
    if st == "review":
        return ev
    add("approve")
    if st == "approved":
        return ev
    add("finals")
    if st == "finalization":
        return ev
    add("invoice")
    if spec.get("reject_first"):
        add("submit"), add("reject")
    if st == "payment_pending" and not spec.get("pay_submitted"):
        return ev
    add("submit")
    if st == "payment_pending":
        return ev
    add("confirm")
    if st == "paid":
        return ev
    add("download")
    if st == "delivered":
        return ev
    add("download"), add("complete")
    return ev


def _slug(name):
    return "-".join(name.lower().replace("&", "and").replace("'", "").split())[:40]


def finals_for(spec, v, pages):
    """[(label, bytes, filename)] for the deliverables."""
    slug = _slug(spec["name"])
    w, h = spec["size"]
    if pages:
        return [("Print PDF", pdf_of(pages), f"{slug}-print.pdf"), ("Cover PNG", png(pages[0]), f"{slug}-cover.png")]
    im = art(spec["look"], w, h, v)
    if spec.get("finals") == "logo":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{slug}-primary.png", png(im))
            z.writestr(f"{slug}-small.png", png(im.resize((w // 2, h // 2))))
        return [("Logo PNG", png(im), f"{slug}.png"), ("Logo PDF", pdf_of([im]), f"{slug}.pdf"),
                ("Brand kit (ZIP)", buf.getvalue(), f"{slug}-brand-kit.zip")]
    return [("JPG", jpg(im), f"{slug}.jpg"), ("PNG", png(im), f"{slug}.png")]


def run(remove=False):
    if remove:
        return _remove()
    if db.session.get(Setting, "showcase"):
        click.echo("Showcase data is already loaded. Remove it first with: flask --app app seed-showcase --remove")
        return

    T = now()
    clock = Clock()
    notif_mark = Clock._max(Notification)
    counters = ("project_next", "invoice_next", "quote_next")
    ids = dict(clients=[], projects=[], quotes=[], counters_before={k: sv.setting(k) for k in counters})

    # Plan every project, align each story so its last event lands `ago` days before now.
    stories = []
    for spec in SPECS:
        ev = plan(spec)
        end = T - timedelta(days=spec["ago"], hours=random.Random(spec["name"] + "h").uniform(0, 5))
        origin = end - timedelta(hours=ev[-1][1])
        # business hours (UTC 04:00-12:00 is 09:30-17:30 IST) for the first event
        origin = origin.replace(hour=4 + (origin.hour % 8), minute=origin.minute)
        times = [(n, min(origin + timedelta(hours=h), T - timedelta(minutes=5))) for n, h in ev]
        stories.append((spec, times))
    stories.sort(key=lambda s: s[1][0][1])

    past = [s for s in stories if s[0]["stage"] in ("completed", "delivered")]
    codes = {s[0]["name"]: f"CF-{1001 + i}" for i, s in enumerate(past)}
    inv_no = {}
    for i, s in enumerate(sorted(past, key=lambda s: next(t for n, t in s[1] if n == "invoice"))):
        inv_no[s[0]["name"]] = f"INV-{1001 + i}"

    clients = {}
    for key, kw in CLIENTS.items():
        first = min(s[1][0][1] for s in stories if s[0]["client"] == key)
        c = Client(**kw)
        c.created_at = first - timedelta(days=2)
        db.session.add(c)
        db.session.flush()
        clients[key] = c
        ids["clients"].append(c.id)

    made = {}
    for spec, times in stories:
        made[spec["name"]] = _tell(spec, times, clients[spec["client"]], codes.get(spec["name"]),
                                   inv_no.get(spec["name"]), clock, T, ids)
    _quotes(made, stories, clients, T, ids)

    # Older client activity is already "read"; only the last couple of days stay unread.
    Notification.query.filter(Notification.id > notif_mark, Notification.created_at < T - timedelta(days=2)) \
        .update({"read_at": T - timedelta(days=2)})
    ids["counters_after"] = {k: sv.setting(k) for k in counters}
    sv.set_setting("showcase", ids)
    db.session.commit()

    click.echo(f"\nShowcase data loaded: {len(ids['clients'])} clients, {len(ids['projects'])} projects, "
               f"{len(ids['quotes'])} quotes.")
    click.echo("Remove it any time with: flask --app app seed-showcase --remove\n")


def _tell(spec, times, client, code, invoice_number, clock, T, ids):
    """Walk one project through the real workflow, back-dating as we go."""
    rng = random.Random(spec["name"] + "s")
    w, h = spec["size"]
    pages_spec = spec.get("pages")
    start = times[0][1]
    p = Project(client=client, code=code or sv.next_project_code(), name=spec["name"], project_type=spec["type"],
                width=w, height=h, format="PDF" if pages_spec else "JPG + PNG", quantity=1,
                deliverable_types="Print PDF, PNG" if pages_spec else "JPG, PNG", amount=spec["amount"] * 100,
                gst_enabled=bool(spec.get("gst")), gst_rate_bp=1800, revisions_included=2,
                extra_revision_price=50000, payment_terms=sv.setting("payment_terms"),
                created_at=start, updated_at=start)
    db.session.add(p)
    db.session.flush()
    ids["projects"].append(p.id)
    sv.log_activity(p, "admin", "created", "Project created")
    clock.at(start)

    revs = iter(spec.get("revs", []))
    nver, pay, last, downloaded = 0, None, start, 0

    def render(v):
        return [art(pg, w, h, v) for pg in pages_spec] if pages_spec else art(spec["look"], w, h, v)

    for name, t in times[1:]:
        last = t
        if name == "design":
            sv.start_design(p)
        elif name == "version":
            nver += 1
            imgs = render(nver)
            data, ext = (pdf_of(imgs), "pdf") if pages_spec else (png(imgs), "png")
            data, ext, fname = sv.read_upload(Upload(data, f"{_slug(spec['name'])}-v{nver}.{ext}"), sv.MASTER_EXTS)
            sv.add_version(p, data, ext, fname, "Updated as per your feedback." if nver > 1 else None)
        elif name == "view":
            rt = sv.active_token(p)
            first = rt.first_viewed_at is None
            sv.touch_link(rt)
            rt.views += rng.randint(0, 3)
            if first:
                rt.first_viewed_at = t
            rt.last_viewed_at = t
        elif name == "revision":
            sv.request_revision(p, next(revs))
        elif name == "approve":
            sv.approve(p, p.latest_version.id)
            p.approved_at = t
        elif name == "finals":
            for label, data, fname in finals_for(spec, nver, render(nver) if pages_spec else None):
                d, ext, nm = sv.read_upload(Upload(data, fname), sv.FINAL_EXTS)
                sv.add_final(p, d, ext, nm, label)
        elif name == "invoice":
            saved = sv.setting("invoice_next")
            inv = sv.issue_invoice(p)
            if invoice_number:  # past work keeps its original, lower numbers
                inv.number = invoice_number
                sv.set_setting("invoice_next", saved)
                ActivityLog.query.filter_by(project_id=p.id, event="invoice_generated") \
                    .update({"message": f"Invoice {invoice_number} generated"})
        elif name == "submit":
            pay = sv.submit_payment(p, str(rng.randint(10**11, 10**12 - 1)))
        elif name == "reject":
            sv.reject_payment(pay, "We couldn't find this reference in our account yet. Please check the UTR and resubmit.")
            pay.decided_at = t
        elif name == "confirm":
            sv.confirm_payment(pay)
            pay.decided_at, p.invoice.paid_at, p.paid_at = t, t, t
            exp = t + timedelta(days=30)
            p.delivery_expires_at = exp if exp > T else None  # old deliveries stay downloadable in the demo
        elif name == "download":
            files = p.final_files[:1] if downloaded == 0 else p.final_files[1:]
            for f in files:
                sv.record_download(p, f)
            if downloaded == 0:
                p.delivered_at = t
            downloaded += 1
        elif name == "complete":
            sv.complete(p)
        clock.at(t)
    p.updated_at = last
    return p


def _remove():
    row = db.session.get(Setting, "showcase")
    if not row:
        click.echo("No showcase data to remove.")
        return
    ids = row.value
    storage = Path(current_app.config["STORAGE_DIR"]) / "projects"
    qids = ids.get("quotes", [])
    for q in Quote.query.filter(Quote.id.in_(qids)).all():
        db.session.delete(q)
    Notification.query.filter(Notification.quote_id.in_(qids)).delete(synchronize_session=False)
    db.session.flush()
    for p in Project.query.filter(Project.id.in_(ids["projects"])).all():
        p.approved_version_id = None
        db.session.flush()
        Download.query.filter_by(project_id=p.id).delete()
        ActivityLog.query.filter_by(project_id=p.id).delete()
        Notification.query.filter_by(project_id=p.id).delete()
        shutil.rmtree(storage / p.code, ignore_errors=True)
        db.session.delete(p)
    db.session.flush()
    kept = 0
    for c in Client.query.filter(Client.id.in_(ids["clients"])).all():
        if c.projects or Quote.query.filter_by(client_id=c.id).first():  # you've added your own work for this client since
            kept += 1
        else:
            db.session.delete(c)
    after = ids.get("counters_after")
    if after and {k: sv.setting(k) for k in after} == after:  # nothing new since: give the numbers back
        for k, v in ids["counters_before"].items():
            sv.set_setting(k, v)
    db.session.delete(row)
    db.session.commit()
    click.echo(f"Showcase data removed.{f' Kept {kept} client(s) that now have your own projects.' if kept else ''}")
