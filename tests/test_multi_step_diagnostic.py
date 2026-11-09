from datetime import datetime
import pytest
from backend.models import Customer, Product, Order, OrderItem
from backend.tools import diagnose_revenue_decline


def test_diagnose_volume_driven_decline(in_memory_db):
    """Simulates a scenario where AOV remains constant ($100),

    but order volume collapses from 100 orders in May to 40 orders in June.
    """
    session = in_memory_db

    c = Customer(customer_id="C-1", name="Test Customer", email="test@test.com", segment="SMB")
    p = Product(product_id="P-1", name="Apparel Pack", category="Apparel", cost_price=40.0, retail_price=100.0, stock_level=500)
    session.add_all([c, p])
    session.commit()

    # May: 100 orders of $100 -> Rev = $10,000, AOV = $100
    for i in range(100):
        o = Order(order_id=f"MAY-{i}", customer_id="C-1", order_date=datetime(2024, 5, 10), status="completed", total_amount=100.0)
        item = OrderItem(order_item_id=f"MAY-ITEM-{i}", order_id=f"MAY-{i}", product_id="P-1", quantity=1, unit_price=100.0, line_total=100.0)
        session.add_all([o, item])

    # June: 40 orders of $100 -> Rev = $4,000, AOV = $100
    for i in range(40):
        o = Order(order_id=f"JUN-{i}", customer_id="C-1", order_date=datetime(2024, 6, 10), status="completed", total_amount=100.0)
        item = OrderItem(order_item_id=f"JUN-ITEM-{i}", order_id=f"JUN-{i}", product_id="P-1", quantity=1, unit_price=100.0, line_total=100.0)
        session.add_all([o, item])

    session.commit()

    result = diagnose_revenue_decline(target_month="2024-06", session=session)

    assert result["status"] == "success"
    assert result["target_month"] == "2024-06"
    assert result["comparison_month"] == "2024-05"
    assert result["revenue_summary"]["revenue_delta"] == -6000.00
    assert result["revenue_summary"]["pct_change"] == -60.00

    # Primary driver must be Volume Drop
    decomp = result["decomposition"]
    assert "Volume Drop" in decomp["primary_driver"]
    assert decomp["volume_effect_usd"] == -6000.00
    assert decomp["price_effect_usd"] == 0.00
    assert decomp["orders_previous"] == 100
    assert decomp["orders_current"] == 40


def test_diagnose_price_driven_decline(in_memory_db):
    """Simulates a scenario where order volume is identical (50 orders in May, 50 orders in June),

    but AOV collapses from $200 down to $50 (e.g. discounting / lower basket size).
    """
    session = in_memory_db

    c = Customer(customer_id="C-1", name="Test Customer", email="test@test.com", segment="SMB")
    p1 = Product(product_id="P-1", name="Premium Item", category="Electronics", cost_price=100.0, retail_price=200.0, stock_level=500)
    p2 = Product(product_id="P-2", name="Budget Item", category="Accessories", cost_price=20.0, retail_price=50.0, stock_level=500)
    session.add_all([c, p1, p2])
    session.commit()

    # May: 50 orders at $200 -> Rev = $10,000
    for i in range(50):
        o = Order(order_id=f"MAY-{i}", customer_id="C-1", order_date=datetime(2024, 5, 10), status="completed", total_amount=200.0)
        item = OrderItem(order_item_id=f"MAY-ITEM-{i}", order_id=f"MAY-{i}", product_id="P-1", quantity=1, unit_price=200.0, line_total=200.0)
        session.add_all([o, item])

    # June: 50 orders at $50 -> Rev = $2,500
    for i in range(50):
        o = Order(order_id=f"JUN-{i}", customer_id="C-1", order_date=datetime(2024, 6, 10), status="completed", total_amount=50.0)
        item = OrderItem(order_item_id=f"JUN-ITEM-{i}", order_id=f"JUN-{i}", product_id="P-2", quantity=1, unit_price=50.0, line_total=50.0)
        session.add_all([o, item])

    session.commit()

    result = diagnose_revenue_decline(target_month="2024-06", session=session)

    assert result["status"] == "success"
    decomp = result["decomposition"]
    assert "Price/Basket Size Drop" in decomp["primary_driver"]
    assert decomp["volume_effect_usd"] == 0.00
    assert decomp["price_effect_usd"] == -7500.00
    assert result["most_impacted_category"]["category"] == "Electronics"

