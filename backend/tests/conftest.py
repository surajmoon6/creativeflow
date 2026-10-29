import io

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app
from app.models import User, db

ADMIN = ("admin@test.local", "correct-horse-battery")


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "STORAGE_DIR": str(tmp_path / "storage"),
        "SECRET_KEY": "test-secret",
        "RATELIMIT_ENABLED": False,
        "PUBLIC_URL": "http://test",
    })
    with app.app_context():
        db.create_all()
        db.session.add(User(email=ADMIN[0], name="Admin", password_hash=generate_password_hash(ADMIN[1])))
        db.session.commit()
    yield app


def png(w=1080, h=1350, color=(20, 40, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


class Admin:
    def __init__(self, client, creds=ADMIN):
        self.c = client
        r = client.post("/api/auth/login", json={"email": creds[0], "password": creds[1]})
        assert r.status_code == 200, r.json
        self.csrf = r.json["csrf"]

    def _h(self):
        return {"X-CSRF-Token": self.csrf}

    def get(self, url):
        return self.c.get(url)

    def post(self, url, json=None, data=None):
        if data is not None:
            return self.c.post(url, data=data, headers=self._h(), content_type="multipart/form-data")
        return self.c.post(url, json=json or {}, headers=self._h())

    def put(self, url, json):
        return self.c.put(url, json=json, headers=self._h())

    def delete(self, url):
        return self.c.delete(url, headers=self._h())

    # shortcuts
    def new_project(self, client_name="ABC Events", name="Nagpur Marathon 2026", **kw):
        c = self.post("/api/clients", {"name": client_name, "company": client_name}).json
        body = dict(client_id=c["id"], name=name, project_type="Instagram Poster", amount=150000,
                    gst_enabled=True, gst_rate_bp=1800, revisions_included=2, extra_revision_price=50000)
        body.update(kw)
        r = self.post("/api/projects", body)
        assert r.status_code == 201, r.json
        return r.json

    def upload_version(self, pid, data=None, name="poster-final.png", note=""):
        r = self.post(f"/api/projects/{pid}/versions",
                      data={"file": (io.BytesIO(data or png()), name), "note": note})
        assert r.status_code == 200, r.json
        return r.json

    def upload_final(self, pid, data, name, label):
        return self.post(f"/api/projects/{pid}/finals",
                         data={"file": (io.BytesIO(data), name), "label": label})


@pytest.fixture()
def admin(app):
    return Admin(app.test_client())


@pytest.fixture()
def anon(app):
    return app.test_client()


def approved_project_with_invoice(admin, anon, **kw):
    """Walks a project to Payment Pending. Returns (detail, token, final_bytes)."""
    p = admin.new_project(**kw)
    d = admin.upload_version(p["id"])
    token = d["active_link"]["token"]
    view = anon.get(f"/api/r/{token}").json
    assert anon.post(f"/api/r/{token}/approve", json={"version_id": view["deliverables"][0]["latest_version_id"]}).status_code == 200
    final = png(1080, 1350, (1, 2, 3))
    assert admin.upload_final(p["id"], final, "poster.png", "PNG").status_code == 200
    d = admin.post(f"/api/projects/{p['id']}/invoice").json
    assert d["status"] == "payment_pending"
    return d, token, final
