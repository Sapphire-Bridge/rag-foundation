"""
Infrastructure verification tests.

Run first to ensure test setup is correct.
"""

import pytest


class TestDatabaseIsolation:
    """Verify DB isolation works correctly."""

    def test_commit_does_not_escape(self, db_session):
        """Commits should be contained within test transaction."""
        from app.models import User

        user = User(email="isolation-test@example.com", hashed_password="", is_active=True)
        db_session.add(user)
        db_session.commit()  # Should not escape!

        found = db_session.query(User).filter(User.email == "isolation-test@example.com").first()
        assert found is not None

    def test_previous_test_data_not_visible(self, db_session):
        """Data from previous test should not be visible."""
        from app.models import User

        found = db_session.query(User).filter(User.email == "isolation-test@example.com").first()
        assert found is None, "Previous test's data leaked!"


class TestFactoriesUseFlush:
    """Verify factories use flush, not commit."""

    def test_factory_user_has_id(self, db_session):
        """Factory should assign ID via flush."""
        from tests.fixtures.factories import UserFactory

        user = UserFactory.create(db_session)
        assert user.id is not None

    def test_factory_data_isolated(self, db_session):
        """Factory data should not leak between tests."""
        from tests.fixtures.factories import UserFactory
        from app.models import User

        UserFactory.create(db_session, email="factory-isolation@example.com")

        count = db_session.query(User).filter(User.email == "factory-isolation@example.com").count()
        assert count == 1


class TestHttpBlocking:
    """Verify HTTP calls are blocked."""

    def test_httpx_blocked(self):
        """httpx calls should raise."""
        import httpx

        with pytest.raises(RuntimeError, match="blocked"):
            httpx.get("https://example.com")

    def test_requests_blocked(self):
        """requests calls should raise (if installed)."""
        try:
            import requests
        except ImportError:
            pytest.skip("requests not installed")
        else:
            with pytest.raises(RuntimeError, match="blocked"):
                requests.get("https://example.com")


class TestDependencyOverride:
    """Verify DB dependency is overridden in routes."""

    def test_route_uses_test_session(self, client, db_session):
        """Routes should use the test session."""
        from tests.fixtures.factories import UserFactory
        from app.auth import create_access_token

        user = UserFactory.create_admin(db_session)
        db_session.commit()
        token = create_access_token(user_id=user.id)

        resp = client.get(
            "/api/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        assert resp.status_code == 200
        users = resp.json()
        assert any(u["email"] == user.email for u in users)
