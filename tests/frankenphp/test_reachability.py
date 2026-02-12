"""
Test that FrankenPHP containers serve the Laravel /up health endpoint.
"""


class TestReachability:
    """GET /up should return 200 for every target."""

    def test_health_endpoint_returns_200(self, container):
        response = container.get("/up")
        assert response.status_code == 200, (
            f"[{container.combo_id}] Expected 200 from /up, got {response.status_code}"
        )

    def test_root_returns_200(self, container):
        response = container.get("/")
        assert response.status_code == 200, (
            f"[{container.combo_id}] Expected 200 from /, got {response.status_code}"
        )
