"""A quotation as a PDF or a PNG.

Drawn on the server from the quote's data, so the file looks the same for everyone and needs no browser.
The PNG is one tall image (handy to send on WhatsApp); the PDF is A4 pages with selectable text.
"""
import base64
import io
import re
from html import escape
from pathlib import Path

import pymupdf
import segno
from flask import current_app
from PIL import Image

from . import services as sv
from .services import inr
from .models import Quote
from .serializers import quote_document, quote_link
from .storage import get_storage

FONTS = Path(__file__).parent / "fonts"
A4 = pymupdf.paper_rect("a4")
MARGIN = 40


def _date(iso: str) -> str:
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "")).strftime("%d %b %Y")


def _tint(hex_color: str, k: float = 0.1) -> str:
    """The brand colour mixed with white, for soft panels."""
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(round(255 - (255 - v) * k) for v in (r, g, b))


def _lines(text: str | None) -> str:
    return "<br/>".join(escape(l) for l in (text or "").splitlines())


def _block(html: str, cls: str = "") -> str:
    """A heading and its text as one unbreakable row, so a page break never strands the heading from what it introduces."""
    return f'<table class="plain keep {cls}" cellspacing="0" cellpadding="0"><tr><td class="{"closing" if cls == "boxed" else ""}">{html}</td></tr></table>'


def _lines_html(lines: list[str]) -> str:
    """'# ' a subheading, '> ' a small note, '~ ' a plain paragraph; anything else a bullet."""
    out = ""
    for ln in lines:
        if ln.startswith("# "):
            out += f'<p class="sub">{escape(ln[2:])}</p>'
        elif ln.startswith("> "):
            out += f'<p class="note">{escape(ln[2:])}</p>'
        elif ln.startswith("~ "):
            out += f'<p class="para">{escape(ln[2:])}</p>'
        else:
            out += f'<p class="li">&#8226;&nbsp;&nbsp;{escape(ln)}</p>'
    return out


