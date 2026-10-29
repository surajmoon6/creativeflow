import io
import time

from app.models import ReviewToken, db
from app.preview import generate_previews
from tests.conftest import approved_project_with_invoice, png


# ---------- authentication / authorisation ----------

def test_admin_endpoints_require_login(anon):
    for url in ["/api/dashboard", "/api/clients", "/api/projects", "/api/settings", "/api/payments",
                "/api/admin/files/1"]:
        assert anon.get(url).status_code == 401, url
    assert anon.post("/api/clients", json={"name": "x"}).status_code == 401


def test_bad_password_rejected(anon):
    r = anon.post("/api/auth/login", json={"email": "admin@test.local", "password": "nope"})
    assert r.status_code == 401


def test_mutations_require_csrf_token(admin):
    r = admin.c.post("/api/clients", json={"name": "No CSRF"})
    assert r.status_code == 403 and r.json["code"] == "csrf"
    assert admin.post("/api/clients", {"name": "With CSRF"}).status_code == 201


def test_login_is_rate_limited(app, anon):
    app.config["RATELIMIT_ENABLED"] = True
    codes = [anon.post("/api/auth/login", json={"email": "x@y.z", "password": "bad"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 401  # a few typos are fine; it takes a long run of wrong guesses to be refused
    more = [anon.post("/api/auth/login", json={"email": "x@y.z", "password": "bad"}).status_code for _ in range(10)]
    assert more[-1] == 429


def test_client_token_cannot_reach_admin_api(admin, anon):
    p = admin.new_project()
    token = admin.upload_version(p["id"])["active_link"]["token"]
    assert anon.get(f"/api/r/{token}").status_code == 200
    assert anon.get(f"/api/projects/{p['id']}").status_code == 401


# ---------- preview generation ----------

def test_preview_is_smaller_watermarked_jpeg():
    original = png(1080, 1350)
    [(jpg, w, h)] = generate_previews(original, "png", ["CLIENT REVIEW COPY", "ABC · #CF-1"])
    assert jpg[:3] == b"\xff\xd8\xff"
    assert (w, h) == (972, 1215) and max(w, h) <= 1800  # sharp, but never the full original
    assert w < 1080 and h < 1350
    from PIL import Image
    pixels = Image.open(io.BytesIO(jpg)).convert("RGB").getcolors(1 << 20)
    assert len(pixels) > 50  # a flat colour image gained watermark detail


def test_pdf_preview_has_one_image_per_page(admin):
    import pymupdf
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    p = admin.new_project()
    d = admin.upload_version(p["id"], doc.tobytes(), "brochure.pdf")
    assert d["versions"][0]["pages"] == 3


def test_upload_rejects_wrong_type_and_spoofed_content(admin):
    p = admin.new_project()
    r = admin.post(f"/api/projects/{p['id']}/versions", data={"file": (io.BytesIO(b"MZ..."), "x.exe")})
    assert r.status_code == 400
    r = admin.post(f"/api/projects/{p['id']}/versions",
                   data={"file": (io.BytesIO(b"<script>alert(1)</script>"), "fake.png")})
    assert r.status_code == 400


def test_client_never_gets_master_bytes(admin, anon):
    original = png()
    p = admin.new_project()
    d = admin.upload_version(p["id"], original)
    token, vid = d["active_link"]["token"], d["versions"][0]["id"]
    view = anon.get(f"/api/r/{token}").json
    assert "master" not in str(view) and "storage" not in str(view) and "internal" not in str(view)
    img = anon.get(f"/api/r/{token}/versions/{vid}/pages/1")
    assert img.status_code == 200 and img.data != original and img.mimetype == "image/jpeg"


# ---------- review tokens ----------

def test_expired_and_revoked_links(app, admin, anon):
    p = admin.new_project()
    d = admin.upload_version(p["id"])
    link = d["active_link"]
    with app.app_context():
        rt = db.session.get(ReviewToken, link["id"])
        from datetime import timedelta
        from app.models import now
        rt.expires_at = now() - timedelta(minutes=1)
        db.session.commit()
    r = anon.get(f"/api/r/{link['token']}")
    assert r.status_code == 410 and "expired" in r.json["error"]

    d = admin.post(f"/api/projects/{p['id']}/review-links", {"expiry": "7d"}).json
    new = d["active_link"]
    assert anon.get(f"/api/r/{new['token']}").status_code == 200
    admin.post(f"/api/review-links/{new['id']}/revoke")
    r = anon.get(f"/api/r/{new['token']}")
    assert r.status_code == 410 and r.json["error"] == "This review link is no longer active."
    assert anon.get("/api/r/not-a-real-token").status_code == 404


# ---------- revisions / approval ----------

def test_revision_cycle_and_approval_rules(admin, anon):
    p = admin.new_project()
    d = admin.upload_version(p["id"])
    token = d["active_link"]["token"]
    v1 = anon.get(f"/api/r/{token}").json["deliverables"][0]["latest_version_id"]

    r = anon.post(f"/api/r/{token}/revisions", json={"body": "Please make the date larger."})
    assert r.status_code == 200 and r.json["status"] == "revision_requested"
    # Can't approve while the studio is working on changes.
    assert anon.post(f"/api/r/{token}/approve", json={"version_id": v1}).status_code == 409

    d = admin.get(f"/api/projects/{p['id']}").json
    assert d["versions"][0]["comments"][0]["body"] == "Please make the date larger."
    d = admin.upload_version(p["id"], png(color=(9, 9, 9)), note="Bigger date")
    assert d["status"] == "review" and len(d["versions"]) == 2
    v2 = d["versions"][-1]["id"]

    # Approving a stale version is refused.
    assert anon.post(f"/api/r/{token}/approve", json={"version_id": v1}).json["code"] == "stale"
    r = anon.post(f"/api/r/{token}/approve", json={"version_id": v2})
    assert r.status_code == 200 and r.json["status"] == "approved"

    r = anon.post(f"/api/r/{token}/revisions", json={"body": "One more change"})
    assert r.status_code == 409
    assert r.json["error"] == ("Creative has already been approved. Contact the studio if additional "
                               "changes are required.")
    # Admin can't upload a version to an approved project without reopening.
    r = admin.post(f"/api/projects/{p['id']}/versions", data={"file": (io.BytesIO(png()), "v3.png")})
    assert r.status_code == 409
    assert admin.post(f"/api/projects/{p['id']}/actions/reopen").json["status"] == "in_design"


def test_extra_revisions_are_flagged_and_invoiced(admin, anon):
    p = admin.new_project(revisions_included=1, extra_revision_price=50000, gst_enabled=False)
    token = admin.upload_version(p["id"])["active_link"]["token"]
    anon.post(f"/api/r/{token}/revisions", json={"body": "first change"})
    admin.upload_version(p["id"])
    anon.post(f"/api/r/{token}/revisions", json={"body": "second change"})
    d = admin.upload_version(p["id"])
    assert [c["is_extra"] for v in d["versions"] for c in v["comments"]] == [False, True]
    anon.post(f"/api/r/{token}/approve", json={"version_id": d["versions"][-1]["id"]})
    admin.upload_final(p["id"], png(), "f.png", "PNG")
    inv = admin.post(f"/api/projects/{p['id']}/invoice").json["invoice"]
    assert inv["total"] == 150000 + 50000


# ---------- invoice ----------

def test_invoice_calculation_with_gst_and_discount(admin, anon):
    d, _, _ = approved_project_with_invoice(admin, anon)
    inv = d["invoice"]
    assert (inv["subtotal"], inv["tax"], inv["total"]) == (150000, 27000, 177000)  # ₹1,500 + 18% = ₹1,770

    d, _, _ = approved_project_with_invoice(admin, anon, client_name="Other", discount=20000,
                                           amount=100000, gst_rate_bp=1800)
    inv = d["invoice"]
    assert (inv["discount"], inv["tax"], inv["total"]) == (20000, 14400, 94400)


def test_invoice_needs_final_files(admin, anon):
    p = admin.new_project()
    token = admin.upload_version(p["id"])["active_link"]["token"]
    vid = anon.get(f"/api/r/{token}").json["deliverables"][0]["latest_version_id"]
    anon.post(f"/api/r/{token}/approve", json={"version_id": vid})
    assert admin.post(f"/api/projects/{p['id']}/invoice").status_code == 409


# ---------- payment & delivery (the important ones) ----------

def test_unpaid_project_never_returns_final_files(admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    fid = d["finals"][0]["id"]
    r = anon.post(f"/api/r/{token}/files/{fid}/link")
    assert r.status_code == 403
    assert r.json["error"] == "Final files are available after payment confirmation."
    assert anon.get(f"/api/r/{token}").json["delivery"] is None


def test_client_submitted_payment_does_not_unlock_files(admin, anon):
    """'Fake frontend payment success' — the client saying they paid changes nothing until the studio confirms."""
    d, token, _ = approved_project_with_invoice(admin, anon)
    fid = d["finals"][0]["id"]
    r = anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"},
                  content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["status"] == "payment_pending"
    assert r.json["payment"]["pending"]["status"] == "submitted"
    assert anon.post(f"/api/r/{token}/files/{fid}/link").status_code == 403
    # Client can't reach the admin confirm endpoint.
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    assert anon.post(f"/api/payments/{pay_id}/confirm").status_code == 401
    # Duplicate submission blocked.
    r = anon.post(f"/api/r/{token}/payments", data={"reference": "999999999"},
                  content_type="multipart/form-data")
    assert r.status_code == 409


def test_rejected_payment_allows_retry(admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    anon.post(f"/api/r/{token}/payments", data={"reference": "WRONG123"}, content_type="multipart/form-data")
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    admin.post(f"/api/payments/{pay_id}/reject", {"note": "Not found in bank statement"})
    view = anon.get(f"/api/r/{token}").json
    assert view["status"] == "payment_pending" and view["payment"]["last_rejected"]
    r = anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"},
                  content_type="multipart/form-data")
    assert r.status_code == 200


def test_confirmed_payment_unlocks_signed_download_and_logs_it(admin, anon):
    d, token, final = approved_project_with_invoice(admin, anon)
    fid = d["finals"][0]["id"]
    anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    assert admin.post(f"/api/payments/{pay_id}/confirm").json["status"] == "confirmed"
    assert anon.get(f"/api/r/{token}").json["status"] == "paid"

    url = anon.post(f"/api/r/{token}/files/{fid}/link").json["url"]
    assert "storage" not in url and ".png" not in url
    r = anon.get(url)
    assert r.status_code == 200 and r.data == final
    assert "attachment" in r.headers["Content-Disposition"]
    detail = admin.get(f"/api/projects/{d['id']}").json
    assert detail["status"] == "delivered" and len(detail["downloads"]) == 1
    assert any(a["event"] == "downloaded" for a in detail["activity"])

    # Tampered signature → 404
    assert anon.get(url[:-3] + "abc").status_code == 404


def test_user_a_cannot_access_user_b_files(admin, anon):
    a, token_a, _ = approved_project_with_invoice(admin, anon, client_name="Client A")
    b, token_b, _ = approved_project_with_invoice(admin, anon, client_name="Client B", name="B project")
    for d, tok in ((a, token_a), (b, token_b)):
        anon.post(f"/api/r/{tok}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
        pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
        admin.post(f"/api/payments/{pay_id}/confirm")

    b_file = b["finals"][0]["id"]
    b_version = b["versions"][0]["id"]
    # A's token + B's ids → not found, never B's bytes.
    assert anon.post(f"/api/r/{token_a}/files/{b_file}/link").status_code == 404
    assert anon.get(f"/api/r/{token_a}/versions/{b_version}/pages/1").status_code == 404
    # A's own file works.
    assert anon.post(f"/api/r/{token_a}/files/{a['finals'][0]['id']}/link").status_code == 200


def test_revoking_link_kills_issued_download_urls(admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    admin.post(f"/api/payments/{pay_id}/confirm")
    url = anon.post(f"/api/r/{token}/files/{d['finals'][0]['id']}/link").json["url"]
    admin.post(f"/api/review-links/{d['active_link']['id']}/revoke")
    assert anon.get(url).status_code == 410


def test_signed_download_url_expires(app, admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    admin.post(f"/api/payments/{pay_id}/confirm")
    url = anon.post(f"/api/r/{token}/files/{d['finals'][0]['id']}/link").json["url"]
    app.config["DOWNLOAD_LINK_TTL"] = 0
    time.sleep(1.1)
    assert anon.get(url).status_code == 410


def test_max_downloads_enforced(app, admin, anon):
    admin.put("/api/settings", {"max_downloads": 1})
    d, token, _ = approved_project_with_invoice(admin, anon)
    anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    admin.post(f"/api/payments/{pay_id}/confirm")
    fid = d["finals"][0]["id"]
    assert anon.get(anon.post(f"/api/r/{token}/files/{fid}/link").json["url"]).status_code == 200
    assert anon.post(f"/api/r/{token}/files/{fid}/link").status_code == 403


def test_finals_cannot_be_removed_after_payment(admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
    pay_id = admin.get(f"/api/projects/{d['id']}").json["payments"][0]["id"]
    admin.post(f"/api/payments/{pay_id}/confirm")
    r = admin.c.delete(f"/api/files/{d['finals'][0]['id']}", headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 409


def test_storage_rejects_path_traversal(tmp_path):
    import pytest
    from app.storage import LocalStorage
    s = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        s.save_bytes("../../etc/evil", b"x")


def test_security_headers(anon):
    r = anon.get("/api/brand")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_activity_log_covers_journey(admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    events = {a["event"] for a in admin.get(f"/api/projects/{d['id']}").json["activity"]}
    assert {"created", "version_uploaded", "preview_generated", "link_opened", "approved",
            "invoice_generated"} <= events




# ---------- watermark switch ----------

def _client_preview_colors(anon, token, view=None):
    from PIL import Image
    view = view or anon.get(f"/api/r/{token}?quiet=1").json
    r = anon.get(f"/api/r/{token}/versions/{view['deliverables'][0]['latest_version_id']}/pages/1")
    assert r.status_code == 200
    return len(Image.open(io.BytesIO(r.data)).convert("RGB").getcolors(1 << 20))


def test_watermark_can_be_switched_off_and_on(admin, anon):
    p = admin.new_project()
    d = admin.upload_version(p["id"])  # a flat-colour image: any detail in the preview is watermark
    token = d["active_link"]["token"]
    assert d["watermark"] is True
    assert _client_preview_colors(anon, token) > 50
    assert anon.get(f"/api/r/{token}?quiet=1").json["watermarked"] is True

    d = admin.post(f"/api/projects/{p['id']}/watermark", {"enabled": False}).json
    assert d["watermark"] is False and d["preview_rev"] == 1
    view = anon.get(f"/api/r/{token}?quiet=1").json
    assert view["watermarked"] is False and view["preview_rev"] == 1
    assert _client_preview_colors(anon, token, view) < 10  # clean: no watermark detail

    # versions uploaded while it is off stay clean too
    d = admin.upload_version(p["id"], png(1080, 1350, (200, 10, 10)))
    assert len(d["versions"]) == 2
    assert _client_preview_colors(anon, token) < 10

    d = admin.post(f"/api/projects/{p['id']}/watermark", {"enabled": True}).json
    assert d["watermark"] is True and d["preview_rev"] == 2
    assert _client_preview_colors(anon, token) > 50
    msgs = [a["message"] for a in d["activity"]]
    assert any("Watermark turned off" in m for m in msgs) and any("Watermark turned on" in m for m in msgs)


def test_watermark_switch_is_admin_only_and_validated(admin, anon):
    p = admin.new_project()
    admin.upload_version(p["id"])
    assert anon.post(f"/api/projects/{p['id']}/watermark", json={"enabled": False}).status_code == 401
    r = admin.c.post(f"/api/projects/{p['id']}/watermark", json={"enabled": False})  # no CSRF header
    assert r.status_code == 403
    assert admin.post(f"/api/projects/{p['id']}/watermark", {"enabled": "no"}).status_code == 400
    assert admin.get(f"/api/projects/{p['id']}").json["watermark"] is True


def test_watermark_switch_rerenders_every_pdf_page(admin, anon):
    import pymupdf
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page()
    p = admin.new_project()
    d = admin.upload_version(p["id"], doc.tobytes(), "brochure.pdf")
    token = d["active_link"]["token"]
    admin.post(f"/api/projects/{p['id']}/watermark", {"enabled": False})
    view = anon.get(f"/api/r/{token}?quiet=1").json
    assert view["deliverables"][0]["versions"][0]["pages"] == 2
    for page in (1, 2):
        assert anon.get(f"/api/r/{token}/versions/{view['deliverables'][0]['latest_version_id']}/pages/{page}").status_code == 200


# ---------- audit fixes ----------

def test_quiet_refresh_does_not_count_as_a_view(admin, anon):
    d = admin.upload_version(admin.new_project()["id"])
    token = d["active_link"]["token"]
    anon.get(f"/api/r/{token}")
    for _ in range(5):
        anon.get(f"/api/r/{token}?quiet=1")
    assert admin.get(f"/api/projects/{d['id']}").json["active_link"]["views"] == 1


def test_only_final_file_cannot_be_removed_once_invoice_is_out(admin, anon):
    d, _, _ = approved_project_with_invoice(admin, anon)
    r = admin.c.delete(f"/api/files/{d['finals'][0]['id']}", headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 409
    assert len(admin.get(f"/api/projects/{d['id']}").json["finals"]) == 1


def test_price_cannot_change_while_invoice_is_out(admin, anon):
    d, _, _ = approved_project_with_invoice(admin, anon)
    body = dict(client_id=d["client"]["id"], name=d["name"], project_type=d["project_type"],
                amount=999900, gst_enabled=True, gst_rate_bp=1800, revisions_included=2,
                extra_revision_price=50000)
    assert admin.put(f"/api/projects/{d['id']}", body).status_code == 409
    body["amount"] = 150000  # unchanged price: other edits still work
    body["description"] = "updated"
    assert admin.put(f"/api/projects/{d['id']}", body).status_code == 200


def test_bad_query_numbers_do_not_crash_admin_lists(admin):
    assert admin.get("/api/activity?limit=abc").status_code == 400
    assert admin.get("/api/projects?client_id=x").status_code == 400


# ---------- showcase data ----------

def test_showcase_loads_realistic_history_and_removes_cleanly(app, admin, anon):
    from collections import Counter

    from app.models import (ActivityLog, Client, Download, Notification, Payment, Project, ProjectFile, Quote,
                            QuoteItem, now)
    from app.services import active_token, quote_totals, setting
    from app.showcase import SPECS, run

    mine = admin.new_project(client_name="My Real Client", name="My Real Project")
    admin.upload_version(mine["id"])

    def counts():
        return {m.__name__: m.query.count() for m in (Client, Project, ProjectFile, ActivityLog, Notification, Quote, QuoteItem)}

    with app.app_context():
        before = counts()
        counters = (setting("project_next"), setting("invoice_next"), setting("quote_next"))
        run()
        run()  # a second call is a no-op
        projects = Project.query.filter(Project.id != mine["id"]).all()
        assert len(projects) == len(SPECS)

        stages = Counter(p.status for p in projects)
        assert stages["completed"] >= 10 and stages["review"] >= 2 and stages["payment_pending"] >= 1
        assert {"brief_received", "in_design", "revision_requested", "approved", "finalization",
                "paid", "delivered"} <= set(stages)
        assert Payment.query.filter_by(status="submitted").count() == 1  # one awaiting the studio's confirmation
        assert Payment.query.filter_by(status="rejected").count() == 1

        for p in projects:
            if p.status in ("completed", "delivered"):
                assert p.paid_at and p.invoice.status == "paid" and p.invoice.paid_at == p.paid_at
                assert Download.query.filter_by(project_id=p.id).count() >= 1
            assert p.created_at <= p.updated_at <= now()
            assert max(a.created_at for a in ActivityLog.query.filter_by(project_id=p.id)) <= now()
        assert len({p.code for p in projects}) == len(projects)
        numbers = [p.invoice.number for p in projects if p.invoice]
        assert len(set(numbers)) == len(numbers)
        assert min(p.code for p in projects) == "CF-1001"  # past work keeps the lower numbers
        tokens = [active_token(p).token for p in projects if p.versions]  # no link until the first upload
        assert len(tokens) == len(projects) - 2  # the brief and design-stage projects have no link yet

        # the one revision beyond the included ones is billed as an extra
        quotes = Quote.query.all()
        by_state = Counter(q.effective_status for q in quotes)
        assert by_state["accepted"] >= 15 and by_state["declined"] >= 4 and by_state["expired"] >= 3
        assert by_state["sent"] >= 3 and by_state["draft"] == 1
        assert len({q.number for q in quotes}) == len(quotes)
        for q in quotes:
            if q.project:  # a quote that became a project adds up to it
                assert quote_totals(q)["subtotal"] == q.project.amount and q.status == "accepted"
        assert sum(1 for q in quotes if q.status == "accepted" and not q.project_id) == 1  # waiting to be converted
        assert all(q.closing and "Thank you for considering" in q.closing for q in quotes)
        assert sum(1 for q in quotes if any(i.complimentary for i in q.items)) >= 10  # many include a free story
        extra = [p for p in projects if p.invoice and any(i.description == "Additional revisions" for i in p.invoice.items)]
        assert len(extra) == 1
        for p in projects:
            if p.invoice:
                assert any(a.message == f"Invoice {p.invoice.number} generated" for a in ActivityLog.query.filter_by(project_id=p.id))

    d = admin.get("/api/dashboard").json
    assert d["stats"]["active"] >= 10 and d["needs_attention"]
    assert {x["reason"] for x in d["quotes"]} >= {"Accepted. Create the project", "Not opened yet", "Viewed, no reply yet"}
    for t in tokens:
        view = anon.get(f"/api/r/{t}?quiet=1")
        assert view.status_code == 200
        if view.json["deliverables"][0]["latest_version_id"]:
            assert anon.get(f"/api/r/{t}/versions/{view.json['deliverables'][0]['latest_version_id']}/pages/1").status_code == 200

    with app.app_context():
        run(remove=True)
        assert counts() == before
        assert (setting("project_next"), setting("invoice_next"), setting("quote_next")) == counters
    assert admin.get(f"/api/projects/{mine['id']}").status_code == 200


# ---------- quotations ----------

def _quote_body(client_id, **kw):
    body = dict(client_id=client_id, title="Diwali campaign creatives", gst_enabled=True, gst_rate_bp=1800, discount=50000,
                items=[dict(description="Instagram poster", quantity=3, unit_price=150000),
                       dict(description="Event banner", quantity=1, unit_price=350000)])
    body.update(kw)
    return body


def _new_quote(admin, **kw):
    c = admin.post("/api/clients", {"name": "Rohit", "company": "ABC Events", "whatsapp": "9822012345"}).json
    r = admin.post("/api/quotes", _quote_body(c["id"], **kw))
    assert r.status_code == 201, r.json
    return r.json


def test_quote_totals_numbering_and_validation(admin):
    q = _new_quote(admin)
    assert q["number"] == "QUO-1001" and q["status"] == "draft"
    t = q["document"]["totals"]  # 3 x 1500 + 3500 = 8000, less 500 = 7500, GST 18% = 1350
    assert (t["subtotal"], t["discount"], t["tax"], t["total"]) == (800000, 50000, 135000, 885000)
    assert admin.post("/api/quotes", _quote_body(q["client_id"])).json["number"] == "QUO-1002"
    bad = [dict(items=[]), dict(title=""), dict(discount=9_999_999), dict(discount=-1),
           dict(items=[dict(description="", quantity=1, unit_price=100)]),
           dict(items=[dict(description="x", quantity=0, unit_price=100)]),
           dict(valid_until="2000-01-01")]
    for patch in bad:
        assert admin.post("/api/quotes", _quote_body(q["client_id"], **patch)).status_code == 400, patch


def test_quote_link_is_private_until_sent_then_tracks_views(admin, anon):
    q = _new_quote(admin)
    token = q["share"]["link"].rsplit("/", 1)[1]
    assert anon.get(f"/api/q/{token}").status_code == 404  # a draft is not reachable
    assert admin.post(f"/api/quotes/{q['id']}/send").json["status"] == "sent"
    assert admin.post(f"/api/quotes/{q['id']}/send").json["status"] == "sent"  # sharing again changes nothing
    v = anon.get(f"/api/q/{token}").json
    assert v["can_respond"] and v["document"]["totals"]["total"] == 885000
    assert "events" not in v and "id" not in v  # nothing internal reaches the client
    anon.get(f"/api/q/{token}")
    anon.get(f"/api/q/{token}?quiet=1")
    d = admin.get(f"/api/quotes/{q['id']}").json
    assert d["views"] == 2 and d["first_viewed_at"]
    assert [e["text"] for e in d["events"]].count("Client opened the quote") == 1
    assert any("opened quotation" in n["message"] for n in admin.get("/api/notifications").json["items"])
    assert anon.get("/api/q/not-a-real-token").status_code == 404


def test_client_accepts_once_and_it_locks_the_quote(admin, anon):
    q = _new_quote(admin)
    token = q["share"]["link"].rsplit("/", 1)[1]
    admin.post(f"/api/quotes/{q['id']}/send")
    r = anon.post(f"/api/q/{token}/accept", json={"note": "Please start this week."})
    assert r.status_code == 200 and r.json["status"] == "accepted" and not r.json["can_respond"]
    assert anon.post(f"/api/q/{token}/accept", json={}).status_code == 409
    assert anon.post(f"/api/q/{token}/decline", json={}).status_code == 409
    d = admin.get(f"/api/quotes/{q['id']}").json
    assert d["status"] == "accepted" and d["response_note"] == "Please start this week."
    assert any("accepted quotation" in n["message"] for n in admin.get("/api/notifications").json["items"])
    body = _quote_body(q["client_id"], title="changed")
    assert admin.put(f"/api/quotes/{q['id']}", body).status_code == 409  # accepted quotes are locked
    assert admin.c.delete(f"/api/quotes/{q['id']}", headers={"X-CSRF-Token": admin.csrf}).status_code == 409


def test_decline_then_reopen_and_expiry(app, admin, anon):
    from datetime import date, timedelta

    from app.models import Quote, db
    q = _new_quote(admin)
    token = q["share"]["link"].rsplit("/", 1)[1]
    admin.post(f"/api/quotes/{q['id']}/send")
    assert anon.post(f"/api/q/{token}/decline", json={"note": "Over budget"}).json["status"] == "declined"
    assert admin.post(f"/api/quotes/{q['id']}/status", {"action": "reopen"}).json["status"] == "sent"

    with app.app_context():  # let the validity run out
        db.session.get(Quote, q["id"]).valid_until = date.today() - timedelta(days=1)
        db.session.commit()
    v = anon.get(f"/api/q/{token}?quiet=1").json
    assert v["status"] == "expired" and not v["can_respond"]
    assert anon.post(f"/api/q/{token}/accept", json={}).status_code == 409
    assert admin.get("/api/quotes").json[0]["status"] == "expired"
    # extending the date brings it back to life
    body = _quote_body(q["client_id"], valid_until=(date.today() + timedelta(days=5)).isoformat())
    assert admin.put(f"/api/quotes/{q['id']}", body).json["status"] == "sent"


def test_studio_can_record_an_answer_given_by_phone(admin):
    q = _new_quote(admin)
    admin.post(f"/api/quotes/{q['id']}/send")
    d = admin.post(f"/api/quotes/{q['id']}/status", {"action": "accept", "note": "Confirmed on call"}).json
    assert d["status"] == "accepted" and "You accepted the quote" in d["events"][-1]["text"]
    assert admin.post(f"/api/quotes/{q['id']}/status", {"action": "nonsense"}).status_code == 400


def test_accepted_quote_becomes_a_project_once(admin):
    q = _new_quote(admin)
    assert admin.post(f"/api/quotes/{q['id']}/convert").status_code == 409  # not accepted yet
    admin.post(f"/api/quotes/{q['id']}/send")
    admin.post(f"/api/quotes/{q['id']}/status", {"action": "accept"})
    r = admin.post(f"/api/quotes/{q['id']}/convert")
    assert r.status_code == 200
    p = admin.get(f"/api/projects/{r.json['project_id']}").json
    assert (p["name"], p["amount"], p["discount"], p["gst_enabled"], p["status"]) == \
        ("Diwali campaign creatives", 800000, 50000, True, "brief_received")
    assert p["total"] == 885000 and p["client"]["id"] == q["client_id"]
    assert "Instagram poster × 3" in p["description"]
    assert r.json["quote"]["project"]["code"] == p["code"]
    assert admin.post(f"/api/quotes/{q['id']}/convert").status_code == 409  # never twice


def test_duplicate_delete_and_admin_only(admin, anon):
    q = _new_quote(admin)
    d = admin.post(f"/api/quotes/{q['id']}/duplicate").json
    assert d["status"] == "draft" and d["number"] != q["number"] and d["total"] == q["total"]
    assert admin.c.delete(f"/api/quotes/{d['id']}", headers={"X-CSRF-Token": admin.csrf}).status_code == 200
    assert admin.get(f"/api/quotes/{d['id']}").status_code == 404
    for method, url in (("get", "/api/quotes"), ("post", "/api/quotes"), ("get", f"/api/quotes/{q['id']}"),
                        ("post", f"/api/quotes/{q['id']}/send"), ("post", f"/api/quotes/{q['id']}/convert")):
        assert getattr(anon, method)(url).status_code == 401, url


def test_whatsapp_message_and_template_safety(admin):
    from app.services import inr, render_template
    q = _new_quote(admin)
    m = q["share"]["message"]
    assert "QUO-1001" in m and "₹8,850" in m and q["share"]["link"] in m
    assert q["share"]["whatsapp_number"] == "919822012345"
    assert inr(12345600) == "₹1,23,456" and inr(150) == "₹1.50" and inr(100000) == "₹1,000"
    assert render_template("Hi {client} {unknown}", client="A") == "Hi A {unknown}"
    assert render_template("bad {", client="A") == "bad {"
    # a custom template with an unknown placeholder must not break sharing
    assert admin.put("/api/settings", {"wa_quote": "Hi {client}, {oops} {link}"}).status_code == 200
    assert admin.get(f"/api/quotes/{q['id']}").status_code == 200


def test_dashboard_flags_quotes_that_need_action(admin):
    q = _new_quote(admin)
    admin.post(f"/api/quotes/{q['id']}/send")
    admin.post(f"/api/quotes/{q['id']}/status", {"action": "accept"})
    d = admin.get("/api/dashboard").json
    assert [x["reason"] for x in d["quotes"]] == ["Accepted. Create the project"]


# ---------- quote downloads, complimentary items, closing message ----------

def _free_quote(admin, **kw):
    items = [dict(description="Instagram poster", quantity=2, unit_price=150000),
             dict(description="Instagram story design", quantity=1, unit_price=10000, complimentary=True)]
    return _new_quote(admin, items=items, discount=0, gst_enabled=False, **kw)


def test_complimentary_item_shows_its_value_but_costs_nothing(admin):
    q = _free_quote(admin)
    doc = q["document"]
    free = [i for i in doc["items"] if i["complimentary"]]
    assert len(free) == 1 and free[0]["amount"] == 0 and free[0]["value"] == 10000
    t = doc["totals"]
    assert t["subtotal"] == 300000 and t["total"] == 300000 and t["complimentary_value"] == 10000
    # discount is limited by what is actually charged, never by the free items
    r = admin.post("/api/quotes", _quote_body(q["client_id"], items=[
        dict(description="Free extra", quantity=1, unit_price=500000, complimentary=True),
        dict(description="Paid", quantity=1, unit_price=100000)], discount=200000))
    assert r.status_code == 400
    # all-free quotes are allowed and total nothing
    r = admin.post("/api/quotes", _quote_body(q["client_id"], discount=0, items=[
        dict(description="Gift", quantity=1, unit_price=10000, complimentary=True)]))
    assert r.status_code == 201
    assert r.json["total"] == 0 and r.json["document"]["totals"]["complimentary_value"] == 10000


def test_closing_message_defaults_edits_and_copies(admin):
    q = _new_quote(admin)
    assert "Thank you for considering CreativeFlow Studio, Rohit!" in q["document"]["closing"]
    custom = admin.post("/api/quotes", _quote_body(q["client_id"], closing="See you soon!")).json
    assert custom["document"]["closing"] == "See you soon!"
    none = admin.post("/api/quotes", _quote_body(q["client_id"], closing="")).json
    assert none["document"]["closing"] is None  # an empty message is respected
    copy = admin.post(f"/api/quotes/{custom['id']}/duplicate").json
    assert copy["document"]["closing"] == "See you soon!"
    # the default can be changed in Settings and uses {client} and {studio}
    assert admin.put("/api/settings", {"quote_closing": "Hello {client} from {studio}!"}).status_code == 200
    assert admin.post("/api/quotes", _quote_body(q["client_id"])).json["document"]["closing"] == "Hello Rohit from CreativeFlow Studio!"


def test_complimentary_items_survive_copy_and_conversion(admin):
    q = _free_quote(admin)
    copy = admin.post(f"/api/quotes/{q['id']}/duplicate").json
    assert [i["complimentary"] for i in copy["document"]["items"]] == [False, True]
    admin.post(f"/api/quotes/{q['id']}/send")
    admin.post(f"/api/quotes/{q['id']}/status", {"action": "accept"})
    pid = admin.post(f"/api/quotes/{q['id']}/convert").json["project_id"]
    p = admin.get(f"/api/projects/{pid}").json
    assert p["amount"] == 300000  # the free item adds nothing to the price
    assert "Instagram story design × 1 (complimentary)" in p["description"]


def test_quote_downloads_as_pdf_and_png(admin, anon):
    import io

    import pymupdf
    from PIL import Image
    q = _free_quote(admin)
    token = q["share"]["link"].rsplit("/", 1)[1]
    pdf = admin.get(f"/api/quotes/{q['id']}/download?format=pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf" and pdf.data[:5] == b"%PDF-"
    assert "QUO-1001" in pdf.headers["Content-Disposition"] and ".pdf" in pdf.headers["Content-Disposition"]
    text = pymupdf.open(stream=pdf.data, filetype="pdf")[0].get_text()
    for expected in ("Quotation", "QUO-1001", "₹3,000", "FREE", "Complimentary", "You save ₹100", "Thank you for considering"):
        assert expected in text, expected
    png = admin.get(f"/api/quotes/{q['id']}/download?format=png")
    assert png.status_code == 200 and png.mimetype == "image/png"
    w, h = Image.open(io.BytesIO(png.data)).size
    assert w > 1000 and h > w * 0.8
    assert admin.get(f"/api/quotes/{q['id']}/download").mimetype == "application/pdf"  # pdf is the default
    assert admin.get(f"/api/quotes/{q['id']}/download?format=exe").status_code == 400

    # the client can download too, but only once it has been sent
    assert anon.get(f"/api/q/{token}/download?format=pdf").status_code == 404
    admin.post(f"/api/quotes/{q['id']}/send")
    assert anon.get(f"/api/q/{token}/download?format=pdf").data[:5] == b"%PDF-"
    assert anon.get(f"/api/q/{token}/download?format=png").status_code == 200
    assert anon.get(f"/api/quotes/{q['id']}/download").status_code == 401  # the studio route stays private


def test_long_quote_pdf_paginates_and_png_stays_one_image(admin):
    import io

    import pymupdf
    from PIL import Image
    c = admin.post("/api/clients", {"name": "Big Client"}).json
    items = [dict(description=f"Design item {i} with a fairly long description to wrap", quantity=2, unit_price=15000) for i in range(28)]
    q = admin.post("/api/quotes", _quote_body(c["id"], items=items, discount=0)).json
    pdf = admin.get(f"/api/quotes/{q['id']}/download?format=pdf").data
    assert pymupdf.open(stream=pdf, filetype="pdf").page_count >= 2
    img = Image.open(io.BytesIO(admin.get(f"/api/quotes/{q['id']}/download?format=png").data))
    assert img.size[1] > 2000


# ---------- payment QR on quotes and invoices ----------

UPI = "demo@upi"
PAYEE = "Demo Studio"


def test_upi_links_are_exact():
    from app.services import upi_uri
    assert upi_uri(UPI, PAYEE, note="QUO-1001") == \
        "upi://pay?pa=demo@upi&pn=Demo%20Studio&cu=INR&tn=QUO-1001"
    assert upi_uri(UPI, PAYEE, 177000, "CF-1042 INV-1042") == \
        "upi://pay?pa=demo@upi&pn=Demo%20Studio&am=1770.00&cu=INR&tn=CF-1042%20INV-1042"


def test_quote_shows_payment_qr_only_when_upi_is_set_up(admin, anon):
    import io

    import pymupdf
    q = _new_quote(admin)
    assert q["document"]["payment"] is None  # nothing configured yet
    pdf = admin.get(f"/api/quotes/{q['id']}/download?format=pdf").data
    assert "Pay by UPI" not in pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()

    assert admin.put("/api/settings", {"upi_id": UPI, "upi_payee_name": PAYEE}).status_code == 200
    d = admin.get(f"/api/quotes/{q['id']}").json["document"]["payment"]
    assert d["upi_id"] == UPI and d["payee"] == PAYEE
    assert d["uri"] == f"upi://pay?pa=demo@upi&pn=Demo%20Studio&cu=INR&tn={q['number']}"
    assert d["qr"].startswith("data:image/png;base64,") and len(d["qr"]) > 500

    text = pymupdf.open(stream=admin.get(f"/api/quotes/{q['id']}/download?format=pdf").data, filetype="pdf")[0].get_text()
    assert "Pay by UPI" in text and UPI in text and q["number"] in text

    # the client sees it too, once the quote is sent
    token = q["share"]["link"].rsplit("/", 1)[1]
    admin.post(f"/api/quotes/{q['id']}/send")
    assert anon.get(f"/api/q/{token}?quiet=1").json["document"]["payment"]["upi_id"] == UPI


def test_invoice_qr_carries_the_exact_amount_and_reference(admin, anon):
    d, token, _ = approved_project_with_invoice(admin, anon)
    assert admin.put("/api/settings", {"upi_id": UPI, "upi_payee_name": PAYEE}).status_code == 200
    uri = anon.get(f"/api/r/{token}/upi-uri").json["uri"]
    assert uri == (f"upi://pay?pa=demo@upi&pn=Demo%20Studio&am={d['invoice']['total'] / 100:.2f}"
                   f"&cu=INR&tn={d['code']}%20{d['invoice']['number']}")
    assert anon.get(f"/api/r/{token}/payment-qr.png").mimetype == "image/png"


# ---------- several designs in one project ----------

def _upload(admin, pid, design_id=None, color=(20, 40, 90), name="d.png"):
    import io
    data = {"file": (io.BytesIO(png(1080, 1080, color)), name)}
    if design_id:
        data["deliverable_id"] = str(design_id)
    return admin.post(f"/api/projects/{pid}/versions", data=data)


def _project_with_designs(admin, titles=("Banner", "Standee", "Instagram post"), **kw):
    p = admin.new_project(name="Diwali campaign", **kw)
    first = p["deliverables"][0]
    admin.c.put(f"/api/deliverables/{first['id']}", json={"title": titles[0]}, headers={"X-CSRF-Token": admin.csrf})
    for t in titles[1:]:
        r = admin.post(f"/api/projects/{p['id']}/deliverables", {"title": t})
        assert r.status_code == 200, r.json
    return admin.get(f"/api/projects/{p['id']}").json


def test_every_project_starts_with_one_design_named_after_it(admin):
    p = admin.new_project(name="Nagpur Marathon")
    assert [(d["title"], d["status"]) for d in p["deliverables"]] == [("Nagpur Marathon", "pending")]


def test_old_projects_get_their_first_design_with_their_versions(app, admin):
    from app import _backfill
    from app.models import Deliverable, Project, ProjectVersion, db
    p = admin.new_project()
    admin.upload_version(p["id"])
    with app.app_context():  # make the project look like it predates designs
        ProjectVersion.query.update({"deliverable_id": None, "seq": None})
        Deliverable.query.delete()
        db.session.commit()
        _backfill(set())
        d = Deliverable.query.one()
        assert d.status == "review" and d.title == "Nagpur Marathon 2026"
        assert [(v.deliverable_id, v.seq) for v in ProjectVersion.query.all()] == [(d.id, 1)]
        _backfill(set())  # running it again changes nothing
        assert Deliverable.query.count() == 1


def test_designs_are_reviewed_and_approved_one_by_one(admin, anon):
    p = _project_with_designs(admin, revisions_included=1)
    banner, standee, post = (d["id"] for d in p["deliverables"])
    assert _upload(admin, p["id"]).status_code == 400  # three designs: say which one
    for did, color in ((banner, (200, 10, 10)), (standee, (10, 200, 10)), (post, (10, 10, 200))):
        assert _upload(admin, p["id"], did, color).status_code == 200
    d = admin.get(f"/api/projects/{p['id']}").json
    assert d["status"] == "review" and len(d["versions"]) == 3
    assert [v["number"] for v in d["versions"]] == [1, 1, 1]  # numbered within each design
    token = d["active_link"]["token"]
    view = anon.get(f"/api/r/{token}?quiet=1").json
    assert [x["title"] for x in view["deliverables"]] == ["Banner", "Standee", "Instagram post"]
    ver = {x["title"]: x["latest_version_id"] for x in view["deliverables"]}

    # approving one design leaves the project in review
    assert anon.post(f"/api/r/{token}/approve", json={"version_id": ver["Banner"]}).status_code == 200
    assert admin.get(f"/api/projects/{p['id']}").json["status"] == "review"
    # changes on another design are about that design only
    assert anon.post(f"/api/r/{token}/revisions", json={"body": "Bigger logo please", "deliverable_id": standee}).status_code == 200
    d = admin.get(f"/api/projects/{p['id']}").json
    assert d["status"] == "revision_requested"
    assert {x["title"]: x["status"] for x in d["deliverables"]} == {"Banner": "approved", "Standee": "changes_requested", "Instagram post": "review"}
    assert anon.post(f"/api/r/{token}/revisions", json={"body": "again"}).status_code == 400  # must name the design
    assert anon.post(f"/api/r/{token}/revisions", json={"body": "nope", "deliverable_id": banner}).status_code == 409  # already approved

    # the studio answers the change; only that design moves
    assert _upload(admin, p["id"], standee).status_code == 200
    v = anon.get(f"/api/r/{token}?quiet=1").json
    standee_v = next(x for x in v["deliverables"] if x["title"] == "Standee")
    assert [x["number"] for x in standee_v["versions"]] == [1, 2] and standee_v["revisions_used"] == 1
    # one revision was included per design: the second request on the same design is an extra one
    anon.post(f"/api/r/{token}/revisions", json={"body": "One more tweak", "deliverable_id": standee})
    d = admin.get(f"/api/projects/{p['id']}").json
    assert [c["is_extra"] for x in d["versions"] for c in x["comments"]] == [False, True]
    # and the quiet design still counts as untouched
    assert next(x for x in d["deliverables"] if x["title"] == "Instagram post")["revisions_used"] == 0

    # everything approved => the project is approved
    _upload(admin, p["id"], standee)
    v = anon.get(f"/api/r/{token}?quiet=1").json
    for x in v["deliverables"]:
        if x["status"] == "review":
            assert anon.post(f"/api/r/{token}/approve", json={"version_id": x["latest_version_id"]}).status_code == 200
    d = admin.get(f"/api/projects/{p['id']}").json
    assert d["status"] == "approved" and all(x["status"] == "approved" for x in d["deliverables"])
    assert _upload(admin, p["id"], banner).status_code == 409  # approved designs are locked

    # one design can be reopened without losing the others' approval
    r = admin.post(f"/api/deliverables/{banner}/reopen").json
    assert r["status"] == "in_design"
    assert {x["title"]: x["status"] for x in r["deliverables"]} == {"Banner": "pending", "Standee": "approved", "Instagram post": "approved"}


def test_design_names_and_removal_rules(admin):
    p = _project_with_designs(admin, titles=("A", "B"))
    a, b = (d["id"] for d in p["deliverables"])
    assert admin.post(f"/api/projects/{p['id']}/deliverables", {"title": "  "}).status_code == 400
    _upload(admin, p["id"], a)
    assert admin.c.delete(f"/api/deliverables/{a}", headers={"X-CSRF-Token": admin.csrf}).status_code == 409  # has a version
    r = admin.c.delete(f"/api/deliverables/{b}", headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 200 and [d["title"] for d in r.json["deliverables"]] == ["A"]
    assert admin.c.delete(f"/api/deliverables/{a}", headers={"X-CSRF-Token": admin.csrf}).status_code == 409  # the last one stays


def test_whole_project_can_be_invoiced_after_every_design_is_approved(admin, anon):
    p = _project_with_designs(admin, titles=("Banner", "Post"))
    for d in p["deliverables"]:
        _upload(admin, p["id"], d["id"])
    token = admin.get(f"/api/projects/{p['id']}").json["active_link"]["token"]
    view = anon.get(f"/api/r/{token}?quiet=1").json
    for x in view["deliverables"][:1]:
        anon.post(f"/api/r/{token}/approve", json={"version_id": x["latest_version_id"]})
    assert admin.post(f"/api/projects/{p['id']}/invoice").status_code == 409  # one design still open
    anon.post(f"/api/r/{token}/approve", json={"version_id": view["deliverables"][1]["latest_version_id"]})
    assert admin.upload_final(p["id"], png(), "all.png", "All designs").status_code == 200
    assert admin.post(f"/api/projects/{p['id']}/invoice").json["status"] == "payment_pending"


# ---------- advance payment ----------

def test_advance_flow_confirm_and_balance(admin, anon):
    assert admin.put("/api/settings", {"upi_id": "studio@okaxis"}).status_code == 200
    p = admin.new_project(amount=1000000, gst_enabled=False)
    assert p["advance"]["status"] == "none" and p["active_link"] is None
    d = admin.post(f"/api/projects/{p['id']}/advance", {"amount": 500000}).json
    assert d["advance"]["status"] == "requested" and d["advance"]["amount"] == 500000
    assert d["active_link"] and d["share"]["advance"]["link"].endswith("/advance")  # the client can pay before any design exists
    d = _upload(admin, p["id"]).json
    token = d["active_link"]["token"]

    view = anon.get(f"/api/r/{token}?quiet=1").json
    assert view["advance"]["due"] == 500000 and view["advance"]["status"] == "requested"
    assert "am=5000.00" in anon.get(f"/api/r/{token}/upi-uri?for=advance").json["uri"]
    assert anon.get(f"/api/r/{token}/advance-qr.png").mimetype == "image/png"
    assert anon.post(f"/api/r/{token}/advance", json={"reference": "12"}).status_code == 400  # not a real UTR
    assert anon.post(f"/api/r/{token}/advance", json={"reference": "426815093317"}).status_code == 200
    assert anon.post(f"/api/r/{token}/advance", json={"reference": "426815093318"}).status_code == 409  # one at a time
    assert admin.get(f"/api/projects/{p['id']}").json["advance"]["status"] == "submitted"
    assert any(x["kind"] == "advance" and x["status"] == "submitted" for x in admin.get("/api/payments?status=submitted").json)
    adv_id = admin.get(f"/api/projects/{p['id']}").json["advance"]["payments"][0]["id"]

    # a reference you can't find goes back to the client, who can try again
    assert admin.post(f"/api/advances/{adv_id}/reject", {"note": "Not in my account"}).status_code == 200
    assert anon.get(f"/api/r/{token}?quiet=1").json["advance"]["last_rejected"]["admin_note"] == "Not in my account"
    anon.post(f"/api/r/{token}/advance", json={"reference": "426815093999"})
    adv_id = admin.get(f"/api/projects/{p['id']}").json["advance"]["payments"][0]["id"]
    assert admin.post(f"/api/advances/{adv_id}/confirm").status_code == 200
    d = admin.get(f"/api/projects/{p['id']}").json
    assert d["advance"]["status"] == "paid" and d["advance"]["paid"] == 500000
    assert anon.post(f"/api/r/{token}/advance", json={"reference": "426815093000"}).status_code == 409  # already paid
    assert admin.post(f"/api/projects/{p['id']}/advance", {"amount": 100000}).status_code == 409  # can't go below what's paid

    # the final invoice asks only for the balance
    for x in anon.get(f"/api/r/{token}?quiet=1").json["deliverables"]:
        anon.post(f"/api/r/{token}/approve", json={"version_id": x["latest_version_id"]})
    admin.upload_final(p["id"], png(), "f.png", "Final")
    inv = admin.post(f"/api/projects/{p['id']}/invoice").json["invoice"]
    assert (inv["total"], inv["advance_paid"], inv["amount_due"]) == (1000000, 500000, 500000)
    assert "am=5000.00" in anon.get(f"/api/r/{token}/upi-uri").json["uri"]  # the QR asks for the balance only
    anon.post(f"/api/r/{token}/payments", data={"reference": "999888777666"}, content_type="multipart/form-data")
    pay = admin.get(f"/api/projects/{p['id']}").json["payments"][0]
    assert pay["amount"] == 500000
    assert admin.post(f"/api/payments/{pay['id']}/confirm").status_code == 200
    assert admin.get(f"/api/projects/{p['id']}").json["status"] == "paid"


def test_advance_can_be_shown_with_a_screenshot_instead_of_a_utr(admin, anon):
    admin.put("/api/settings", {"upi_id": "studio@okaxis", "studio_whatsapp": "919000000000"})
    assert anon.get("/api/brand").json["whatsapp"] == "919000000000"  # the client page offers WhatsApp
    p = admin.new_project(amount=1000000, gst_enabled=False)
    token = admin.post(f"/api/projects/{p['id']}/advance", {"amount": 500000}).json["active_link"]["token"]
    url = f"/api/r/{token}/advance"
    mp = "multipart/form-data"

    assert anon.post(url, data={"reference": ""}, content_type=mp).status_code == 400  # neither a screenshot nor a UTR
    assert anon.post(url, data={"reference": "12"}, content_type=mp).status_code == 400  # a bad UTR is still refused
    bad = anon.post(url, data={"proof": (io.BytesIO(b"not an image"), "pay.png")}, content_type=mp)
    assert bad.status_code == 400  # contents don't match the extension
    assert anon.post(url, data={"proof": (io.BytesIO(png(300, 600)), "pay.png")}, content_type=mp).status_code == 200

    adv = admin.get(f"/api/projects/{p['id']}").json["advance"]["payments"][0]
    assert adv["reference"] == "" and adv["proof_file_id"]  # screenshot only, no UTR
    shot = admin.get(f"/api/admin/files/{adv['proof_file_id']}?inline=1")
    assert shot.status_code == 200 and shot.mimetype == "image/png"
    seen = anon.get(f"/api/r/{token}?quiet=1").json["advance"]
    assert seen["pending"]["reference"] == "" and "proof_file_id" not in seen["pending"]  # clients never get file ids
    assert admin.post(f"/api/advances/{adv['id']}/confirm").status_code == 200
    assert admin.get(f"/api/projects/{p['id']}").json["advance"]["status"] == "paid"


def test_invoice_page_download_and_edit(admin, anon):
    admin.put("/api/settings", {"upi_id": "studio@okaxis"})
    d, token, _ = approved_project_with_invoice(admin, anon)
    inv_id = admin.get("/api/invoices").json[0]["id"]

    det = admin.get(f"/api/invoices/{inv_id}").json
    assert det["editable"] and det["document"]["items"] and det["link"].endswith("/invoice")
    assert "Thank you for trusting" in det["document"]["closing"] and "{client}" not in det["document"]["closing"]
    assert anon.get(f"/api/r/{token}?quiet=1").json["invoice"]["closing"] == det["document"]["closing"]
    assert det["document"]["payment"]["upi_id"] == "studio@okaxis"  # the QR on the invoice
    pdf = admin.get(f"/api/invoices/{inv_id}/download?format=pdf")
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    assert "attachment" in pdf.headers["Content-Disposition"] and det["number"] in pdf.headers["Content-Disposition"]
    img = admin.get(f"/api/invoices/{inv_id}/download?format=png")
    assert img.status_code == 200 and img.data[:4] == b"\x89PNG"
    assert admin.get(f"/api/invoices/{inv_id}/download?format=exe").status_code == 400
    assert anon.get(f"/api/invoices/{inv_id}").status_code == 401  # studio only

    # edit: change a price, add a line, a discount and a note
    items = [dict(i) for i in det["items"]]
    items[0]["unit_price"] = 600000
    items.append(dict(description="Rush delivery", quantity=1, unit_price=50000))
    r = admin.put(f"/api/invoices/{inv_id}", {"items": items, "discount": 10000, "gst_enabled": False,
                                              "notes": "Thank you for your business."})
    assert r.status_code == 200, r.json
    out = r.json
    assert out["subtotal"] == 650000 and out["total"] == 640000 and out["notes"] == "Thank you for your business."
    assert out["amount_due"] == 640000
    seen = anon.get(f"/api/r/{token}?quiet=1").json["invoice"]  # the client sees the edited invoice
    assert seen["total"] == 640000 and seen["notes"] == "Thank you for your business."

    # bad input is refused
    assert admin.put(f"/api/invoices/{inv_id}", {"items": [], "discount": 0}).status_code == 400
    assert admin.put(f"/api/invoices/{inv_id}", {"items": items, "discount": 99999999}).status_code == 400

    # once a payment is awaiting confirmation, or paid, the invoice is locked
    anon.post(f"/api/r/{token}/payments", data={"reference": "426815093317"}, content_type="multipart/form-data")
    assert admin.put(f"/api/invoices/{inv_id}", {"items": items, "discount": 0}).status_code == 409
    pay = admin.get(f"/api/projects/{d['id']}").json["payments"][0]
    admin.post(f"/api/payments/{pay['id']}/confirm")
    paid = admin.get(f"/api/invoices/{inv_id}").json
    assert paid["editable"] is False and "Payment received" in paid["document"]["closing"]  # a warmer note once paid
    assert admin.put(f"/api/invoices/{inv_id}", {"items": items, "discount": 0}).status_code == 409


def test_invoice_total_cannot_drop_below_the_advance_received(admin, anon):
    admin.put("/api/settings", {"upi_id": "studio@okaxis"})
    p = admin.new_project(amount=1000000, gst_enabled=False)
    admin.post(f"/api/projects/{p['id']}/advance", {"amount": 500000})
    d = _upload(admin, p["id"]).json
    token = d["active_link"]["token"]
    anon.post(f"/api/r/{token}/advance", json={"reference": "426815093317"})
    adv = admin.get(f"/api/projects/{p['id']}").json["advance"]["payments"][0]
    admin.post(f"/api/advances/{adv['id']}/confirm")
    for x in anon.get(f"/api/r/{token}?quiet=1").json["deliverables"]:
        anon.post(f"/api/r/{token}/approve", json={"version_id": x["latest_version_id"]})
    admin.upload_final(p["id"], png(), "f.png", "Final")
    admin.post(f"/api/projects/{p['id']}/invoice")
    inv = admin.get("/api/invoices").json[0]
    line = [dict(description="Poster", quantity=1, unit_price=300000)]  # below the 5000 already paid
    assert admin.put(f"/api/invoices/{inv['id']}", {"items": line, "discount": 0}).status_code == 409
    line[0]["unit_price"] = 500000  # exactly the advance: it is paid in full
    out = admin.put(f"/api/invoices/{inv['id']}", {"items": line, "discount": 0}).json
    assert out["status"] == "paid" and out["amount_due"] == 0


def test_studio_can_approve_a_design_for_the_client_quietly(admin, anon):
    p = admin.new_project(amount=500000, gst_enabled=False)
    d = _upload(admin, p["id"]).json
    token = d["active_link"]["token"]
    design = d["deliverables"][0]
    assert anon.post(f"/api/deliverables/{design['id']}/approve").status_code == 401  # studio only
    r = admin.post(f"/api/deliverables/{design['id']}/approve")
    assert r.status_code == 200 and r.json["status"] in ("approved", "finalization")
    view = anon.get(f"/api/r/{token}?quiet=1").json
    assert view["deliverables"][0]["status"] == "approved"  # the client simply sees it approved
    assert "studio" not in str(view).lower() or "studio" in view["brand"]["name"].lower()  # nothing says the studio did it
    log = [a for a in admin.get(f"/api/projects/{p['id']}").json["activity"] if a["event"] == "approved_by_studio"]
    assert log and "Studio approved" in log[0]["message"]  # the private record
    assert admin.post(f"/api/deliverables/{design['id']}/approve").status_code == 409  # already approved


def test_invoice_can_use_the_approved_design_files_as_the_finals(admin, anon):
    p = admin.new_project(amount=500000, gst_enabled=False)
    d = _upload(admin, p["id"]).json
    token = d["active_link"]["token"]
    for x in d["deliverables"]:
        anon.post(f"/api/r/{token}/approve", json={"version_id": x["latest_version_id"]})
    assert admin.post(f"/api/projects/{p['id']}/invoice").status_code == 409  # no finals and no opt-in
    r = admin.post(f"/api/projects/{p['id']}/invoice", {"use_approved_files": True})
    assert r.status_code == 200, r.json
    out = r.json
    assert out["status"] == "payment_pending" and out["invoice"]["status"] == "issued"
    assert len(out["finals"]) == len(d["deliverables"])  # the approved files became the finals
    assert out["finals"][0]["label"] == d["deliverables"][0]["title"]


def test_advance_covering_everything_marks_the_invoice_paid(admin, anon):
    p = admin.new_project(amount=100000, gst_enabled=False)
    admin.post(f"/api/projects/{p['id']}/advance", {"amount": 100000})
    admin.post(f"/api/projects/{p['id']}/advance/received", {"note": "cash"})
    d = _upload(admin, p["id"]).json
    token = d["active_link"]["token"]
    for x in anon.get(f"/api/r/{token}?quiet=1").json["deliverables"]:
        anon.post(f"/api/r/{token}/approve", json={"version_id": x["latest_version_id"]})
    admin.upload_final(p["id"], png(), "f.png", "Final")
    d = admin.post(f"/api/projects/{p['id']}/invoice").json
    assert d["status"] == "paid" and d["invoice"]["status"] == "paid" and d["invoice"]["amount_due"] == 0
    assert anon.get(f"/api/r/{token}?quiet=1").json["delivery"]["files"]  # files released without another payment


def test_advance_reminders_and_dashboard(app, admin):
    from datetime import timedelta

    from app.models import Project, db, now
    p = admin.new_project(amount=500000)
    _upload(admin, p["id"])  # the client link exists once something is shared
    assert admin.post(f"/api/projects/{p['id']}/advance/remind").status_code == 409  # nothing requested yet
    admin.post(f"/api/projects/{p['id']}/advance", {"amount": 250000})
    assert not [x for x in admin.get("/api/dashboard").json["needs_attention"] if "Advance" in x["reason"]]  # too soon to nag
    with app.app_context():
        db.session.get(Project, p["id"]).advance_requested_at = now() - timedelta(days=3)
        db.session.commit()
    reasons = [x["reason"] for x in admin.get("/api/dashboard").json["needs_attention"]]
    assert any("Advance of ₹2,500 not paid" in r for r in reasons)
    d = admin.post(f"/api/projects/{p['id']}/advance/remind").json  # sending a reminder resets the clock
    assert d["advance"]["reminded_at"]
    assert not [x for x in admin.get("/api/dashboard").json["needs_attention"] if "Advance" in x["reason"]]
    assert "₹2,500" in d["share"]["advance"]["message"] and d["share"]["advance"]["link"].endswith("/advance")


# ---------- quote -> project with several designs ----------

def test_quote_becomes_a_project_with_one_design_per_item(admin):
    q = _new_quote(admin, items=[
        dict(description="Event Flex banner", quantity=1, unit_price=120000),
        dict(description="Instagram post", quantity=3, unit_price=30000),
        dict(description="Instagram story", quantity=1, unit_price=10000, complimentary=True)], discount=0, gst_enabled=True)
    assert (q["document"]["revisions_included"], q["document"]["advance_percent"]) == (4, 50)  # the studio's standards
    t = q["document"]["totals"]
    assert t["total"] == 247800 and t["advance"] == 123900  # 50% of the total with GST
    admin.post(f"/api/quotes/{q['id']}/send")
    admin.post(f"/api/quotes/{q['id']}/status", {"action": "accept"})
    pid = admin.post(f"/api/quotes/{q['id']}/convert").json["project_id"]
    p = admin.get(f"/api/projects/{pid}").json
    assert [d["title"] for d in p["deliverables"]] == [
        "Event Flex banner", "Instagram post (1 of 3)", "Instagram post (2 of 3)", "Instagram post (3 of 3)", "Instagram story"]
    assert p["revisions_included"] == 4
    assert p["advance"]["amount"] == 123900 and p["advance"]["status"] == "requested"


def test_converting_can_override_revisions_and_advance(admin):
    q = _new_quote(admin)
    admin.post(f"/api/quotes/{q['id']}/send")
    admin.post(f"/api/quotes/{q['id']}/status", {"action": "accept"})
    assert admin.post(f"/api/quotes/{q['id']}/convert", {"advance_percent": 150}).status_code == 400
    pid = admin.post(f"/api/quotes/{q['id']}/convert", {"revisions_included": 6, "advance_percent": 0}).json["project_id"]
    p = admin.get(f"/api/projects/{pid}").json
    assert p["revisions_included"] == 6 and p["advance"]["status"] == "none"


def test_quote_terms_are_editable_per_quote(admin):
    q = _new_quote(admin, revisions_included=2, advance_percent=30)
    assert (q["document"]["revisions_included"], q["document"]["advance_percent"]) == (2, 30)
    assert admin.post("/api/quotes", _quote_body(q["client_id"], advance_percent=101)).status_code == 400
    assert admin.post("/api/quotes", _quote_body(q["client_id"], revisions_included=-1)).status_code == 400


# ---------- team accounts: employees see only their clients and never the money ----------

def _staff(app, admin, client_ids, email="staff@test.local", name="Priya Designer"):
    from tests.conftest import Admin
    r = admin.post("/api/team", {"name": name, "email": email, "password": "long-enough-pw", "client_ids": client_ids})
    assert r.status_code == 201, r.json
    return Admin(app.test_client(), (email, "long-enough-pw")), r.json


def test_employee_sees_only_assigned_clients_and_no_money(app, admin, anon):
    a = admin.new_project(client_name="Client A", name="A poster")
    b = admin.new_project(client_name="Client B", name="B poster")
    da, db_ = admin.upload_version(a["id"]), admin.upload_version(b["id"])
    token_a = da["active_link"]["token"]
    admin.post(f"/api/projects/{a['id']}/advance", {"amount": 50000})
    staff, member = _staff(app, admin, [a["client"]["id"]])

    rows = staff.get("/api/projects").json
    assert [r["id"] for r in rows] == [a["id"]]  # Client B is invisible
    assert rows[0]["amount"] == 0 and rows[0]["total"] == 0 and rows[0]["pending_payment"] is False
    assert staff.get(f"/api/projects/{b['id']}").status_code == 404  # not "forbidden": it simply isn't theirs

    r = staff.get(f"/api/projects/{a['id']}")
    d = r.json
    assert d["invoice"] is None and d["payments"] == [] and d["advance"]["amount"] == 0 and d["discount"] == 0
    assert d["client"]["email"] is None and d["client"]["phone"] is None and d["client"]["billing_address"] is None
    assert d["active_link"] is None and d["review_links"] == [] and d["share"]["review"]["link"] is None
    assert token_a not in r.get_data(as_text=True)  # the client's link would let them approve as the client
    assert d["versions"] and d["deliverables"]  # the work itself is there

    # the work: previews of their client's designs, not another client's
    vid_a, vid_b = d["versions"][0]["id"], db_["versions"][0]["id"]
    assert staff.get(f"/api/admin/versions/{vid_a}/pages/1").status_code == 200
    assert staff.get(f"/api/admin/versions/{vid_b}/pages/1").status_code == 404
    assert staff.upload_version(a["id"])["deliverables"]  # can upload a new version
    assert staff.post(f"/api/projects/{b['id']}/versions", data={"file": (io.BytesIO(png()), "x.png")}).status_code == 404

    # the owner can tell who did it, the client cannot
    log = [x["message"] for x in admin.get(f"/api/projects/{a['id']}").json["activity"] if x["event"] == "version_uploaded"]
    assert any("(by Priya Designer)" in m for m in log)
    assert "Priya" not in str(anon.get(f"/api/r/{token_a}?quiet=1").json)


def test_employee_is_locked_out_of_everything_owner_only(app, admin):
    p = admin.new_project(client_name="Client A")
    staff, _ = _staff(app, admin, [p["client"]["id"]])
    for url in ["/api/dashboard", "/api/clients", "/api/invoices", "/api/payments", "/api/settings", "/api/quotes",
                "/api/activity", "/api/files", "/api/notifications", "/api/team"]:
        assert staff.get(url).status_code == 403, url
    did = p["deliverables"][0]["id"]
    for url, body in [("/api/projects", {"client_id": p["client"]["id"], "name": "x", "project_type": "t", "amount": 1}),
                      (f"/api/projects/{p['id']}/advance", {"amount": 1000}),
                      (f"/api/projects/{p['id']}/invoice", {}),
                      (f"/api/projects/{p['id']}/watermark", {"enabled": False}),
                      (f"/api/deliverables/{did}/approve", {}),
                      (f"/api/projects/{p['id']}/review-links", {}),
                      ("/api/team", {"name": "x", "email": "x@x.co", "password": "long-enough-pw"})]:
        assert staff.post(url, body).status_code == 403, url
    assert staff.put(f"/api/projects/{p['id']}", {"name": "renamed"}).status_code == 403


def test_team_management_rules_and_switching_an_account_off(app, admin, anon):
    p = admin.new_project(client_name="Client A")
    cid = p["client"]["id"]
    assert admin.post("/api/team", {"name": "S", "email": "s@test.local", "password": "short"}).status_code == 400
    staff, m = _staff(app, admin, [cid], email="s@test.local")
    assert admin.post("/api/team", {"name": "S2", "email": "S@test.local", "password": "long-enough-pw"}).status_code == 409
    assert anon.get("/api/team").status_code == 401

    # change the assignment: access follows immediately
    assert admin.put(f"/api/team/{m['id']}", {"client_ids": []}).status_code == 200
    assert staff.get("/api/projects").json == []
    assert staff.get(f"/api/projects/{p['id']}").status_code == 404
    admin.put(f"/api/team/{m['id']}", {"client_ids": [cid]})
    assert len(staff.get("/api/projects").json) == 1

    # switching them off ends a live session and blocks a new login
    assert admin.put(f"/api/team/{m['id']}", {"active": False}).status_code == 200
    assert staff.get("/api/projects").status_code == 401
    r = anon.post("/api/auth/login", json={"email": "s@test.local", "password": "long-enough-pw"})
    assert r.status_code == 403
    # reset the password and switch back on
    admin.put(f"/api/team/{m['id']}", {"active": True, "password": "a-brand-new-password"})
    assert anon.post("/api/auth/login", json={"email": "s@test.local", "password": "long-enough-pw"}).status_code == 401
    assert anon.post("/api/auth/login", json={"email": "s@test.local", "password": "a-brand-new-password"}).status_code == 200
    # the owner account can't be edited through the team screen
    owner_id = [u for u in admin.get("/api/team").json if u["role"] == "admin"][0]["id"]
    assert admin.put(f"/api/team/{owner_id}", {"active": False}).status_code == 409


# ---------- monthly clients: plan, content calendar, client login ----------

def _plan_setup(admin, client_name="Monthly Co", inclusions=None, approval=True):
    c = admin.post("/api/clients", {"name": "Asha Rao", "company": client_name}).json
    r = admin.put(f"/api/clients/{c['id']}/plan", {"name": "Growth plan", "monthly_price": 2500000, "client_approval": approval,
                  "revisions_per_post": 2, "inclusions": inclusions or [{"kind": "post", "count": 3}, {"kind": "reel", "count": 1}]})
    assert r.status_code == 200, r.json
    return c, r.json


def _client_login(app, admin, c, can_approve=True, email="asha@monthly.co"):
    from tests.conftest import Admin
    r = admin.post(f"/api/clients/{c['id']}/logins", {"name": "Asha", "email": email, "password": "long-enough-pw", "can_approve": can_approve})
    assert r.status_code == 201, r.json
    return Admin(app.test_client(), (email, "long-enough-pw"))


def test_plan_calendar_posts_and_progress(admin):
    c, plan = _plan_setup(admin)
    assert plan["monthly_price"] == 2500000 and plan["project_id"]
    assert admin.put(f"/api/clients/{c['id']}/plan", {"name": "x", "inclusions": [{"kind": "podcast", "count": 2}]}).status_code == 400
    mk = lambda **kw: admin.post("/api/calendar/posts", dict(client_id=c["id"], title="Diwali post", kind="post",
                                 scheduled_at="2026-10-20T18:00", platforms=["Instagram", "Facebook"], caption="Happy Diwali", **kw))
    a = mk().json
    assert a["state"] == "planned" and a["platforms"] == ["Instagram", "Facebook"] and a["scheduled_at"] == "2026-10-20T18:00"
    blank = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="", kind="reel", scheduled_at="2026-10-21"))
    assert blank.status_code == 201 and blank.json["title"] == "Reel, 21 Oct"  # a planned slot needs no name yet
    admin.delete(f"/api/calendar/posts/{blank.json['id']}")
    assert admin.post("/api/calendar/posts", dict(client_id=c["id"], title="")).status_code == 400
    assert admin.post("/api/calendar/posts", dict(client_id=c["id"], title="x", scheduled_at="2026-10-21", platforms=["MySpace"])).status_code == 400
    reel = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="Reel", kind="reel", scheduled_at="2026-10-25",
                                                  media_url="https://youtu.be/abc")).json
    admin.post("/api/calendar/posts", dict(client_id=c["id"], title="November post", scheduled_at="2026-11-02"))
    cal = admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json
    assert [i["title"] for i in cal["items"]] == ["Diwali post", "Reel"]  # November is not in October
    prog = {r["kind"]: r for r in cal["progress"]}
    assert prog["post"]["included"] == 3 and prog["post"]["planned"] == 1 and prog["reel"]["planned"] == 1

    # upload a design for the post (the normal version upload), it goes to review
    pid = a["project_id"]
    d = admin.post(f"/api/projects/{pid}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(a["id"])})
    assert d.status_code == 200, d.json
    assert admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json["items"][0]["state"] == "review"
    assert admin.post(f"/api/calendar/posts/{a['id']}/posted", {"posted": True}).status_code == 409  # not approved yet
    assert admin.delete(f"/api/calendar/posts/{a['id']}").status_code == 409  # has a design
    assert admin.delete(f"/api/calendar/posts/{reel['id']}").status_code == 200  # a planned one can go
    # retainer projects don't clutter the normal project list
    assert all(p["id"] != pid for p in admin.get("/api/projects").json)


def test_client_login_sees_only_their_calendar_and_can_approve(app, admin, anon):
    c, _ = _plan_setup(admin)
    other, _ = _plan_setup(admin, client_name="Other Co")
    post = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="Post A", scheduled_at="2026-10-12T10:00")).json
    theirs = admin.post("/api/calendar/posts", dict(client_id=other["id"], title="Post B", scheduled_at="2026-10-12T10:00")).json
    for p in (post, theirs):
        admin.post(f"/api/projects/{p['project_id']}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(p["id"])})
    cl = _client_login(app, admin, c)

    cal = cl.get("/api/c/calendar?month=2026-10").json
    assert [i["title"] for i in cal["items"]] == ["Post A"] and cal["can_approve"] is True
    body = str(cal)
    assert "monthly_price" not in body and "2500000" not in body and "Post B" not in body  # no money, no other client
    detail = cl.get(f"/api/c/posts/{post['id']}").json
    vid = detail["history"][0]["id"]
    assert cl.get(f"/api/c/versions/{vid}/pages/1").status_code == 200
    assert cl.get(f"/api/c/posts/{theirs['id']}").status_code == 404  # someone else's post is just "not found"
    theirs_vid = admin.get(f"/api/projects/{theirs['project_id']}").json["versions"][0]["id"]
    assert cl.get(f"/api/c/versions/{theirs_vid}/pages/1").status_code == 404
    # owner-only places are closed to a client login
    for url in ["/api/projects", "/api/clients", "/api/invoices", "/api/settings", "/api/team", "/api/calendar/clients",
                f"/api/calendar?client_id={c['id']}&month=2026-10"]:
        assert cl.get(url).status_code == 403, url

    # request changes, then approve the next version
    assert cl.post(f"/api/c/posts/{post['id']}/revisions", {"body": "Make the logo bigger"}).json["state"] == "changes"
    assert admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json["items"][0]["request"] == "Make the logo bigger"
    admin.post(f"/api/projects/{post['project_id']}/versions", data={"file": (io.BytesIO(png()), "d2.png"), "deliverable_id": str(post["id"])})
    v2 = cl.get(f"/api/c/posts/{post['id']}").json["history"][0]["id"]
    r = cl.post(f"/api/c/posts/{post['id']}/approve", {"version_id": v2})
    assert r.status_code == 200 and r.json["state"] == "approved"
    # the monthly project never locks: it keeps taking new posts and versions
    assert admin.post("/api/calendar/posts", dict(client_id=c["id"], title="Later", scheduled_at="2026-10-30")).status_code == 201
    # posted + the plan count
    assert admin.post(f"/api/calendar/posts/{post['id']}/posted", {"posted": True}).json["state"] == "posted"
    prog = {r["kind"]: r for r in admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json["progress"]}
    assert prog["post"]["approved"] == 1 and prog["post"]["posted"] == 1 and prog["post"]["planned"] == 2


def test_view_only_client_login_cannot_approve_and_switched_off_logins_stop(app, admin):
    c, _ = _plan_setup(admin)
    post = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="P", scheduled_at="2026-10-12")).json
    admin.post(f"/api/projects/{post['project_id']}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(post["id"])})
    viewer = _client_login(app, admin, c, can_approve=False, email="view@monthly.co")
    vid = viewer.get(f"/api/c/posts/{post['id']}").json["history"][0]["id"]
    assert viewer.post(f"/api/c/posts/{post['id']}/approve", {"version_id": vid}).status_code == 403
    assert viewer.post(f"/api/c/posts/{post['id']}/revisions", {"body": "change it"}).status_code == 403
    uid = admin.get(f"/api/clients/{c['id']}/logins").json[0]["id"]
    admin.put(f"/api/logins/{uid}", {"active": False})
    assert viewer.get("/api/c/calendar?month=2026-10").status_code == 401
    # a client login can't be used on admin routes, and an employee can't reach client routes
    staff, _ = _staff(app, admin, [c["id"]])
    assert staff.get("/api/c/calendar?month=2026-10").status_code == 403


def test_employee_works_the_calendar_of_assigned_clients_only(app, admin):
    a, _ = _plan_setup(admin, client_name="Client A")
    b, _ = _plan_setup(admin, client_name="Client B")
    staff, _ = _staff(app, admin, [a["id"]])
    assert [c["id"] for c in staff.get("/api/calendar/clients").json] == [a["id"]]
    post = staff.post("/api/calendar/posts", dict(client_id=a["id"], title="Mine", scheduled_at="2026-10-12"))
    assert post.status_code == 201
    assert staff.post("/api/calendar/posts", dict(client_id=b["id"], title="Not mine", scheduled_at="2026-10-12")).status_code == 404
    assert staff.get(f"/api/calendar?client_id={b['id']}&month=2026-10").status_code == 404
    cal = staff.get(f"/api/calendar?client_id={a['id']}&month=2026-10").json
    assert "monthly_price" not in str(cal) and "2500000" not in str(cal)  # an employee never sees what the plan costs
    # plan settings (price, inclusions) stay with the owner
    assert staff.put(f"/api/clients/{a['id']}/plan", {"name": "x", "monthly_price": 1}).status_code == 403
    assert staff.get(f"/api/clients/{a['id']}/logins").status_code == 403


def test_monthly_quote_with_scope_starts_the_monthly_plan(admin, anon):
    c = admin.post("/api/clients", {"name": "Asha", "company": "Test Co"}).json
    body = dict(client_id=c["id"], title="Monthly package", discount=700000, discount_label="Special client discount",
                billing="monthly", revisions_included=2, advance_percent=50, valid_until="2099-01-01",
                items=[dict(description="Standard monthly package", quantity=1, unit_price=2200000)],
                sections=[dict(title="Social media", lines=["# Reels, 7 per month", "Video editing", "> Ad spend is separate."]),
                          dict(title="SEO", lines="Audit\nOn-page fixes")],
                plan_inclusions=[dict(kind="reel", count=7), dict(kind="post", count=7)])
    q = admin.post("/api/quotes", body)
    assert q.status_code == 201, q.json
    q = q.json
    doc = q["document"]
    assert doc["billing"] == "monthly" and doc["discount_label"] == "Special client discount"
    assert doc["totals"]["total"] == 1500000 and doc["totals"]["discount"] == 700000
    assert [s["title"] for s in doc["sections"]] == ["Social media", "SEO"] and doc["sections"][1]["lines"] == ["Audit", "On-page fixes"]
    assert q["plan_inclusions"] == [dict(kind="reel", count=7), dict(kind="post", count=7)]
    # validation
    assert admin.post("/api/quotes", dict(body, sections=[dict(title="", lines=["x"])])).status_code == 400
    assert admin.post("/api/quotes", dict(body, plan_inclusions=[dict(kind="podcast", count=1)])).status_code == 400
    # the files download with the scope in them
    pdf = admin.get(f"/api/quotes/{q['id']}/download?format=pdf")
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    import pymupdf
    text = "".join(p.get_text() for p in pymupdf.open(stream=pdf.data, filetype="pdf"))
    assert "Scope of work" in text and "Reels, 7 per month" in text and "Special client discount" in text and "Total per month" in text
    # copies keep it
    assert admin.post(f"/api/quotes/{q['id']}/duplicate").json["document"]["sections"][0]["title"] == "Social media"

    # not before it is accepted, and only once
    assert admin.post(f"/api/quotes/{q['id']}/start-plan").status_code == 409
    admin.post(f"/api/quotes/{q['id']}/send")
    anon.post(f"/api/q/{q['token'] if 'token' in q else q['share']['link'].rsplit('/', 1)[-1]}/accept", json={})
    r = admin.post(f"/api/quotes/{q['id']}/start-plan")
    assert r.status_code == 200 and r.json["has_plan"] is True
    plan = admin.get(f"/api/clients/{c['id']}/plan").json
    assert plan["monthly_price"] == 1500000 and plan["revisions_per_post"] == 2
    assert {(i["kind"], i["count"]) for i in plan["inclusions"]} == {("reel", 7), ("post", 7)}
    assert admin.post(f"/api/quotes/{q['id']}/start-plan").status_code == 409


def test_mixed_quote_one_time_plus_monthly_is_summarised_and_accepted_by_the_client(admin, anon):
    c = admin.post("/api/clients", {"name": "Asha", "company": "Web Test Co"}).json
    body = dict(client_id=c["id"], title="Website and care", scope_first=False, advance_percent=100, revisions_included=0,
                valid_until="2099-01-01",
                items=[dict(description="Website design", quantity=1, unit_price=6000000, period="once", detail="UI/UX and deployment."),
                       dict(description="Maintenance and SEO", quantity=1, unit_price=2500000, period="monthly"),
                       dict(description="Hosting care", quantity=1, unit_price=1000000, period="monthly")],
                sections=[dict(title="Website", part="scope", lines=["Responsive pages"]),
                          dict(title="Payment terms", part="after", lines=["# 1. One-time", "~ Payable before work starts.", "Bullet"])])
    q = admin.post("/api/quotes", body)
    assert q.status_code == 201, q.json
    q = q.json
    doc = q["document"]
    t = doc["totals"]
    assert doc["mode"] == "mixed" and doc["scope_first"] is False
    assert (t["recurring"], t["one_time"], t["total"], t["advance"]) == (3500000, 6000000, 9500000, 9500000)  # 60k + first month 35k
    assert [i["period"] for i in doc["items"]] == ["once", "monthly", "monthly"] and doc["items"][0]["detail"] == "UI/UX and deployment."
    assert [s["part"] for s in doc["sections"]] == ["scope", "after"]
    import pymupdf
    pdf = admin.get(f"/api/quotes/{q['id']}/download?format=pdf")
    text = "".join(p.get_text() for p in pymupdf.open(stream=pdf.data, filetype="pdf"))
    assert "Total initial payment" in text and "Monthly recurring fee" in text and "Payable before work starts." in text
    assert text.index("Website design") < text.index("Scope of work") < text.index("Payment terms")  # pricing, then scope, then terms
    # all-monthly and all-one-time quotes keep their old wording
    mono = admin.post("/api/quotes", dict(body, items=[dict(description="Care", quantity=1, unit_price=100000, period="monthly")])).json
    assert mono["document"]["mode"] == "monthly"
    once = admin.post("/api/quotes", dict(body, items=[dict(description="Poster", quantity=1, unit_price=100000)])).json
    assert once["document"]["mode"] == "once"
    # the client opens the link and accepts it
    link = admin.post(f"/api/quotes/{q['id']}/send").json["share"]["link"]
    token = link.rsplit("/", 1)[-1]
    seen = anon.get(f"/api/q/{token}").json
    assert seen["document"]["totals"]["total"] == 9500000 and seen["can_respond"] is True
    r = anon.post(f"/api/q/{token}/accept", json={"note": "Go ahead"})
    assert r.status_code == 200 and r.json["status"] == "accepted"
    assert admin.get(f"/api/quotes/{q['id']}").json["status"] == "accepted"


def test_bundle_quote_special_price_savings_and_a_closing_page(admin):
    import pymupdf
    c = admin.post("/api/clients", {"name": "Asha", "company": "Bundle Co"}).json
    body = dict(client_id=c["id"], title="Bundle", valid_until="2099-01-01", advance_percent=100, revisions_included=0,
                items=[dict(description="Marketing", quantity=1, unit_price=1500000, list_price=2200000, period="monthly"),
                       dict(description="Website", quantity=1, unit_price=6000000, list_price=6500000, period="once"),
                       dict(description="Care", quantity=1, unit_price=1000000, list_price=900000, period="monthly")],  # not a saving
                sections=[dict(title="Scope", part="scope", lines=["One"]),
                          dict(title="Why both matter", part="appendix", tone="title", lines=["~ Intro paragraph."]),
                          dict(title="What you gain", part="appendix", tone="gain", lines=["Visibility"]),
                          dict(title="What can go wrong", part="appendix", tone="caution", lines=["Lost visitors"]),
                          dict(title="Odd", part="elsewhere", tone="rainbow", lines=["x"])])
    q = admin.post("/api/quotes", body)
    assert q.status_code == 201, q.json
    doc = q.json["document"]
    t = doc["totals"]
    assert (t["recurring"], t["one_time"], t["total"]) == (2500000, 6000000, 8500000)
    assert t["savings_monthly"] == 700000 and t["savings_once"] == 500000  # a "list price" below the price is ignored
    assert doc["items"][0]["list_price"] == 2200000 and doc["items"][2]["list_price"] is None
    parts = [(s["part"], s["tone"]) for s in doc["sections"]]
    assert parts == [("scope", None), ("appendix", "title"), ("appendix", "gain"), ("appendix", "caution"), ("scope", None)]  # unknowns fall back
    pdf = admin.get(f"/api/quotes/{q.json['id']}/download?format=pdf")
    docx = pymupdf.open(stream=pdf.data, filetype="pdf")
    text = "".join(p.get_text() for p in docx)
    assert "You save" in text and "every month with the special" in text and "Special client" in text  # (the PDF font joins "ff")
    last = docx[docx.page_count - 1].get_text()
    assert "Why both matter" in last and "What can go wrong" in last  # the closing page starts a fresh page
    assert "Why both matter" not in "".join(docx[i].get_text() for i in range(docx.page_count - 1))
    assert admin.get(f"/api/quotes/{q.json['id']}/download?format=png").data[:4] == b"\x89PNG"
    assert admin.post(f"/api/quotes/{q.json['id']}/duplicate").json["document"]["items"][0]["list_price"] == 2200000


def test_recurring_fee_starting_after_launch(admin):
    c = admin.post("/api/clients", {"name": "Shailesh", "company": "Catering Co"}).json
    body = dict(client_id=c["id"], title="Site", valid_until="2099-01-01", advance_percent=50, recurring_start="launch",
                items=[dict(description="Website", quantity=1, unit_price=2500000, period="once"),
                       dict(description="Maintenance", quantity=1, unit_price=250000, period="monthly")])
    r = admin.post("/api/quotes", body)
    assert r.status_code == 201, r.json
    doc = r.json["document"]
    t = doc["totals"]
    assert doc["recurring_start"] == "launch"
    assert t["total"] == 2500000 and t["advance"] == 1250000 and t["recurring"] == 250000 and t["one_time"] == 2500000
    body["recurring_start"] = "now"
    assert admin.post("/api/quotes", body).json["document"]["totals"]["total"] == 2750000


def test_quote_and_invoice_header_with_a_logo_keeps_the_title_block_and_names_the_software(admin):
    import pymupdf
    admin.put("/api/settings", {"brand_name": "Demo Studio"})
    up = admin.post("/api/settings/logo", data={"file": (io.BytesIO(png(600, 300)), "logo.png")})
    assert up.status_code == 200, up.json
    q = _free_quote(admin)
    text = pymupdf.open(stream=admin.get(f"/api/quotes/{q['id']}/download?format=pdf").data, filetype="pdf")[0].get_text()
    for expected in ("Quotation", "QUO-1001", "Valid until", "CreativeFlow Studio"):
        assert expected in text, expected


def test_post_chat_between_team_and_client_with_unread_and_new_flags(app, admin):
    c, _ = _plan_setup(admin)
    other, _ = _plan_setup(admin, client_name="Other Co")
    post = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="Diwali post", scheduled_at="2026-10-12T10:00")).json
    theirs = admin.post("/api/calendar/posts", dict(client_id=other["id"], title="Secret", scheduled_at="2026-10-12T10:00")).json
    admin.post(f"/api/projects/{post['project_id']}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(post["id"]), "note": "First look"})
    cl = _client_login(app, admin, c)

    cal = cl.get("/api/c/calendar?month=2026-10").json
    assert cal["items"][0]["fresh"] is True and cal["updates"][0]["new"] is True and cal["updates"][0]["kind"] == "creative"
    # opening the post clears 'new'
    first = cl.get(f"/api/c/posts/{post['id']}").json
    assert first["fresh"] is True and [t["type"] for t in first["thread"]] == ["version"]
    assert cl.get("/api/c/calendar?month=2026-10").json["items"][0]["fresh"] is False

    # the client writes; the team sees one unread and the owner gets a notification
    r = cl.post(f"/api/c/posts/{post['id']}/messages", {"body": "Can the date be bigger?"})
    assert r.status_code == 201 and r.json["thread"][-1]["mine"] is True
    assert cl.post(f"/api/c/posts/{post['id']}/messages", {"body": "  "}).status_code == 400
    assert cl.post(f"/api/c/posts/{post['id']}/messages", {"body": "x" * 2001}).status_code == 400
    assert cl.post(f"/api/c/posts/{theirs['id']}/messages", {"body": "hi"}).status_code == 404  # someone else's post
    clients = admin.get("/api/calendar/clients").json
    assert next(x for x in clients if x["id"] == c["id"])["unread"] == 1
    assert admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json["items"][0]["unread"] == 1
    assert any("Diwali post" in n["message"] for n in admin.get("/api/notifications").json["items"])

    # the team opens it (read) and answers; the client then has one unread and an update
    t = admin.get(f"/api/calendar/posts/{post['id']}/thread").json["thread"]
    assert [x["type"] for x in t] == ["version", "message"] and t[1]["mine"] is False  # "mine" is relative to the viewer
    assert admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json["items"][0]["unread"] == 0
    admin.post(f"/api/calendar/posts/{post['id']}/messages", {"body": "Done, version 2 coming."})
    mine = cl.get("/api/c/calendar?month=2026-10").json
    assert mine["items"][0]["unread"] == 1 and mine["updates"][0]["kind"] == "message" and mine["updates"][0]["new"] is True
    thread = cl.get(f"/api/c/posts/{post['id']}").json["thread"]
    assert [x["mine"] for x in thread if x["type"] == "message"] == [True, False]
    assert cl.get("/api/c/calendar?month=2026-10").json["items"][0]["unread"] == 0

    # a client login can't reach the team's chat endpoints
    assert cl.get(f"/api/calendar/posts/{post['id']}/thread").status_code == 403
    assert cl.post(f"/api/calendar/posts/{post['id']}/messages", {"body": "x"}).status_code == 403
    # and an employee not assigned to this client can't either
    staff, _ = _staff(app, admin, [other["id"]])
    assert staff.get(f"/api/calendar/posts/{post['id']}/thread").status_code in (403, 404)


def test_chat_only_plan_has_no_client_approval_and_posts_without_it(app, admin):
    c, plan = _plan_setup(admin, approval=False)
    assert plan["client_approval"] is False
    post = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="Reel A", kind="reel", scheduled_at="2026-10-12T10:00")).json
    admin.post(f"/api/projects/{post['project_id']}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(post["id"])})
    cl = _client_login(app, admin, c)
    cal = cl.get("/api/c/calendar?month=2026-10").json
    assert cal["can_approve"] is False and cal["plan"]["client_approval"] is False
    row = next(r for r in cal["progress"] if r["kind"] == "reel")
    assert row["included"] == 1 and row["made"] == 1 and row["posted"] == 0
    # the client can't approve or ask for changes, only chat
    vid = admin.get(f"/api/calendar?client_id={c['id']}&month=2026-10").json["items"][0]["latest_version_id"]
    assert cl.post(f"/api/c/posts/{post['id']}/approve", {"version_id": vid}).status_code == 403
    assert cl.post(f"/api/c/posts/{post['id']}/revisions", {"body": "make it red"}).status_code == 403
    assert cl.post(f"/api/c/posts/{post['id']}/messages", {"body": "make it red please"}).status_code == 201
    # the team can mark it posted straight from "shared"; with approval on, that still needs the client's approval
    assert admin.post(f"/api/calendar/posts/{post['id']}/posted", {"posted": True}).json["state"] == "posted"
    c2, _ = _plan_setup(admin, client_name="Strict Co", approval=True)
    p2 = admin.post("/api/calendar/posts", dict(client_id=c2["id"], title="B", scheduled_at="2026-10-12T10:00")).json
    admin.post(f"/api/projects/{p2['project_id']}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(p2["id"])})
    assert admin.post(f"/api/calendar/posts/{p2['id']}/posted", {"posted": True}).status_code == 409
    # toggling approval on later gives the client the buttons
    assert admin.post(f"/api/clients/{c['id']}/plan/toggles", {"client_approval": True}).json["client_approval"] is True
    assert cl.get("/api/c/calendar?month=2026-10").json["can_approve"] is True


def test_month_end_payment_reminder_toggle_claim_and_paid(app, admin, monkeypatch):
    from datetime import date
    from app import services as sv
    from app.models import Plan
    monkeypatch.setattr(sv, "PAYMENT_REMINDER_ENABLED", True)  # the feature is parked in the app for now
    c, plan = _plan_setup(admin, approval=False)
    cl = _client_login(app, admin, c)
    assert cl.get("/api/c/calendar?month=2026-10").json["payment"] is None  # off by default
    assert admin.post(f"/api/clients/{c['id']}/plan/toggles", {"payment_reminder": True}).json["payment_reminder"] is True

    class Day(date):
        today_is = date(2026, 10, 20)

        @classmethod
        def today(cls):
            return cls.today_is
    monkeypatch.setattr(sv, "date", Day)
    pay = lambda: cl.get("/api/c/calendar?month=2026-10").json["payment"]
    assert pay() is None  # still early in the month

    Day.today_is = date(2026, 10, 27)  # five days before the month ends
    p = pay()
    assert p["month"] == "2026-10" and p["amount"] == 2500000 and p["due_date"] == "2026-10-31" and p["days_left"] == 4 and not p["claimed"]
    assert admin.get(f"/api/clients/{c['id']}/plan").json["payment"]["showing"] is True
    assert cl.post("/api/c/payment/claim").status_code == 200 and pay()["claimed"] is True
    assert any("says they have paid" in n["message"] for n in admin.get("/api/notifications").json["items"])

    # the studio confirms: the reminder goes away, and comes back for the next month
    assert admin.post(f"/api/clients/{c['id']}/plan/paid", {"paid": True}).json["payment"]["paid"] is True
    assert pay() is None
    Day.today_is = date(2026, 11, 3)  # October is paid, so nothing yet for November
    assert pay() is None
    Day.today_is = date(2026, 11, 27)
    assert pay()["month"] == "2026-11"
    # an unpaid month stays visible, marked overdue, for the first days of the next one
    Day.today_is = date(2026, 12, 4)
    assert pay()["month"] == "2026-11" and pay()["overdue"] is True
    admin.post(f"/api/clients/{c['id']}/plan/paid", {"paid": False})  # undo marks the month unpaid again
    # switched off: nothing shows, and a staff member never sees any of it
    admin.post(f"/api/clients/{c['id']}/plan/toggles", {"payment_reminder": False})
    assert pay() is None
    staff, _ = _staff(app, admin, [c["id"]])
    assert staff.get(f"/api/clients/{c['id']}/plan").status_code == 403


def test_payment_reminder_is_parked_and_shows_nothing(app, admin):
    c, plan = _plan_setup(admin, approval=False)
    admin.post(f"/api/clients/{c['id']}/plan/toggles", {"payment_reminder": True})
    cl = _client_login(app, admin, c)
    assert cl.get("/api/c/calendar?month=2026-10").json["payment"] is None
    assert admin.get(f"/api/clients/{c['id']}/plan").json["payment_available"] is False


def test_record_a_payment_from_a_monthly_client(app, admin):
    c, _ = _plan_setup(admin, approval=True)
    shot = (io.BytesIO(png(300, 400)), "imps.png")
    r = admin.post(f"/api/clients/{c['id']}/plan/payments", data={"amount": "750000", "received_on": "2026-10-27", "reference": "1234567890",
                                                                    "note": "IMPS, 50% of the first month", "proof": shot})
    assert r.status_code == 201, r.json
    pay = r.json["payments"][0]
    assert pay["amount"] == 750000 and pay["received_on"] == "2026-10-27" and pay["reference"] == "1234567890" and pay["proof_file_id"]
    assert admin.get(f"/api/admin/files/{pay['proof_file_id']}?inline=1").status_code == 200
    assert admin.post(f"/api/clients/{c['id']}/plan/payments", {"amount": 0}).status_code == 400
    assert admin.post(f"/api/clients/{c['id']}/plan/payments", {"amount": 100, "received_on": "2999-01-01"}).status_code == 400
    # a client login never sees it, and nobody but the owner can record one
    cl = _client_login(app, admin, c)
    assert "1234567890" not in str(cl.get("/api/c/calendar?month=2026-10").json)
    assert cl.post(f"/api/clients/{c['id']}/plan/payments", {"amount": 5}).status_code == 403
    assert admin.get("/api/dashboard").status_code == 200


def test_monthly_client_invoice_shows_the_advance_and_its_screenshot(app, admin):
    c, _ = _plan_setup(admin, approval=True)
    assert admin.post(f"/api/clients/{c['id']}/plan/invoice", {}).status_code == 201  # no payment yet: the whole price is due
    inv = admin.get("/api/invoices").json[0]
    assert inv["total"] == 2500000 and inv["advance_paid"] == 0 and inv["amount_due"] == 2500000
    assert admin.post(f"/api/clients/{c['id']}/plan/invoice", {}).status_code == 409  # one invoice per client
    c2, _ = _plan_setup(admin, client_name="Second Co", approval=True)
    shot = (io.BytesIO(png(300, 400)), "imps.png")
    admin.post(f"/api/clients/{c2['id']}/plan/payments", data={"amount": "1250000", "received_on": "2026-10-27", "reference": "1234567890", "proof": shot})
    r = admin.post(f"/api/clients/{c2['id']}/plan/invoice", {})
    assert r.status_code == 201 and r.json["invoice"]["number"]
    inv = next(i for i in admin.get("/api/invoices").json if i["project"]["client"] == "Second Co")
    assert inv["status"] == "issued" and inv["advance_paid"] == 1250000 and inv["amount_due"] == 1250000
    d = admin.get(f"/api/invoices/{inv['id']}").json
    assert d["advances"][0]["amount"] == 1250000 and d["advances"][0]["proof_file_id"]
    assert d["document"]["advances"] == [dict(amount=1250000, reference="1234567890", received_on="2026-10-27")]
    assert admin.get(f"/api/admin/files/{d['advances'][0]['proof_file_id']}?inline=1").status_code == 200
    pdf = admin.get(f"/api/invoices/{inv['id']}/download?format=pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    import pymupdf
    text = "".join(pg.get_text() for pg in pymupdf.open(stream=pdf.data, filetype="pdf"))
    assert "Advance received" in text and "27 Oct 2026" in text and "1234567890" in text
    assert "final creative" not in text and "final files" not in text  # wording for one-off design work


def test_client_brief_flow_from_planned_slot_to_team_attention(app, admin):
    c, _ = _plan_setup(admin, approval=True)
    slot = admin.post("/api/calendar/posts", dict(client_id=c["id"], title="", kind="carousel", scheduled_at="2026-11-07T11:00")).json
    assert slot["title"] == "Carousel, 7 Nov" and slot["state"] == "planned"
    cl = _client_login(app, admin, c)
    assert admin.get("/api/calendar/attention").json["count"] == 0

    # the client fills in their content (words and a photo); the post becomes "brief" and the team is told
    shot = (io.BytesIO(png(300, 300)), "offer.png")
    r = cl.post(f"/api/c/posts/{slot['id']}/brief", data={"text": "Diwali offer: 20% off on all packages till 15 Nov.", "files": shot})
    assert r.status_code == 201, r.json
    assert r.json["state"] == "brief" and r.json["brief"].startswith("Diwali offer") and len(r.json["brief_files"]) == 1
    assert cl.post(f"/api/c/posts/{slot['id']}/brief", data={"text": ""}).status_code == 201  # keeps what is there; files stay
    assert any("sent their content" in n["message"] for n in admin.get("/api/notifications").json["items"])
    att = admin.get("/api/calendar/attention").json
    assert att["count"] == 1 and att["items"][0]["what"] == "brief" and att["items"][0]["title"] == "Carousel, 7 Nov"
    assert admin.get("/api/calendar/clients").json[0]["unread"] == 1

    # the team can open the client's file; the client can open their own, nobody else's
    fid = r.json["brief_files"][0]["id"]
    assert admin.get(f"/api/admin/files/{fid}?inline=1").status_code == 200
    assert cl.get(f"/api/c/brief-files/{fid}").status_code == 200
    # opening the post marks the brief as seen, which clears the attention
    assert admin.get(f"/api/calendar/posts/{slot['id']}/thread").status_code == 200
    assert admin.get("/api/calendar/attention").json["count"] == 0
    # an employee on this client can see it too; one who isn't assigned cannot
    mine, _ = _staff(app, admin, [c["id"]])
    cl.post(f"/api/c/posts/{slot['id']}/brief", data={"text": "Also add our phone number."})
    assert mine.get("/api/calendar/attention").json["count"] == 1
    assert mine.get(f"/api/admin/files/{fid}?inline=1").status_code == 200
    other, _ = _staff(app, admin, [], email="other@test.local", name="Other")
    assert other.get("/api/calendar/attention").json["count"] == 0

    # once the studio shares a design, the brief is closed and the client uses the chat
    admin.post(f"/api/projects/{slot['project_id']}/versions", data={"file": (io.BytesIO(png()), "d.png"), "deliverable_id": str(slot["id"])})
    assert cl.post(f"/api/c/posts/{slot['id']}/brief", data={"text": "change"}).status_code == 409
    # a brief needs words or a photo, and the file must be an image or PDF
    s2 = admin.post("/api/calendar/posts", dict(client_id=c["id"], kind="post", scheduled_at="2026-11-09")).json
    assert cl.post(f"/api/c/posts/{s2['id']}/brief", data={"text": ""}).status_code == 400
    assert cl.post(f"/api/c/posts/{s2['id']}/brief", data={"files": (io.BytesIO(b"MZ..."), "x.exe")}).status_code == 400


def test_several_people_can_sign_in_to_one_account_at_once_without_being_locked_out(app, admin):
    from tests.conftest import Admin
    app.config["RATELIMIT_ENABLED"] = True
    c, _ = _plan_setup(admin, approval=True)
    _client_login(app, admin, c)
    # twenty people on the same office network sign in with the right password: nobody is held up, and each has their own session
    people = [Admin(app.test_client(), ("asha@monthly.co", "long-enough-pw")) for _ in range(20)]
    assert all(p.get("/api/c/calendar?month=2026-10").status_code == 200 for p in people)
    # one person making many wrong guesses does not stop the others
    bad = app.test_client()
    assert [bad.post("/api/auth/login", json={"email": "asha@monthly.co", "password": "nope"}, environ_overrides={"REMOTE_ADDR": "203.0.113.9"}).status_code
            for _ in range(16)][-1] == 429
    assert Admin(app.test_client(), ("asha@monthly.co", "long-enough-pw")).get("/api/c/calendar?month=2026-10").status_code == 200
    # a second device signing in does not sign the first one out
    first = people[0]
    Admin(app.test_client(), ("asha@monthly.co", "long-enough-pw"))
    assert first.get("/api/c/calendar?month=2026-10").status_code == 200


def test_two_people_on_one_login_cannot_overwrite_each_others_brief(app, admin):
    from tests.conftest import Admin
    c, _ = _plan_setup(admin, approval=True)
    slot = admin.post("/api/calendar/posts", dict(client_id=c["id"], kind="post", scheduled_at="2026-11-02")).json
    _client_login(app, admin, c)
    a = Admin(app.test_client(), ("asha@monthly.co", "long-enough-pw"))
    b = Admin(app.test_client(), ("asha@monthly.co", "long-enough-pw"))
    first = a.post(f"/api/c/posts/{slot['id']}/brief", data={"text": "From person A", "base": ""})
    assert first.status_code == 201
    # B opened the post before A saved, so B's copy is out of date: refused, nothing lost
    stale = b.post(f"/api/c/posts/{slot['id']}/brief", data={"text": "From person B", "base": ""})
    assert stale.status_code == 409 and stale.json["code"] == "brief_changed"
    assert b.get(f"/api/c/posts/{slot['id']}").json["brief"] == "From person A"
    # with the latest version B can save
    base = b.get(f"/api/c/posts/{slot['id']}").json["brief_at"]
    assert b.post(f"/api/c/posts/{slot['id']}/brief", data={"text": "From person A and B", "base": base}).status_code == 201
    # both people chat on the same post and every message is kept, in order
    for i in range(5):
        a.post(f"/api/c/posts/{slot['id']}/messages", {"body": f"A{i}"})
        b.post(f"/api/c/posts/{slot['id']}/messages", {"body": f"B{i}"})
    thread = [m["body"] for m in a.get(f"/api/c/posts/{slot['id']}").json["thread"] if m["type"] == "message"]
    assert len(thread) == 10 and set(thread) == {f"A{i}" for i in range(5)} | {f"B{i}" for i in range(5)}


def test_signup_exists_only_on_test_installs(app, anon):
    assert anon.get("/api/auth/options").json == {"signup": False}
    body = {"name": "Tester", "email": "tester@example.com", "password": "long-enough-pw"}
    assert anon.post("/api/auth/signup", json=body).status_code == 404  # a real server never offers it
    app.config["DEMO_SIGNUP"] = True
    assert anon.get("/api/auth/options").json == {"signup": True}
    assert anon.post("/api/auth/signup", json=dict(body, password="short")).status_code == 400
    assert anon.post("/api/auth/signup", json=dict(body, email="nope")).status_code == 400
    r = anon.post("/api/auth/signup", json=body)
    assert r.status_code == 201 and r.json["user"]["role"] == "admin" and anon.get("/api/auth/me").status_code == 200
    assert anon.post("/api/auth/signup", json=body).status_code == 409  # the email is taken
    other = app.test_client()
    assert other.post("/api/auth/login", json={"email": "tester@example.com", "password": "long-enough-pw"}).status_code == 200
