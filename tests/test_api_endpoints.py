import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "version" in data


def test_kpis_endpoint():
    response = client.get("/api/kpis")
    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
    assert "total_completed_orders" in data
    assert "average_order_value" in data
    assert "total_unique_customers" in data
    assert isinstance(data["total_revenue"], (int, float))


def test_monthly_analytics_endpoint():
    response = client.get("/api/analytics/monthly")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "month" in first
        assert "revenue" in first
        assert "order_count" in first


def test_category_analytics_endpoint():
    response = client.get("/api/analytics/categories")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert "category" in data[0]
        assert "total_revenue" in data[0]
        assert "contribution_pct" in data[0]


def test_top_products_endpoint_valid():
    response = client.get("/api/analytics/products/top?metric=revenue&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 3


def test_top_products_endpoint_invalid_metric():
    response = client.get("/api/analytics/products/top?metric=unsupported_metric")
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["status_code"] == 422
    assert data["error_type"] == "ValidationError"


def test_top_products_endpoint_invalid_limit():
    response = client.get("/api/analytics/products/top?limit=100")
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["error_type"] == "ValidationError"


def test_chat_endpoint_valid():
    payload = {
        "message": "What were the top 5 products by revenue?",
        "session_id": "test_session"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "tool_used" in data
    assert data["tool_used"] == "get_top_products"
    assert "data" in data


def test_chat_endpoint_empty_message_validation():
    payload = {"message": "", "session_id": "test_session"}
    response = client.post("/api/chat", json=payload)
    assert response.status_code in [400, 422]
    data = response.json()
    assert data["status"] == "error"

