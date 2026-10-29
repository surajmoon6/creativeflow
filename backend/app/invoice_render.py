"""An invoice as a PDF or a PNG, drawn the same way as a quotation (see quote_render)."""
import re
from html import escape

import pymupdf

from . import services as sv
from .models import Invoice
from .quote_render import _archive, _block, _css, _date, _lines, story_pdf, story_png
from .serializers import invoice_document, invoice_link
from .services import inr


def _html(doc: dict, has_logo: bool) -> tuple[str, str]:
    b, t, bill = doc["brand"], doc["totals"], doc["bill_to"]
    brand = b["color"] if re.fullmatch(r"#[0-9a-fA-F]{6}", b["color"] or "") else "#4F46E5"
    head = '<img src="logo.png" width="112"/>' if has_logo else f'<span class="brand">{escape(b["name"])}</span>'
    if b["name"] != "CreativeFlow Studio":  # our software's name, under the studio's own brand
        head += '<br/><span class="small muted">CreativeFlow Studio</span>'
    paid = doc["status"] == "paid"

    rows = []
    for it in doc["items"]:
        rate = inr(it["unit_price"]) if it["unit_price"] else ""
        amount = escape(it["note"]) if it["note"] else inr(it["amount"])
        rows.append(f'<tr><td style="width:268px">{escape(it["description"])}</td><td class="r" style="width:44px">{it["quantity"]}</td>'
                    f'<td class="r" style="width:96px">{rate}</td><td class="r b" style="width:107px">{amount}</td></tr>')

    sp = '<td style="width:258px" class="nob"></td>'

    def row(label, value, cls=""):
        return f'<tr>{sp}<td class="{cls or "muted"}" style="width:150px">{label}</td><td class="r {cls}" style="width:107px">{value}</td></tr>'

    total_rows = [row("Subtotal", inr(t["subtotal"]))]
    if t["discount"]:
        total_rows.append(row("Discount", f'− {inr(t["discount"])}'))
    if t["tax_rate_bp"]:
        total_rows.append(row(f'GST {t["tax_rate_bp"] / 100:g}%', inr(t["tax"])))
    total_rows.append(row("Total", inr(t["total"]), "grand"))
    if t["advance_paid"]:
        total_rows.append(row("Advance received", f'− {inr(t["advance_paid"])}'))
        total_rows.append(row("Paid in full" if paid else "Balance due", inr(t["amount_due"]), "b"))

    got = "<br/>".join(f'Received {inr(a["amount"])} on {_date(a["received_on"] + "T00:00:00")}'
                       + (f' &#183; Ref {escape(a["reference"])}' if a["reference"] else "") for a in doc["advances"]) if t["advance_paid"] else ""
    got_html = f'<p class="r small muted">{got}</p>' if got else ""

    stamp = (f'<br/><span class="free b">PAID on {_date(doc["paid_at"])}</span>' if paid and doc["paid_at"] else "")
    notes = _block(f'<h3>Notes</h3><p class="small">{_lines(doc["notes"])}</p>') if doc["notes"] else ""
    terms = _block(f'<h3>Payment terms</h3><p class="small">{_lines(doc["payment_terms"])}</p>') if doc["payment_terms"] and not paid else ""
    pay = doc.get("payment")
    pay_html = (_block(f'<table class="pay" cellspacing="0" cellpadding="0"><tr>'
                f'<td style="width:96px"><img src="pay.png" width="84"/></td>'
                f'<td><span class="b">Pay {inr(t["amount_due"])} by UPI</span><br/>'
                f'<span class="small muted">Scan with any UPI app, or pay to</span><br/>'
                f'<span class="b">{escape(pay["upi_id"])}</span><br/>'
                f'<span class="small muted">{escape(pay["payee"])}. Add {escape(doc["number"])} as the note.</span></td>'
                f'</tr></table>')) if pay else ""
    closing = (_block(f'<p class="small muted">A note from {escape(b["name"])}</p><p>{_lines(doc["closing"])}</p>', "boxed")
               if doc.get("closing") else "")
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
  <td class="r"><span class="h1">Invoice</span><br/>#{escape(doc["number"])}<br/>
     <span class="muted small">Issued {_date(doc["issued_at"])}</span>{stamp}</td>
</tr></table>
<table class="plain gap" cellspacing="0" cellpadding="0"><tr>
  <td width="50%"><span class="muted small">Bill to</span><br/><span class="b">{escape(bill["name"])}</span>{bill_extra}</td>
  <td width="50%"><span class="muted small">Project</span><br/><span class="b">{escape(doc["project"]["name"])}</span><br/><span class="small muted">#{escape(doc["project"]["code"])}</span></td>
</tr></table>
<table class="items" cellspacing="0" cellpadding="0">
  <tr><th style="width:268px">Description</th><th class="r" style="width:44px">Qty</th><th class="r" style="width:96px">Rate</th><th class="r" style="width:107px">Amount</th></tr>
  {"".join(rows)}
</table>
<table class="totals" cellspacing="0" cellpadding="0">{"".join(total_rows)}</table>
{got_html}
{notes}
{terms}
{pay_html}
{closing}
<table class="plain foot" cellspacing="0" cellpadding="0"><tr>
  <td><span class="b">{escape(b["name"])}</span><br/><span class="small muted">{contact}</span></td>
  <td class="r"><img src="qr.png" width="64"/><br/><span class="small muted">Scan to view online</span></td>
</tr></table>
""", brand


def _story(inv: Invoice):
    doc = invoice_document(inv)
    link = invoice_link(inv) or sv.current_app.config["PUBLIC_URL"]
    arc, has_logo = _archive(None, link, doc)
    html, brand = _html(doc, has_logo)
    return pymupdf.Story(html=html, user_css=_css(brand), archive=arc)


def render_pdf(inv: Invoice) -> bytes:
    return story_pdf(_story(inv))


def render_png(inv: Invoice, scale: float = 2.0) -> bytes:
    return story_png(_story(inv), scale)


def filename(inv: Invoice, ext: str) -> str:
    name = re.sub(r"[^\w\- ]+", "", inv.project.name).strip()[:50]
    return f"{inv.number} - {name}.{ext}" if name else f"{inv.number}.{ext}"
