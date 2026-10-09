"""Configuration helpers: CORS origin parsing and insecure-default warnings.
The warnings must never contain secret values."""
from app import config
from app.config import settings


def test_allowed_origins_default_is_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "*")
    assert config.allowed_origins_list() == ["*"]


def test_allowed_origins_parses_comma_separated(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "http://localhost:5173, https://dash.example.edu ,")
    assert config.allowed_origins_list() == ["http://localhost:5173", "https://dash.example.edu"]


def test_allowed_origins_empty_falls_back_to_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", " , ")
    assert config.allowed_origins_list() == ["*"]


def test_warns_on_dev_jwt_secret_without_leaking_values(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", config.DEV_JWT_SECRET)
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "*")
    warnings = config.insecure_configuration_warnings()
    assert any("JWT_SECRET" in w for w in warnings)
    assert any("CORS" in w for w in warnings)
    assert all(config.DEV_JWT_SECRET not in w for w in warnings)


def test_no_jwt_or_cors_warning_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "a-real-long-random-secret-value")
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "https://dash.example.edu")
    warnings = config.insecure_configuration_warnings()
    assert not any("JWT_SECRET" in w or "CORS" in w for w in warnings)
