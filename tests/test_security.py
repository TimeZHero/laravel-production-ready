"""
Test security configurations across all ENGINE x TARGET combinations.
"""

import pytest


class TestSecurityHeaders:
    """Verify security headers are present in responses."""

    def test_x_frame_options_header(self, container):
        response = container.get("/up")
        header = response.headers.get("X-Frame-Options", "")
        assert header == "SAMEORIGIN", (
            f"[{container.combo_id}] Expected X-Frame-Options: SAMEORIGIN, got: '{header}'"
        )

    def test_x_content_type_options_header(self, container):
        response = container.get("/up")
        header = response.headers.get("X-Content-Type-Options", "")
        assert header == "nosniff", (
            f"[{container.combo_id}] Expected X-Content-Type-Options: nosniff, got: '{header}'"
        )


class TestInfoLeakPrevention:
    """Verify no information leaks via headers."""

    def test_no_x_powered_by_header(self, container):
        response = container.get("/up")
        assert "X-Powered-By" not in response.headers, (
            f"[{container.combo_id}] X-Powered-By header should not be present. "
            f"Got: {response.headers.get('X-Powered-By')}"
        )

    def test_server_header_hides_version(self, container):
        response = container.get("/up")
        server = response.headers.get("Server", "")
        # nginx should not expose version (server_tokens off)
        assert "/" not in server, (
            f"[{container.combo_id}] Server header should not contain version. Got: '{server}'"
        )


class TestDotfileDeny:
    """Verify dotfiles are denied access (403)."""

    def test_dotenv_returns_403(self, container):
        response = container.get("/.env", allow_redirects=False)
        assert response.status_code == 403, (
            f"[{container.combo_id}] GET /.env should return 403, got {response.status_code}"
        )

    def test_dotgit_returns_403(self, container):
        response = container.get("/.git/config", allow_redirects=False)
        assert response.status_code == 403, (
            f"[{container.combo_id}] GET /.git/config should return 403, got {response.status_code}"
        )


class TestDirectPHPAccess:
    """FPM-specific: deny direct access to arbitrary .php files."""

    def test_direct_php_file_returns_404(self, container):
        if not container.is_fpm:
            pytest.skip("Direct .php deny only applies to FPM engine")

        response = container.get("/some-random-file.php", allow_redirects=False)
        assert response.status_code == 404, (
            f"[{container.combo_id}] GET /some-random-file.php should return 404, "
            f"got {response.status_code}"
        )