def _html(q: Quote, doc: dict, link: str, has_logo: bool, appendix_separate: bool = False):
    b, t = doc["brand"], doc["totals"]
    brand = b["color"] if re.fullmatch(r"#[0-9a-fA-F]{6}", b["color"] or "") else "#4F46E5"
    head = '<img src="logo.png" width="112"/>' if has_logo else f'<span class="brand">{escape(b["name"])}</span>'
    if b["name"] != "CreativeFlow Studio":  # our software's name, under the studio's own brand
        head += '<br/><span class="small muted">CreativeFlow Studio</span>'
    bill = doc["bill_to"]

    scope_first = doc.get("scope_first", True)
    mode = doc.get("mode") or ("monthly" if doc.get("billing") == "monthly" else "once")
    monthly, mixed = mode == "monthly", mode == "mixed"
    scope, after, appendix = "", "", ""
    n = 0
    for s in doc.get("sections") or []:
        if s.get("part") == "appendix":
            tone = s.get("tone") or ""
            cls = {"title": "apptitle", "gain": "gain", "caution": "caution"}.get(tone, "sec2")
            appendix += _block(f'<h2 class="{cls}">{escape(s["title"])}</h2>' + _lines_html(s["lines"]))
        elif s.get("part") == "after":
            after += _block(f'<h2 class="sec2">{escape(s["title"])}</h2>' + _lines_html(s["lines"]))
        else:
            n += 1
            lead = '<h3 class="scope">Scope of work</h3>' if n == 1 else ""
            scope += _block(lead + f'<h2 class="sec">{n}. {escape(s["title"])}</h2>' + _lines_html(s["lines"]))

    rows = []
    for it in doc["items"]:
        if it["complimentary"]:
            rate = f'<s class="muted">{inr(it["unit_price"])}</s>' if it["unit_price"] else ""
            amount = '<span class="free">FREE</span>'
            tag = '<br/><span class="free small">Complimentary</span>'
        else:
            rate, amount, tag = inr(it["unit_price"]), inr(it["amount"]), ""
            if it.get("list_price"):  # the standard price crossed out beside the special offer
                rate = f'<s class="muted">{inr(it["list_price"])}</s><br/>{inr(it["unit_price"])}'
                tag = '<br/><span class="free small">Special client offer</span>'
            if mixed:  # one-time and monthly lines side by side: say which is which
                amount += '<br/><span class="small muted">' + ("per month" if it["period"] == "monthly" else "one-time") + '</span>'
        if it.get("detail"):
            tag += f'<br/><span class="small muted">{_lines(it["detail"])}</span>'
        rows.append(f'<tr><td style="width:268px">{escape(it["description"])}{tag}</td><td class="r" style="width:44px">{it["quantity"]}</td>'
                    f'<td class="r" style="width:96px">{rate}</td><td class="r b" style="width:107px">{amount}</td></tr>')

    sp = '<td style="width:258px" class="nob"></td>'
    total_rows = [f'<tr>{sp}<td class="muted" style="width:150px">Subtotal</td><td class="r" style="width:107px">{inr(t["subtotal"])}</td></tr>']
    if t["discount"]:
        dlabel = escape(doc.get("discount_label") or "Discount")
        total_rows.append(f'<tr>{sp}<td class="muted" style="width:150px">{dlabel}</td><td class="r" style="width:107px">− {inr(t["discount"])}</td></tr>')
    if t["tax_rate_bp"]:
        total_rows.append(f'<tr>{sp}<td class="muted" style="width:150px">GST {t["tax_rate_bp"] / 100:g}%</td><td class="r" style="width:107px">{inr(t["tax"])}</td></tr>')
    later = mixed and doc.get("recurring_start") == "launch"
    total_rows.append(f'<tr>{sp}<td class="grand" style="width:150px">{"Total per month" if monthly else ("Initial payment" if later else "Total initial payment") if mixed else "Total"}</td><td class="r grand" style="width:107px">{inr(t["total"])}</td></tr>')
    summary = ""
    if mixed:  # the cost summary: what recurs, what is paid once, and how the first payment adds up
        total_rows = [r for r in total_rows if "Subtotal" not in r]
        total_rows.insert(0, f'<tr>{sp}<td class="b" style="width:150px">Monthly recurring fee</td><td class="r b" style="width:107px">{inr(t["recurring"])}/month</td></tr>')
        total_rows.insert(1, f'<tr>{sp}<td class="muted" style="width:150px">One-time fees</td><td class="r" style="width:107px">{inr(t["one_time"])}</td></tr>')
        if later:
            summary = (f'<p class="small muted">The initial payment is the one-time fees only. The monthly fee of {inr(t["recurring"])} is not charged '
                       f'until the website is launched and the monthly service is activated. It is then payable in advance at the start of each monthly period.</p>')
        elif not t["discount"] and not t["tax_rate_bp"]:
            summary = (f'<p class="small muted">The initial payment is the one-time fees ({inr(t["one_time"])}) plus the first month of '
                       f'recurring services ({inr(t["recurring"])}) = {inr(t["total"])}. From the second month, {inr(t["recurring"])} is payable '
                       f'at the start of each billing cycle.</p>')

    save = (f'<p class="saving">You save {inr(t["complimentary_value"])} with complimentary items.</p>'
            if t["complimentary_value"] else "")
    if t.get("savings_monthly"):
        save += f'<p class="saving">You save {inr(t["savings_monthly"])} every month with the special offer.</p>'
    if t.get("savings_once"):
        save += f'<p class="saving">You save {inr(t["savings_once"])} on the one-time fees with the special offer.</p>'
    if t["discount"] and doc.get("discount_label"):
        save += f'<p class="saving">You save {inr(t["discount"])} every month with this special offer.</p>' if monthly \
            else f'<p class="saving">You save {inr(t["discount"])} with this special offer.</p>'
    rev = doc["revisions_included"]
    cells = [f'<td><span class="muted small">Revisions included</span><br/><span class="b">{rev} for each design</span></td>'] if rev else []
    if t["advance"]:
        cells.append(f'<td><span class="muted small">{"Advance each month" if monthly else "Advance to start the work"}</span><br/>'
                     f'<span class="b">{inr(t["advance"])} ({doc["advance_percent"]}%)</span></td>')
    key_terms = f'<table class="plain terms" cellspacing="0" cellpadding="0"><tr>{"".join(cells)}</tr></table>' if cells else ""
    closing = (_block(f'<p class="small muted">A note from {escape(b["name"])}</p><p>{_lines(doc["closing"])}</p>', "boxed")
               if doc["closing"] else "")
    notes = _block(f'<h3>Notes</h3><p class="small">{_lines(doc["notes"])}</p>') if doc["notes"] else ""
    terms = _block(f'<h3>Terms</h3><p class="small">{_lines(doc["terms"])}</p>') if doc["terms"] else ""
    pay = doc.get("payment")
    pay_html = (_block(f'<table class="pay" cellspacing="0" cellpadding="0"><tr>'
                f'<td style="width:96px"><img src="pay.png" width="84"/></td>'
                f'<td><span class="b">Pay by UPI</span><br/>'
                f'<span class="small muted">Scan with any UPI app, or pay to</span><br/>'
                f'<span class="b">{escape(pay["upi_id"])}</span><br/>'
                f'<span class="small muted">{escape(pay["payee"])}. Add {escape(doc["number"])} as the note.</span></td>'
                f'</tr></table>')) if pay else ""
    contact = " &#183; ".join(escape(x) for x in (b["phone"], b["email"]) if x)
    addr = f'<br/><span class="muted small">{_lines(b["address"])}</span>' if b["address"] else ""
    gstin = f'<br/><span class="muted small">GSTIN {escape(b["gstin"])}</span>' if b["gstin"] else ""
    bill_extra = "".join(f'<br/><span class="small">{escape(x)}</span>' for x in (
        bill["contact"] if bill["contact"] and bill["contact"] != bill["name"] else None,
        bill["address"], f'GSTIN {bill["gstin"]}' if bill["gstin"] else None) if x)

    return f"""
<div class="bar"></div>
<table class="plain" cellspacing="0" cellpadding="0"><tr>
  <td>{head}{addr}{gstin}</td>
  <td class="r"><span class="h1">Quotation</span><br/>#{escape(doc["number"])}<br/>
     <span class="muted small">Date {_date(doc["issued_at"])}</span><br/>
     <span class="b small">Valid until {_date(doc["valid_until"])}</span></td>
</tr></table>
<table class="plain gap" cellspacing="0" cellpadding="0"><tr>
  <td width="50%"><span class="muted small">Prepared for</span><br/><span class="b">{escape(bill["name"])}</span>{bill_extra}</td>
  <td width="50%"><span class="muted small">Project</span><br/><span class="b">{escape(doc["title"])}</span></td>
</tr></table>
{scope if scope_first else ""}
{('<h3 class="scope" style="margin-top:14pt">' + ("Monthly commercials" if monthly else "Pricing") + '</h3>') if scope and scope_first else ""}
<table class="items" cellspacing="0" cellpadding="0" {'style="margin-top:6pt"' if scope and scope_first else ""}>
  <tr><th style="width:268px">Description</th><th class="r" style="width:44px">Qty</th><th class="r" style="width:96px">Rate</th><th class="r" style="width:107px">Amount</th></tr>
  {"".join(rows)}
</table>
<table class="totals" cellspacing="0" cellpadding="0">{"".join(total_rows)}</table>
{save}
{summary}
{key_terms}
{scope if not scope_first else ""}
{after}
{closing}
{notes}
{terms}
{pay_html}
<table class="plain foot" cellspacing="0" cellpadding="0"><tr>
  <td><span class="b">{escape(b["name"])}</span><br/><span class="small muted">{contact}</span></td>
  <td class="r"><img src="qr.png" width="64"/><br/><span class="small muted">Scan to view and accept online</span></td>
</tr></table>
{"" if appendix_separate else '<p style="margin-top:26pt"></p>' + appendix}
""", brand, appendix


