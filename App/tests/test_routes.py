import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.testing = True
    with flask_app.test_client() as c:
        yield c


def _fake_get_db():
    yield MagicMock()


class _FakeProduct:
    def __init__(self, name, list_velocity):
        self.name = name
        self.list_velocity = list_velocity

    def to_dict(self):
        return {"name": self.name, "list_velocity": self.list_velocity}


def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["status"] == "healthy"
    assert "version" in body
    datetime.fromisoformat(body["timestamp"])  # raises ValueError if malformed


def test_get_products_returns_serialized_list(client):
    products = [_FakeProduct("Widget A", 10), _FakeProduct("Widget B", 5)]
    with patch("app.get_db", _fake_get_db), \
         patch("app.get_all_products", return_value=products):
        resp = client.get("/api/products")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert len(body) == 2
    assert body[0] == {"name": "Widget A", "list_velocity": 10}
    assert body[1] == {"name": "Widget B", "list_velocity": 5}


def test_trending_sorts_by_velocity_and_caps_at_ten(client):
    # 12 products with list_velocity 0–11 in ascending order
    products = [_FakeProduct(f"p{i}", i) for i in range(12)]
    with patch("app.get_db", _fake_get_db), \
         patch("app.get_all_products", return_value=products):
        resp = client.get("/api/products/trending")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert len(body) == 10
    velocities = [item["list_velocity"] for item in body]
    assert velocities == sorted(velocities, reverse=True)
    assert velocities[0] == 11
