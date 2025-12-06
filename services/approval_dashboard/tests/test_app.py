"""Tests for Approval Dashboard application."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.approval_dashboard.src.config import Settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_database_url(self):
        """Test database URL construction."""
        settings = Settings(
            postgres_host="db.example.com",
            postgres_port=5432,
            postgres_user="user",
            postgres_password="pass",
            postgres_db="mydb",
        )
        expected = "postgresql://user:pass@db.example.com:5432/mydb"
        assert settings.database_url == expected

    def test_redis_url(self):
        """Test Redis URL construction."""
        settings = Settings(redis_host="redis.example.com", redis_port=6380)
        assert settings.redis_url == "redis://redis.example.com:6380/0"

    def test_elasticsearch_url(self):
        """Test Elasticsearch URL construction."""
        settings = Settings(elasticsearch_host="es.example.com", elasticsearch_port=9201)
        assert settings.elasticsearch_url == "http://es.example.com:9201"

    def test_default_values(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8080
        assert settings.stories_per_page == 20
        assert settings.logs_per_page == 50


class TestDashboardApp:
    """Tests for Dashboard FastAPI application."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute.return_value.scalar.return_value = 0
        session.execute.return_value.scalars.return_value.all.return_value = []
        return session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client with mocked dependencies."""
        with patch("services.approval_dashboard.src.app.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            from services.approval_dashboard.src.app import app

            yield TestClient(app)

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "approval-dashboard"

    def test_dashboard_renders(self, client, mock_session):
        """Test dashboard page renders."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Pipeline Status" in response.text

    def test_stories_list_renders(self, client, mock_session):
        """Test stories list page renders."""
        response = client.get("/stories")
        assert response.status_code == 200
        assert "Stories" in response.text

    def test_stories_list_with_status_filter(self, client, mock_session):
        """Test stories list with status filter."""
        response = client.get("/stories?status=pending")
        assert response.status_code == 200

    def test_story_not_found(self, client, mock_session):
        """Test 404 for non-existent story."""
        mock_session.get.return_value = None
        response = client.get("/stories/999")
        assert response.status_code == 404

    def test_approve_story_not_found(self, client, mock_session):
        """Test approve returns 404 for non-existent story."""
        mock_session.get.return_value = None
        response = client.post("/stories/999/approve")
        assert response.status_code == 404

    def test_approve_story_wrong_status(self, client, mock_session):
        """Test approve returns 400 for non-pending story."""
        mock_story = MagicMock()
        mock_story.status = "processing"
        mock_session.get.return_value = mock_story

        response = client.post("/stories/1/approve")
        assert response.status_code == 400

    def test_reject_story_not_found(self, client, mock_session):
        """Test reject returns 404 for non-existent story."""
        mock_session.get.return_value = None
        response = client.post("/stories/999/reject", data={"reason": "test"})
        assert response.status_code == 404

    def test_retry_story_not_found(self, client, mock_session):
        """Test retry returns 404 for non-existent story."""
        mock_session.get.return_value = None
        response = client.post("/stories/999/retry")
        assert response.status_code == 404

    def test_retry_story_wrong_status(self, client, mock_session):
        """Test retry returns 400 for non-failed story."""
        mock_story = MagicMock()
        mock_story.status = "pending"
        mock_session.get.return_value = mock_story

        response = client.post("/stories/1/retry")
        assert response.status_code == 400

    def test_logs_page_renders(self, client):
        """Test logs page renders even with ES errors."""
        with patch("services.approval_dashboard.src.app.LogService") as mock_log_service:
            mock_instance = MagicMock()
            mock_instance.search_logs.return_value = ([], 0)
            mock_log_service.return_value = mock_instance

            response = client.get("/logs")
            assert response.status_code == 200
            assert "Logs" in response.text

    def test_batches_list_renders(self, client, mock_session):
        """Test batches list page renders."""
        response = client.get("/batches")
        assert response.status_code == 200
        assert "Batches" in response.text


class TestLogService:
    """Tests for LogService."""

    def test_elasticsearch_url_property(self):
        """Test Elasticsearch URL is stored correctly."""
        from services.approval_dashboard.src.logs import LogService

        service = LogService("http://localhost:9200")
        assert service.es_url == "http://localhost:9200"

    def test_health_check_returns_false_on_error(self):
        """Test health check returns False when ES is unavailable."""
        from services.approval_dashboard.src.logs import LogService

        with patch("services.approval_dashboard.src.logs.Elasticsearch") as mock_es:
            mock_es.return_value.ping.side_effect = Exception("Connection failed")

            service = LogService("http://localhost:9200")
            assert service.health_check() is False

    @pytest.mark.asyncio
    async def test_search_logs_handles_errors(self):
        """Test search_logs returns empty on errors."""
        from services.approval_dashboard.src.logs import LogService

        with patch("services.approval_dashboard.src.logs.Elasticsearch") as mock_es:
            mock_es.return_value.search.side_effect = Exception("Search failed")

            service = LogService("http://localhost:9200")
            logs, total = await service.search_logs()

            assert logs == []
            assert total == 0


class TestTemplateFilters:
    """Tests for Jinja2 template filters."""

    def test_format_datetime_with_value(self):
        """Test datetime formatting with valid value."""
        from datetime import datetime

        from services.approval_dashboard.src.app import format_datetime

        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = format_datetime(dt)
        assert result == "2024-01-15 10:30:45"

    def test_format_datetime_with_none(self):
        """Test datetime formatting with None."""
        from services.approval_dashboard.src.app import format_datetime

        result = format_datetime(None)
        assert result == "N/A"

    def test_truncate_text_short(self):
        """Test truncate with short text."""
        from services.approval_dashboard.src.app import truncate_text

        result = truncate_text("Short text", 100)
        assert result == "Short text"

    def test_truncate_text_long(self):
        """Test truncate with long text."""
        from services.approval_dashboard.src.app import truncate_text

        result = truncate_text("A" * 300, 200)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")
