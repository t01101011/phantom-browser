"""Desktop GUI integration/security checks for the HTTP control plane."""
from fastapi.testclient import TestClient

from phantom.api.app import create_app
from phantom.api.auth import load_or_generate_token


def test_tauri_and_vite_origins_get_exact_cors_headers():
    with TestClient(create_app()) as client:
        for origin in (
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "http://localhost:1420",
        ):
            response = client.options(
                "/v1/profiles",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,last-event-id",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert "Authorization" in response.headers["access-control-allow-headers"]
            assert response.headers.get("access-control-allow-credentials") != "true"


def test_untrusted_origin_is_not_cors_enabled():
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/profiles",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_bearer_still_required_with_desktop_origin():
    with TestClient(create_app()) as client:
        denied = client.get("/v1/profiles", headers={"Origin": "tauri://localhost"})
        allowed = client.get("/v1/profiles", headers={"Origin": "tauri://localhost", "Authorization": f"Bearer {load_or_generate_token()}"})
    assert denied.status_code == 403
    assert allowed.status_code == 200
