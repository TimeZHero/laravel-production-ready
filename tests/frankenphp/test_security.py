"""
Test security configurations for FrankenPHP containers.

FrankenPHP uses Caddy as its HTTP server, which has different default
behavior than nginx for some security aspects.
"""


class TestInfoLeakPrevention:
    """Verify no information leaks via headers."""

    def test_no_x_powered_by_header(self, container):
        response = container.get("/up")
        assert "X-Powered-By" not in response.headers, (
            f"[{container.combo_id}] X-Powered-By header should not be present. "
            f"Got: {response.headers.get('X-Powered-By')}"
        )