def _css(brand: str) -> str:
    return f"""
@font-face {{ font-family: Noto; src: url(NotoSans-Regular.ttf); }}
@font-face {{ font-family: Noto; font-weight: bold; src: url(NotoSans-Bold.ttf); }}
body {{ font-family: Noto; font-size: 9.5pt; color: #15171C; line-height: 1.35; margin: 0; padding: 0; }}
.bar {{ background-color: {brand}; height: 5pt; margin-bottom: 14pt; }}
.brand {{ font-weight: bold; font-size: 15pt; }}
.h1 {{ font-weight: bold; font-size: 22pt; }}
.muted {{ color: #6A7080; }}
.small {{ font-size: 8.5pt; }}
.b {{ font-weight: bold; }}
.r {{ text-align: right; }}
.free {{ color: #17845A; font-weight: bold; }}
table {{ width: 100%; border-collapse: collapse; border-spacing: 0; }}
.gap {{ margin-top: 16pt; margin-bottom: 14pt; }}
td, th {{ vertical-align: top; padding-left: 0; padding-right: 0; }}
.items th {{ text-align: left; font-weight: normal; font-size: 8.5pt; color: #6A7080; padding-bottom: 5pt; border-bottom: 1pt solid #E2E4E9; }}
.items th.r {{ text-align: right; }}
.items td {{ padding-top: 7pt; padding-bottom: 7pt; border-bottom: 0.5pt solid #EDEEF1; }}
.totals {{ margin-top: 8pt; }}
.totals td {{ padding-top: 2pt; padding-bottom: 2pt; }}
.totals td.nob {{ padding: 0; }}
.grand {{ font-weight: bold; font-size: 12pt; padding-top: 6pt; border-top: 1pt solid #15171C; }}
.saving {{ color: #17845A; font-weight: bold; text-align: right; margin-top: 6pt; }}
.terms {{ margin-top: 14pt; }}
.closing {{ border-left: 3pt solid {brand}; padding: 6pt 12pt; }}
.boxed {{ margin-top: 16pt; }}
h3 {{ font-size: 8.5pt; color: #6A7080; font-weight: normal; margin-top: 14pt; margin-bottom: 2pt; }}
.pay {{ margin-top: 16pt; background-color: {_tint(brand, 0.06)}; padding: 8pt 10pt; }}
.scope {{ font-size: 8.5pt; color: #6A7080; font-weight: normal; margin: 4pt 0 0 0; }}
.sec {{ font-size: 11pt; font-weight: bold; color: {brand}; margin: 9pt 0 2pt 0; }}
.sub {{ font-weight: bold; margin: 5pt 0 1pt 0; }}
.para {{ margin: 0 0 3pt 0; }}
.apptitle {{ font-size: 17pt; font-weight: bold; margin: 0 0 4pt 0; }}
.gain {{ font-size: 11pt; font-weight: bold; color: #17845A; margin: 12pt 0 3pt 0; }}
.caution {{ font-size: 11pt; font-weight: bold; color: #A86A0B; margin: 12pt 0 3pt 0; }}
.sec2 {{ font-size: 10.5pt; font-weight: bold; margin: 12pt 0 2pt 0; }}
.li {{ margin: 0 0 0.5pt 0; padding-left: 14pt; text-indent: -10pt; }}
.note {{ color: #6A7080; font-size: 8.5pt; margin: 4pt 0 2pt 0; }}
.foot {{ margin-top: 20pt; border-top: 0.5pt solid #E2E4E9; padding-top: 8pt; }}
"""


