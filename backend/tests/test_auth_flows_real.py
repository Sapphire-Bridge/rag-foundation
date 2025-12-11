from fastapi.testclient import TestClient


def test_register_and_login_roundtrip(client: TestClient) -> None:
    email = "auth-flow@example.com"
    password = "StrongPass123!"

    # Register user
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert r.status_code in (200, 201), r.text

    # Login with the new credentials (JSON body in this implementation)
    r2 = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "access_token" in body
    assert body.get("token_type", "bearer").lower() == "bearer"
