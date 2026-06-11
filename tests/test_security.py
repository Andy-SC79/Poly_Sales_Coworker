"""
tests/test_security.py
-----------------------
Security tests for the WhatsApp webhook.
Verifies that the Twilio signature validation works correctly.
No LLM or API keys required — tests the HTTP layer only.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from importlib import reload


@pytest.fixture
def production_client():
    """FastAPI test client with APP_ENV=production to enable signature validation."""
    with patch.dict("os.environ", {
        "APP_ENV": "production",
        "TWILIO_AUTH_TOKEN": "test_auth_token_1234567890abcdef",
    }):
        import config.settings as settings_module
        settings_module.get_settings.cache_clear()
        reload(settings_module)

        import channels.whatsapp as whatsapp_module
        reload(whatsapp_module)
        import api.main as main_module
        reload(main_module)
        yield TestClient(main_module.app, raise_server_exceptions=False)

    # Restore settings cache
    from config.settings import get_settings
    get_settings.cache_clear()


@pytest.fixture
def dev_client():
    """FastAPI test client in development mode — validation skipped."""
    with patch.dict("os.environ", {
        "APP_ENV": "development",
        "TWILIO_AUTH_TOKEN": "test_auth_token_1234567890abcdef",
    }):
        import config.settings as settings_module
        settings_module.get_settings.cache_clear()
        reload(settings_module)

        import channels.whatsapp as whatsapp_module
        reload(whatsapp_module)
        import api.main as main_module
        reload(main_module)
        yield TestClient(main_module.app, raise_server_exceptions=False)


class TestTwilioSignatureValidation:

    def test_missing_signature_rejected_in_production(self, production_client):
        """Requests without X-Twilio-Signature must be rejected with 403 in production."""
        response = production_client.post(
            "/channels/whatsapp/webhook",
            data={"From": "whatsapp:+573001234567", "Body": "Hola"},
        )
        assert response.status_code == 403

    def test_invalid_signature_rejected(self, production_client):
        """Requests with a wrong/spoofed signature must be rejected with 403."""
        response = production_client.post(
            "/channels/whatsapp/webhook",
            data={"From": "whatsapp:+573001234567", "Body": "Hola"},
            headers={"X-Twilio-Signature": "fakebase64fakesignature"},
        )
        assert response.status_code == 403

    def test_dev_mode_bypasses_validation(self, dev_client):
        """In development mode, requests without signatures must be processed (not 403)."""
        response = dev_client.post(
            "/channels/whatsapp/webhook",
            data={"From": "whatsapp:+573001234567", "Body": "Hola"},
        )
        # 403 should NOT appear in dev mode (may get 200 or 500 from LLM, but not 403)
        assert response.status_code != 403

    def test_empty_body_without_signature_in_dev(self, dev_client):
        """Empty message in dev mode should return a helpful TwiML response."""
        response = dev_client.post(
            "/channels/whatsapp/webhook",
            data={"From": "whatsapp:+573001234567", "Body": ""},
        )
        assert response.status_code != 403
        assert "application/xml" in response.headers.get("content-type", "")
