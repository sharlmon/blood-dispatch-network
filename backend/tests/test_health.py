import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app


def test_health(tmp_path):
    app = create_app(os.path.join(os.path.dirname(__file__), "..", "config", "settings.default.yaml"), test_config={"DB_PATH": str(tmp_path / "health.sqlite")})
    r = app.test_client().get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"
