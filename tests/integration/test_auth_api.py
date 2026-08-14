from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api import auth as auth_module
from apps.api import main as api_main
from apps.api.database import get_db
from apps.api.main import app
from apps.api.models import Base


@pytest.fixture
def authenticated_app(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    monkeypatch.setattr(auth_module, "SessionLocal", factory)
    monkeypatch.setattr(api_main.settings, "auth_required", True)
    monkeypatch.setattr(api_main.settings, "auth_cookie_secure", False)
    monkeypatch.setattr(api_main.settings, "auth_password_iterations", 2_000)
    app.dependency_overrides[get_db] = override_db
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()


def register(client: TestClient, *, email: str, workspace: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": email.split("@")[0].title(),
            "email": email,
            "password": "StrongPass123",
            "workspace_name": workspace,
            "timezone": "Europe/Moscow",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_creates_private_session_and_workspace_boundary(
    authenticated_app: sessionmaker[Session],
) -> None:
    with TestClient(app) as first_client:
        first = register(
            first_client,
            email="owner-one@example.com",
            workspace="First Studio",
        )
        first_workspace = str(first["workspace"]["id"])  # type: ignore[index]
        context = first_client.get("/api/v1/context")
        assert context.status_code == 200
        assert context.json()["workspace_id"] == first_workspace
        assert context.json()["onboarding_status"] == "in_progress"
        assert first_client.get("/api/v1/admin/providers").status_code == 403

    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/context").status_code == 401

    with TestClient(app) as second_client:
        second = register(
            second_client,
            email="owner-two@example.com",
            workspace="Second Studio",
        )
        second_workspace = str(second["workspace"]["id"])  # type: ignore[index]
        assert second_workspace != first_workspace
        denied = second_client.get(f"/api/v1/workspaces/{first_workspace}/channels")
        assert denied.status_code == 403


def test_login_logout_and_password_rotation(
    authenticated_app: sessionmaker[Session],
) -> None:
    with TestClient(app) as client:
        register(client, email="owner@example.com", workspace="Owner Studio")
        changed = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "StrongPass123",
                "new_password": "BetterPass456",
            },
        )
        assert changed.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

        old_password = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "StrongPass123"},
        )
        assert old_password.status_code == 401
        new_password = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "BetterPass456"},
        )
        assert new_password.status_code == 200
        assert client.get("/api/v1/context").status_code == 200
