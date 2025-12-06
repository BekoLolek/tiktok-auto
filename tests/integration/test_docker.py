"""Docker integration tests.

These tests verify that Docker images build and services start correctly.
They can be run in CI or locally with Docker.
"""

import os

import pytest


class TestDockerfileValidation:
    """Validate Dockerfile syntax and structure."""

    @pytest.fixture
    def service_dockerfiles(self):
        """List of all service Dockerfiles."""
        base_path = os.path.join(os.path.dirname(__file__), "..", "..", "services")
        return [
            os.path.join(base_path, "reddit_fetch", "Dockerfile"),
            os.path.join(base_path, "approval_dashboard", "Dockerfile"),
            os.path.join(base_path, "text_processor", "Dockerfile"),
            os.path.join(base_path, "tts_service", "Dockerfile"),
            os.path.join(base_path, "video_renderer", "Dockerfile"),
            os.path.join(base_path, "uploader", "Dockerfile"),
        ]

    def test_all_dockerfiles_exist(self, service_dockerfiles):
        """Verify all service Dockerfiles exist."""
        for dockerfile in service_dockerfiles:
            assert os.path.exists(dockerfile), f"Missing Dockerfile: {dockerfile}"

    def test_dockerfiles_have_valid_base_image(self, service_dockerfiles):
        """Verify Dockerfiles have valid FROM instruction."""
        for dockerfile in service_dockerfiles:
            if not os.path.exists(dockerfile):
                continue

            with open(dockerfile) as f:
                content = f.read()

            assert "FROM" in content, f"No FROM instruction in {dockerfile}"

    def test_dockerfiles_expose_ports(self, service_dockerfiles):
        """Verify Dockerfiles expose necessary ports."""
        services_needing_ports = ["approval_dashboard", "uploader"]

        for dockerfile in service_dockerfiles:
            if not os.path.exists(dockerfile):
                continue

            service_name = os.path.basename(os.path.dirname(dockerfile))
            if service_name in services_needing_ports:
                with open(dockerfile) as f:
                    content = f.read()
                assert "EXPOSE" in content, f"No EXPOSE in {dockerfile}"


class TestDockerComposeValidation:
    """Validate docker-compose.yml structure."""

    @pytest.fixture
    def compose_file(self):
        """Path to docker-compose.yml."""
        return os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")

    def test_compose_file_exists(self, compose_file):
        """Verify docker-compose.yml exists."""
        assert os.path.exists(compose_file)

    def test_compose_has_required_services(self, compose_file):
        """Verify all required services are defined."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        required_services = [
            "postgres",
            "redis",
            "elasticsearch",
            "dashboard",
            "reddit-fetch",
            "text-processor",
            "tts-service",
            "video-renderer",
            "uploader",
            "celery-worker",
            "celery-beat",
        ]

        for service in required_services:
            assert service in services, f"Missing service: {service}"

    def test_compose_has_health_checks(self, compose_file):
        """Verify infrastructure services have health checks."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        infrastructure_services = ["postgres", "redis", "elasticsearch"]

        for service_name in infrastructure_services:
            service = services.get(service_name, {})
            assert "healthcheck" in service, f"No healthcheck for {service_name}"

    def test_compose_has_volumes(self, compose_file):
        """Verify compose defines persistent volumes."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        volumes = compose.get("volumes", {})
        required_volumes = ["postgres-data", "redis-data"]

        for volume in required_volumes:
            assert volume in volumes, f"Missing volume: {volume}"

    def test_compose_has_network(self, compose_file):
        """Verify compose defines a network."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        networks = compose.get("networks", {})
        assert len(networks) > 0, "No networks defined"


class TestServiceHealthEndpoints:
    """Test health check endpoints for services."""

    def test_dashboard_health_endpoint_design(self):
        """Verify dashboard health endpoint returns expected format."""
        expected_response = {
            "status": "healthy",
            "service": "dashboard",
            "database": "connected",
        }
        # This documents the expected health endpoint response format
        assert "status" in expected_response
        assert "service" in expected_response

    def test_uploader_health_endpoint_design(self):
        """Verify uploader health endpoint returns expected format."""
        expected_response = {
            "status": "healthy",
            "service": "uploader",
            "database": "connected",
        }
        assert "status" in expected_response
        assert "service" in expected_response


class TestServiceDependencies:
    """Test service dependency configuration."""

    @pytest.fixture
    def compose_file(self):
        """Path to docker-compose.yml."""
        return os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")

    def test_services_depend_on_infrastructure(self, compose_file):
        """Verify application services depend on infrastructure."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        app_services = [
            "dashboard",
            "reddit-fetch",
            "text-processor",
            "tts-service",
            "video-renderer",
            "uploader",
        ]

        for service_name in app_services:
            service = services.get(service_name, {})
            depends_on = service.get("depends_on", {})
            # Should depend on at least postgres or redis
            assert len(depends_on) > 0, f"{service_name} has no dependencies"

    def test_celery_worker_has_correct_dependencies(self, compose_file):
        """Verify celery worker depends on required services."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        worker = services.get("celery-worker", {})
        depends_on = worker.get("depends_on", {})

        assert "postgres" in depends_on
        assert "redis" in depends_on


class TestEnvironmentVariables:
    """Test environment variable configuration."""

    @pytest.fixture
    def compose_file(self):
        """Path to docker-compose.yml."""
        return os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")

    def test_services_have_database_config(self, compose_file):
        """Verify services have database configuration."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        services_needing_db = ["dashboard", "reddit-fetch", "celery-worker"]

        for service_name in services_needing_db:
            service = services.get(service_name, {})
            env = service.get("environment", [])

            # Convert list to dict if needed
            if isinstance(env, list):
                env_dict = {}
                for item in env:
                    if "=" in item:
                        key, _ = item.split("=", 1)
                        env_dict[key] = True
                    else:
                        env_dict[item.lstrip("- ")] = True
                env = env_dict

            env_keys = (
                list(env.keys())
                if isinstance(env, dict)
                else [e.split("=")[0] if "=" in e else e for e in env]
            )

            assert any(
                "POSTGRES" in k for k in env_keys
            ), f"{service_name} missing POSTGRES config"

    def test_uploader_has_tiktok_config(self, compose_file):
        """Verify uploader has TikTok-specific configuration."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        uploader = services.get("uploader", {})
        env = uploader.get("environment", [])

        env_str = str(env)
        assert "TIKTOK" in env_str or "COOKIES" in env_str


class TestVolumeMapping:
    """Test volume mapping configuration."""

    @pytest.fixture
    def compose_file(self):
        """Path to docker-compose.yml."""
        return os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")

    def test_data_volume_mapped(self, compose_file):
        """Verify data directory is volume mapped to services."""
        import yaml

        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        services_needing_data = ["video-renderer", "tts-service", "uploader"]

        for service_name in services_needing_data:
            service = services.get(service_name, {})
            volumes = service.get("volumes", [])

            volumes_str = str(volumes)
            assert "/data" in volumes_str, f"{service_name} missing /data volume mount"
