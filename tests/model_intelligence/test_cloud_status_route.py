"""Tests for GET /models/cloud/status (HOS-066C) — handle_get_cloud_status().

_get_cloud_catalog()/_cloud_authorized() are monkeypatched directly rather
than exercised through real settings/Aegis config, so this stays a fast,
hermetic test of the handler's own response shaping.
"""
from __future__ import annotations

from backend.model_intelligence import routes as mi_routes


class _FakeCatalog:
    def __init__(self, status: dict) -> None:
        self._status = status

    def status(self) -> dict:
        return self._status


class TestNotConfigured:
    def test_reports_unconfigured_when_no_catalog(self, monkeypatch):
        monkeypatch.setattr(mi_routes, "_get_cloud_catalog", lambda: None)
        result = mi_routes.handle_get_cloud_status()
        assert result["success"] is True
        assert result["configured"] is False
        assert result["authorized"] is False
        assert "OPENROUTER_API_KEY" in result["message"]


class TestConfigured:
    def test_authorized_reports_real_catalog_snapshot(self, monkeypatch):
        fake_status = {
            "catalog_size": 7, "catalog_age_s": 12.3,
            "quota_remaining": 40, "quota_checked_age_s": 5.0,
            "reserve_daily_requests": 5,
        }
        monkeypatch.setattr(mi_routes, "_get_cloud_catalog", lambda: _FakeCatalog(fake_status))
        monkeypatch.setattr(mi_routes, "_cloud_authorized", lambda: True)
        result = mi_routes.handle_get_cloud_status()
        assert result["configured"] is True
        assert result["authorized"] is True
        assert result["catalog_size"] == 7
        assert result["quota_remaining"] == 40

    def test_unauthorized_explains_why_in_the_message(self, monkeypatch):
        monkeypatch.setattr(mi_routes, "_get_cloud_catalog",
                            lambda: _FakeCatalog({"catalog_size": 0}))
        monkeypatch.setattr(mi_routes, "_cloud_authorized", lambda: False)
        result = mi_routes.handle_get_cloud_status()
        assert result["configured"] is True
        assert result["authorized"] is False
        assert "autonomy_level" in result["message"]
