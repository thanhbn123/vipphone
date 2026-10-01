"""Turnstile — adapter, chính sách fail-open/fail-closed, và cấu hình công khai.

Không test nào ở đây gọi ra Internet: `verify_turnstile` nhận `client` nên ta truyền
`httpx.MockTransport`. Một test phụ thuộc Cloudflare thật là một test sẽ đỏ vì lý do
không liên quan tới sản phẩm.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.errors import ExternalServiceUnavailable, SpamRejected
from app.security import build_strict_csp, verify_turnstile

pytestmark = pytest.mark.integration


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"success": True})


def fail_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"success": False, "error-codes": ["invalid-input-response"]})


def boom_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"success": False})


# ======================================================= adapter: chưa cấu hình
def test_skips_when_not_configured_and_not_required(monkeypatch):
    async def _body():
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", None)
        monkeypatch.setattr(security.settings, "turnstile_required", False)

        # Không ném gì cả, kể cả khi không có token.
        await verify_turnstile(None, "1.2.3.4")

    asyncio.run(_body())


def test_fails_closed_when_required_but_secret_missing(monkeypatch):
    async def _body():
        """Yêu cầu Turnstile mà chưa có secret ⇒ TỪ CHỐI, không im lặng cho qua."""
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", None)
        monkeypatch.setattr(security.settings, "turnstile_required", True)

        with pytest.raises(SpamRejected) as excinfo:
            await verify_turnstile("bat-ky", "1.2.3.4")
        assert excinfo.value.status_code == 403

    asyncio.run(_body())


# ========================================================= adapter: đã cấu hình
def test_missing_token_is_rejected_when_configured(monkeypatch):
    async def _body():
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-gia")

        with pytest.raises(SpamRejected):
            await verify_turnstile(None, "1.2.3.4")

    asyncio.run(_body())


def test_valid_token_passes(monkeypatch):
    async def _body():
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-gia")

        async with make_client(ok_handler) as client:
            await verify_turnstile("token-tot", "1.2.3.4", client=client)

    asyncio.run(_body())


def test_rejected_token_raises_spam(monkeypatch):
    async def _body():
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-gia")

        async with make_client(fail_handler) as client:
            with pytest.raises(SpamRejected):
                await verify_turnstile("token-sai", "1.2.3.4", client=client)

    asyncio.run(_body())


def test_cloudflare_error_is_not_swallowed(monkeypatch):
    async def _body():
        """Cloudflare lỗi ⇒ 503 rõ ràng, KHÔNG coi là 'qua' và KHÔNG nuốt lỗi."""
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-gia")

        async with make_client(boom_handler) as client:
            with pytest.raises(ExternalServiceUnavailable) as excinfo:
                await verify_turnstile("token", "1.2.3.4", client=client)
        assert excinfo.value.status_code == 503

    asyncio.run(_body())


def test_secret_is_sent_to_siteverify(monkeypatch):
    async def _body():
        """Chứng minh secret thật sự được gửi ĐI (ở server), không phải bỏ quên."""
        from app import security

        monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-gia")
        seen: dict = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.content.decode()
            return httpx.Response(200, json={"success": True})

        async with make_client(capture) as client:
            await verify_turnstile("token-tot", "9.9.9.9", client=client)

        assert "secret-gia" in seen["body"]
        assert "token-tot" in seen["body"]
        assert "9.9.9.9" in seen["body"]

    asyncio.run(_body())


# ================================================== endpoint: chính sách thật
def test_lead_without_token_succeeds_when_turnstile_disabled(client, valid_lead_payload):
    payload = dict(valid_lead_payload)
    payload.pop("turnstile_token", None)
    assert client.post("/api/leads", json=payload).status_code == 201


def test_lead_is_rejected_when_verifier_rejects(client, valid_lead_payload, monkeypatch):
    """Endpoint phải CHẶN khi verifier chặn — đo qua HTTP, không qua đọc mã."""
    import app.routers.leads as leads_router

    async def reject(token, remote_ip, **kwargs):
        raise SpamRejected("bị chặn vì test")

    monkeypatch.setattr(leads_router, "verify_turnstile", reject)

    response = client.post("/api/leads", json=valid_lead_payload)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "SPAM_REJECTED"


def test_token_is_forwarded_to_verifier(client, valid_lead_payload, monkeypatch):
    """Token khách gửi phải tới được verifier, không bị nuốt dọc đường."""
    import app.routers.leads as leads_router

    seen: dict = {}

    async def capture(token, remote_ip, **kwargs):
        seen["token"] = token

    monkeypatch.setattr(leads_router, "verify_turnstile", capture)

    payload = {**valid_lead_payload, "turnstile_token": "token-cua-khach"}
    assert client.post("/api/leads", json=payload).status_code == 201
    assert seen["token"] == "token-cua-khach"


def test_cloudflare_outage_surfaces_as_503(client, valid_lead_payload, monkeypatch):
    import app.routers.leads as leads_router

    async def outage(token, remote_ip, **kwargs):
        raise ExternalServiceUnavailable("Turnstile")

    monkeypatch.setattr(leads_router, "verify_turnstile", outage)

    response = client.post("/api/leads", json=valid_lead_payload)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EXTERNAL_SERVICE_UNAVAILABLE"


# =========================================================== public config
def test_public_config_reports_disabled_by_default(client):
    body = client.get("/api/public-config").json()
    assert body["turnstile"]["enabled"] is False
    assert body["turnstile"]["site_key"] is None


def test_public_config_exposes_site_key_but_NEVER_the_secret(client, monkeypatch):
    from app import security

    monkeypatch.setattr(security.settings, "turnstile_site_key", "site-key-cong-khai")
    monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-tuyet-mat")

    response = client.get("/api/public-config")
    body = response.json()

    assert body["turnstile"]["enabled"] is True
    assert body["turnstile"]["site_key"] == "site-key-cong-khai"
    # Chốt quan trọng nhất: secret KHÔNG được xuất hiện ở bất kỳ đâu trong response.
    assert "secret-tuyet-mat" not in response.text


def test_public_config_half_configured_is_not_enabled_and_warns(client, monkeypatch):
    """Chỉ có secret mà thiếu site key ⇒ CHƯA bật, và phải CẢNH BÁO."""
    from app import security

    monkeypatch.setattr(security.settings, "turnstile_site_key", None)
    monkeypatch.setattr(security.settings, "turnstile_secret_key", "secret-tuyet-mat")

    body = client.get("/api/public-config").json()
    assert body["turnstile"]["enabled"] is False
    assert body["turnstile"]["warning"], "phải cảnh báo khi cấu hình nửa vời"


def test_public_config_warns_when_required_but_incomplete(client, monkeypatch):
    from app import security

    monkeypatch.setattr(security.settings, "turnstile_site_key", None)
    monkeypatch.setattr(security.settings, "turnstile_secret_key", None)
    monkeypatch.setattr(security.settings, "turnstile_required", True)

    body = client.get("/api/public-config").json()
    warning = body["turnstile"]["warning"] or ""
    assert "TURNSTILE_REQUIRED" in warning


# =================================================================== CSP
def test_csp_allows_cloudflare_only_when_turnstile_enabled():
    off = build_strict_csp(turnstile=False)
    on = build_strict_csp(turnstile=True)

    assert "challenges.cloudflare.com" not in off, "CSP mặc định KHÔNG được mở cho bên thứ ba"
    assert "frame-src" not in off

    assert "https://challenges.cloudflare.com" in on
    assert "frame-src https://challenges.cloudflare.com" in on


def test_csp_header_is_strict_when_turnstile_off(client, monkeypatch):
    from app import security

    monkeypatch.setattr(security.settings, "turnstile_site_key", None)
    monkeypatch.setattr(security.settings, "turnstile_secret_key", None)

    csp = client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "challenges.cloudflare.com" not in csp
