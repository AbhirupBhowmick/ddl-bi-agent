from datetime import datetime, timedelta
import pytest
from backend.models import Customer, Product, Order, OrderItem
from backend.tools import (
    get_kpis,
    get_monthly_revenue,
    get_category_performance,
    get_customer_metrics,
    get_top_products
)


@pytest.fixture
def populated_session(in_memory_db):
    """Seeds a controlled set of records with known numbers for exact verification."""
    session = in_memory_db

    # Customers
    c1 = Customer(customer_id="C-1", name="Alpha User", email="alpha@test.com", segment="Enterprise")
    c2 = Customer(customer_id="C-2", name="Beta User", email="beta@test.com", segment="SMB")
    c3 = Customer(customer_id="C-3", name="Gamma User", email="gamma@test.com", segment="Consumer")
    session.add_all([c1, c2, c3])
    session.commit()

    # Products
    p1 = Product(product_id="P-1", name="Laptop Pro", category="Electronics", cost_price=500.0, retail_price=1000.0, stock_level=10)
    p2 = Product(product_id="P-2", name="Coffee Beans", category="Grocery", cost_price=5.0, retail_price=15.0, stock_level=100)
    session.add_all([p1, p2])
    session.commit()

    now = datetime(2024, 6, 15, 12, 0, 0)
    prev_month = datetime(2024, 5, 15, 12, 0, 0)
    old_date = datetime(2024, 2, 1, 12, 0, 0)

    # Orders:
    # O1: C1 completed in May ($1000)
    # O2: C1 completed in June ($1000) -> C1 is repeat customer (>1 order)
    # O3: C2 completed in June ($30)
    # O4: C3 completed in Feb ($15) -> C3 inactive (>60 days inactive)
    # O5: C2 cancelled in June ($500) -> SHOULD BE EXCLUDED from revenue & KPIs!
    # O6: C2 refunded in June ($100) -> SHOULD BE EXCLUDED from revenue & KPIs!
    o1 = Order(order_id="O-1", customer_id="C-1", order_date=prev_month, status="completed", total_amount=1000.0)
    o2 = Order(order_id="O-2", customer_id="C-1", order_date=now, status="completed", total_amount=1000.0)
    o3 = Order(order_id="O-3", customer_id="C-2", order_date=now, status="completed", total_amount=30.0)
    o4 = Order(order_id="O-4", customer_id="C-3", order_date=old_date, status="completed", total_amount=15.0)
    o5 = Order(order_id="O-5", customer_id="C-2", order_date=now, status="cancelled", total_amount=500.0)
    o6 = Order(order_id="O-6", customer_id="C-2", order_date=now, status="refunded", total_amount=100.0)
    session.add_all([o1, o2, o3, o4, o5, o6])
    session.commit()

    # Order Items for completed orders
    item1 = OrderItem(order_item_id="I-1", order_id="O-1", product_id="P-1", quantity=1, unit_price=1000.0, line_total=1000.0)
    item2 = OrderItem(order_item_id="I-2", order_id="O-2", product_id="P-1", quantity=1, unit_price=1000.0, line_total=1000.0)
    item3 = OrderItem(order_item_id="I-3", order_id="O-3", product_id="P-2", quantity=2, unit_price=15.0, line_total=30.0)
    item4 = OrderItem(order_item_id="I-4", order_id="O-4", product_id="P-2", quantity=1, unit_price=15.0, line_total=15.0)
    session.add_all([item1, item2, item3, item4])
    session.commit()

    return session


def test_get_kpis_filters_non_completed_orders(populated_session):
    # Total completed revenue = 1000 + 1000 + 30 + 15 = 2045.00
    # Total completed orders = 4
    # AOV = 2045.00 / 4 = 511.25
    # Unique customers = 3
    kpis = get_kpis(session=populated_session)

    assert kpis["total_revenue"] == 2045.00
    assert kpis["total_completed_orders"] == 4
    assert kpis["average_order_value"] == 511.25
    assert kpis["total_unique_customers"] == 3


def test_get_monthly_revenue_calculation(populated_session):
    # Months:
    # 2024-02: $15.00 (1 order)
    # 2024-05: $1000.00 (1 order) -> MoM = ((1000 - 15) / 15) * 100 = 6566.67%
    # 2024-06: $1030.00 (2 orders) -> MoM = ((1030 - 1000) / 1000) * 100 = 3.00%
    monthly = get_monthly_revenue(session=populated_session)

    assert len(monthly) == 3
    assert monthly[0]["month"] == "2024-02"
    assert monthly[0]["revenue"] == 15.00
    assert monthly[0]["order_count"] == 1
    assert monthly[0]["mom_growth_pct"] is None

    assert monthly[1]["month"] == "2024-05"
    assert monthly[1]["revenue"] == 1000.00
    assert monthly[1]["mom_growth_pct"] == 6566.67

    assert monthly[2]["month"] == "2024-06"
    assert monthly[2]["revenue"] == 1030.00
    assert monthly[2]["order_count"] == 2
    assert monthly[2]["mom_growth_pct"] == 3.00


def test_get_category_performance(populated_session):
    # Total completed revenue = $2045.00
    # Electronics: P1 line totals = 1000 + 1000 = $2000.00 (Share = 2000 / 2045 = 97.80%)
    # Grocery: P2 line totals = 30 + 15 = $45.00 (Share = 45 / 2045 = 2.20%)
    categories = get_category_performance(session=populated_session)

    assert len(categories) == 2
    top_cat = categories[0]
    assert top_cat["category"] == "Electronics"
    assert top_cat["total_revenue"] == 2000.00
    assert top_cat["contribution_pct"] == 97.80

    second_cat = categories[1]
    assert second_cat["category"] == "Grocery"
    assert second_cat["total_revenue"] == 45.00
    assert second_cat["contribution_pct"] == 2.20


def test_get_customer_metrics(populated_session):
    metrics = get_customer_metrics(session=populated_session)

    # 3 total customers
    assert metrics["total_customers"] == 3
    # C-1 has 2 completed orders -> repeat_customers = 1
    assert metrics["repeat_customers"] == 1
    # C-3 last order was Feb 2024 (>60 days before anchor June 2024) -> inactive_churned = 1
    assert metrics["inactive_churned_customers"] == 1
    # Top LTV customer is C-1 with $2000.00
    top_ltv = metrics["top_5_ltv_customers"]
    assert len(top_ltv) >= 1
    assert top_ltv[0]["customer_id"] == "C-1"
    assert top_ltv[0]["total_spend"] == 2000.00

