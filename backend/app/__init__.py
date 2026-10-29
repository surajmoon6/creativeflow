from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import ROOT, Config
from .models import db
from .security import ApiError, error_response

load_dotenv(ROOT / ".env")


def _secret_key():
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    # Local convenience: generate once and keep it out of git. On a server, set SECRET_KEY.
    path = ROOT / "backend" / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


def create_app(overrides: dict | None = None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config["SECRET_KEY"] = Config.SECRET_KEY or _secret_key()
    if overrides:
        app.config.update(overrides)
    logging.basicConfig(level=logging.INFO)
    if os.environ.get("TRUST_PROXY") == "1":
        # Behind Caddy/nginx: use the real client IP (rate limits) and https scheme (secure cookies, links).
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        # Several people use the app at once: readers must not wait for a writer, and a busy moment waits instead of failing.
        from sqlalchemy import event

        def _sqlite_pragmas(conn, _record):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=15000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        with app.app_context():
            event.listen(db.engine, "connect", _sqlite_pragmas)

    from .routes import admin, auth, calendar, client, plans, portal, quotes, team
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(client.bp)
    app.register_blueprint(quotes.bp)
    app.register_blueprint(quotes.public)
    app.register_blueprint(team.bp)
    app.register_blueprint(plans.bp)
    app.register_blueprint(calendar.bp)
    app.register_blueprint(portal.bp)

    @app.errorhandler(ApiError)
    def _api_error(e):
        db.session.rollback()
        return error_response(e)

    @app.errorhandler(HTTPException)
    def _http_error(e):
        if request.path.startswith("/api/"):
            msg = {404: "Not found.", 413: "That file is too large.", 405: "Method not allowed."}
            return jsonify(error=msg.get(e.code, e.description), code=e.name.lower()), e.code
        return e

    @app.errorhandler(Exception)
    def _server_error(e):
        db.session.rollback()
        app.logger.exception("Unhandled error")
        return jsonify(error="Something went wrong. Please try again."), 500

    @app.after_request
    def _headers(resp):
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")  # review tokens live in URLs
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Content-Security-Policy",
                     "default-src 'self'; img-src 'self' data: blob:; "
                     "style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self'; "
                     "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if request.path.startswith("/api/") and "Cache-Control" not in h:
            h["Cache-Control"] = "no-store"
        return resp

    # Serve the built frontend (production / single-process mode).
    dist = Path(app.config["FRONTEND_DIST"])

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path):
        if path.startswith("api/") or not dist.exists():
            return jsonify(error="Not found."), 404
        target = dist / path
        if path and target.is_file() and dist.resolve() in target.resolve().parents:
            return send_from_directory(dist, path, max_age=31536000 if path.startswith("assets/") else 0)
        return send_from_directory(dist, "index.html", max_age=0)

    from .cli import register
    register(app)

    with app.app_context():
        db.create_all()
        _add_missing_columns()
    return app


# create_all() never alters existing tables, so columns added after first run are added here.
_NEW_COLUMNS = {
    "projects": {
        "kind": "VARCHAR(20) NOT NULL DEFAULT 'project'",
        "watermark": "BOOLEAN NOT NULL DEFAULT TRUE",
        "preview_rev": "INTEGER NOT NULL DEFAULT 0",
        "advance_amount": "INTEGER NOT NULL DEFAULT 0",
        "advance_requested_at": "DATETIME",
        "advance_reminded_at": "DATETIME",
    },
    "notifications": {"quote_id": "INTEGER"},
    "plans": {"client_approval": "BOOLEAN NOT NULL DEFAULT FALSE", "payment_reminder": "BOOLEAN NOT NULL DEFAULT FALSE",
              "paid_through": "VARCHAR(7)", "pay_claimed": "VARCHAR(7)"},
    "comments": {"deliverable_id": "INTEGER", "author_name": "VARCHAR(120)", "seen_at": "DATETIME"},
    "quotes": {
        "closing": "TEXT",
        "revisions_included": "INTEGER NOT NULL DEFAULT 2",
        "advance_percent": "INTEGER NOT NULL DEFAULT 0",
        "scope_first": "BOOLEAN NOT NULL DEFAULT TRUE", "sections": "JSON", "billing": "VARCHAR(10) NOT NULL DEFAULT 'once'", "discount_label": "VARCHAR(80)",
        "recurring_start": "VARCHAR(10) NOT NULL DEFAULT 'now'",
        "plan_inclusions": "JSON",
    },
    "quote_items": {"complimentary": "BOOLEAN NOT NULL DEFAULT FALSE", "detail": "TEXT",
                    "period": "VARCHAR(10) NOT NULL DEFAULT 'once'", "list_price": "INTEGER"},
    "invoices": {"advance_paid": "INTEGER NOT NULL DEFAULT 0", "notes": "TEXT"},
    "project_versions": {"deliverable_id": "INTEGER", "seq": "INTEGER"},
    "advance_payments": {"proof_file_id": "INTEGER"},
    "users": {"active": "BOOLEAN NOT NULL DEFAULT TRUE", "client_id": "INTEGER",
              "can_approve": "BOOLEAN NOT NULL DEFAULT FALSE"},
    "deliverables": {"kind": "VARCHAR(20) NOT NULL DEFAULT 'post'", "scheduled_at": "DATETIME",
                     "platforms": "VARCHAR(160)", "caption": "TEXT", "media_url": "VARCHAR(500)", "posted_at": "DATETIME",
                     "client_seen_version_id": "INTEGER", "brief": "TEXT", "brief_file_ids": "JSON", "brief_at": "DATETIME",
                     "brief_by": "VARCHAR(120)", "brief_seen_at": "DATETIME"},
}


def _add_missing_columns():
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    added = set()
    for table, cols in _NEW_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                added.add((table, name))
    db.session.commit()
    _backfill(added)


def _backfill(added):
    """One-time upgrades of data that already exists, run only when the matching column was just added."""
    from .models import Deliverable, Project, ProjectVersion, Quote
    from . import services as sv
    if ("quotes", "revisions_included") in added:  # existing quotes pick up the studio's standard terms
        for q in Quote.query.all():
            q.revisions_included = int(sv.setting("default_revisions"))
            q.advance_percent = int(sv.setting("quote_advance_percent"))
    for p in Project.query.all():  # every project gets its first design, holding the versions it already has
        if Deliverable.query.filter_by(project_id=p.id).first():
            continue
        latest = p.versions[-1] if p.versions else None
        if p.status in ("approved", "finalization", "payment_pending", "paid", "delivered", "completed"):
            status = "approved"
        elif latest and latest.status in ("review", "changes_requested", "approved"):
            status = latest.status
        else:
            status = "pending"
        d = Deliverable(project_id=p.id, title=(p.name or "Design")[:200], position=0, status=status)
        db.session.add(d)
        db.session.flush()
        for v in p.versions:
            v.deliverable_id = d.id
    for v in ProjectVersion.query.filter(ProjectVersion.seq.is_(None)).all():
        v.seq = v.number
    db.session.commit()