def _archive(q: Quote, link: str, doc: dict) -> tuple[pymupdf.Archive, bool]:
    arc = pymupdf.Archive(str(FONTS))
    qr = io.BytesIO()
    segno.make(link, error="m").save(qr, kind="png", scale=6, border=1)
    arc.add(qr.getvalue(), "qr.png")
    pay = doc.get("payment")
    if pay:
        arc.add(base64.b64decode(pay["qr"].split(",", 1)[1]), "pay.png")
    has_logo = False
    from .models import ProjectFile, db
    fid = sv.setting("logo_file_id")
    f = db.session.get(ProjectFile, fid) if fid else None
    if f:
        try:
            with get_storage().open(f.storage_key) as fh:
                out = io.BytesIO()
                Image.open(fh).convert("RGBA").save(out, "PNG")
            arc.add(out.getvalue(), "logo.png")
            has_logo = True
        except Exception:  # noqa: BLE001 — a broken logo must not break the quote
            current_app.logger.warning("quote logo could not be used", exc_info=True)
    return arc, has_logo


def _story(q: Quote, appendix_separate: bool = False):
    """The quote as a Story; with appendix_separate, also a second Story for the closing page(s), so they start on a new page."""
    link = quote_link(q)
    doc = quote_document(q)
    arc, has_logo = _archive(q, link, doc)
    html, brand, appendix = _html(q, doc, link, has_logo, appendix_separate)
    main = pymupdf.Story(html=html, user_css=_css(brand), archive=arc)
    if not appendix_separate:
        return main
    return main, (pymupdf.Story(html=appendix, user_css=_css(brand), archive=arc) if appendix.strip() else None)


def render_pdf(q: Quote) -> bytes:
    main, appendix = _story(q, appendix_separate=True)
    return story_pdf(main, appendix)


def render_png(q: Quote, scale: float = 2.0) -> bytes:
    return story_png(_story(q), scale)


def story_pdf(story, *then) -> bytes:
    """A4 pages from a Story; each Story in `then` starts on a fresh page after it."""
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    where = A4 + (MARGIN, MARGIN, -MARGIN, -MARGIN)
    for st in (story, *[t for t in then if t is not None]):
        more = 1
        while more:
            dev = writer.begin_page(A4)
            more, _ = st.place(where)
            st.draw(dev)
            writer.end_page()
    writer.close()
    return buf.getvalue()


def story_png(story, scale: float = 2.0) -> bytes:
    """One tall page, cropped to its content."""
    tall = pymupdf.Rect(0, 0, A4.width, 6000)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    dev = writer.begin_page(tall)
    _, filled = story.place(tall + (MARGIN, MARGIN, -MARGIN, -MARGIN))
    story.draw(dev)
    writer.end_page()
    writer.close()
    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    clip = pymupdf.Rect(0, 0, A4.width, min(tall.height, pymupdf.Rect(filled).y1 + MARGIN))
    return doc[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False).tobytes("png")


def filename(q: Quote, ext: str) -> str:
    title = re.sub(r"[^\w\- ]+", "", q.title).strip()[:50]
    return f"{q.number} - {title}.{ext}" if title else f"{q.number}.{ext}"
