"""Phase 1A security regression: client-supplied embeddings must never become
REAL Face ID credentials.

Until a trusted server-side enrollment pipeline exists, the only enrollment
write path (POST /api/face/me/enroll) records SIMULATED credentials only, and
face_service.enroll() refuses REAL unless the (not yet existing) trusted
pipeline flag is passed.
"""
import math

import pytest

from app import models, security
from app.config import settings
from app.main import app
from app.services import face_service

NODE = {"X-Node-Key": "node-secret"}


@pytest.fixture(autouse=True)
def _node_key(monkeypatch):
    monkeypatch.setattr(settings, "FACE_NODE_API_KEY", "node-secret")


def vec(seed, n=16):
    return [math.sin(seed * (i + 1)) for i in range(n)]


def mk_user(db, name, role="doctor", status="active"):
    u = models.User(name=name, email=f"{name.lower()}@example.edu", role=role, status=status,
                    password_hash=security.hash_password("pw123456"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def auth(client, name):
    r = client.post("/api/auth/login", json={"email": f"{name.lower()}@example.edu", "password": "pw123456"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def body(**kw):
    return {"embedding": vec(3), "quality": 0.9, "liveness_passed": True, **kw}


def face_rows(db):
    return db.query(models.FaceCredential).all()


# ------------------------------------------------------------ fabricated REAL
def test_real_enrollment_from_client_embedding_is_forbidden(client, db_session):
    mk_user(db_session, "Ann")
    r = client.post("/api/face/me/enroll", json=body(source="REAL"), headers=auth(client, "Ann"))
    assert r.status_code == 403
    assert face_rows(db_session) == []
    assert "embedding" not in r.text
    actions = [a.action for a in db_session.query(models.AuditLog).all()]
    assert "face_enroll" not in actions and "face_reenroll" not in actions


@pytest.mark.parametrize("source", ["real", "Real", " REAL", "REAL ", "", "TRUSTED", "SERVER", "PRODUCTION"])
def test_source_variants_cannot_smuggle_real(client, db_session, source):
    mk_user(db_session, "Bob")
    r = client.post("/api/face/me/enroll", json=body(source=source), headers=auth(client, "Bob"))
    assert r.status_code in (400, 403, 422)
    assert face_rows(db_session) == []


def test_omitted_source_defaults_to_simulated_not_real(client, db_session):
    mk_user(db_session, "Cy")
    r = client.post("/api/face/me/enroll", json=body(), headers=auth(client, "Cy"))
    assert r.status_code == 201
    assert r.json()["source"] == "SIMULATED"
    assert [f.enrolled_source for f in face_rows(db_session)] == ["SIMULATED"]


def test_explicit_simulated_still_works(client, db_session):
    mk_user(db_session, "Di")
    r = client.post("/api/face/me/enroll", json=body(source="SIMULATED"), headers=auth(client, "Di"))
    assert r.status_code == 201 and r.json()["status"] == "ENROLLED" and r.json()["source"] == "SIMULATED"


def test_extra_fields_cannot_override_source_or_identity(client, db_session):
    a = mk_user(db_session, "Eve")
    victim = mk_user(db_session, "Vic")
    r = client.post("/api/face/me/enroll",
                    json=body(enrolled_source="REAL", user_id=victim.user_id, doctor_id=victim.user_id,
                              trusted_pipeline=True),
                    headers=auth(client, "Eve"))
    assert r.status_code == 201
    rows = face_rows(db_session)
    assert len(rows) == 1 and rows[0].user_id == a.user_id and rows[0].enrolled_source == "SIMULATED"


def test_reenrollment_cannot_upgrade_simulated_to_real(client, db_session):
    mk_user(db_session, "Flo")
    h = auth(client, "Flo")
    assert client.post("/api/face/me/enroll", json=body(), headers=h).status_code == 201
    assert client.post("/api/face/me/enroll", json=body(source="REAL"), headers=h).status_code == 403
    active = [f for f in face_rows(db_session) if f.status == "ENROLLED"]
    assert len(active) == 1 and active[0].enrolled_source == "SIMULATED"


# ------------------------------------------------------------ unauthorized
def test_unauthenticated_enrollment_rejected(client, db_session):
    assert client.post("/api/face/me/enroll", json=body(source="REAL")).status_code in (401, 403)
    assert client.post("/api/face/me/enroll", json=body()).status_code in (401, 403)
    assert face_rows(db_session) == []


def test_node_key_cannot_enroll(client, db_session):
    """Door-node credentials authorize verification only; they must not be a
    way to create templates."""
    door = models.Door(code="R9", name="R9", building="B", fail_mode="secure", online=True, locked=True)
    db_session.add(door)
    db_session.commit()
    for path in ("/api/face/me/enroll", "/api/face/node/enroll"):
        r = client.post(path, json=body(source="REAL"), headers=NODE)
        assert r.status_code in (401, 403, 404, 405)
    client.post("/api/face/node/verify", json={"door_code": "R9", "embedding": vec(5), "quality": 0.9,
                                               "liveness_passed": True}, headers=NODE)
    assert face_rows(db_session) == []


# ------------------------------------------------------------ service layer
def test_service_refuses_real_without_trusted_pipeline(db_session):
    u = mk_user(db_session, "Gus")
    with pytest.raises(PermissionError):
        face_service.enroll(db_session, u, embedding=vec(2), quality=0.9, liveness_passed=True,
                            model_version="t", source="REAL", actor=u)
    assert face_rows(db_session) == []


def test_service_rejects_unknown_source(db_session):
    u = mk_user(db_session, "Hal")
    with pytest.raises(ValueError):
        face_service.enroll(db_session, u, embedding=vec(2), quality=0.9, liveness_passed=True,
                            model_version="t", source="whatever", actor=u)
    assert face_rows(db_session) == []


def test_service_allows_simulated(db_session):
    u = mk_user(db_session, "Ian")
    row = face_service.enroll(db_session, u, embedding=vec(2), quality=0.9, liveness_passed=True,
                              model_version="t", source="SIMULATED", actor=u)
    db_session.commit()
    assert row.enrolled_source == "SIMULATED"


# ------------------------------------------------------------ no bypass route
def test_only_one_face_route_can_create_a_credential():
    """Guards against a new write route being added under /api/face (or any
    route elsewhere) without this restriction being reviewed. Every non-GET
    face route is listed; adding one forces an explicit update here."""
    write_routes = set()
    # The OpenAPI schema is used (not app.routes) because included routers are
    # not always flattened into app.routes on newer FastAPI versions.
    for path, ops in app.openapi()["paths"].items():
        methods = {m.upper() for m in ops} - {"GET", "HEAD", "OPTIONS"}
        if path.startswith("/api/face") and methods:
            write_routes.add((path, tuple(sorted(methods))))
    assert write_routes == {
        ("/api/face/me/enroll", ("POST",)),            # SIMULATED-only (this phase)
        ("/api/face/me/revoke", ("POST",)),
        ("/api/face/users/{user_id}/revoke", ("POST",)),
        ("/api/face/users/{user_id}/disable", ("POST",)),
        ("/api/face/node/verify", ("POST",)),          # decision only, creates no credential
        ("/api/face/node/ack", ("POST",)),
    }


def test_enrollment_path_is_the_only_caller_of_service_enroll():
    """Static check: nothing else in app/ calls face_service.enroll."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    callers = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if "face_service.enroll(" in text or "models.FaceCredential(" in text:
            callers.append(p.relative_to(root).as_posix())
    assert sorted(callers) == ["routers/face.py", "services/face_service.py"]
