from datetime import datetime
import pandas as pd
from data.seed_data import validate_and_clean_data


def test_data_processing_null_and_duplicates():
    # Setup dirty data fixtures
    raw_customers = [
        {"customer_id": "C-1", "name": "User One", "email": "user1@example.com", "created_at": "2024-01-01", "segment": "Consumer"},
        {"customer_id": "C-1", "name": "Duplicate User", "email": "user1_dup@example.com", "created_at": "2024-01-01", "segment": "Consumer"},
        {"customer_id": "C-2", "name": "Duplicate Email User", "email": "user1@example.com", "created_at": "2024-01-02", "segment": "SMB"},
        {"customer_id": "C-3", "name": "No Email User", "email": None, "created_at": "2024-01-03", "segment": "Enterprise"},
        {"customer_id": "C-4", "name": "Whitespace Email User", "email": "   ", "created_at": "2024-01-04", "segment": "Enterprise"},
        {"customer_id": "C-5", "name": "Valid User", "email": "user5@example.com", "created_at": "2024-01-05", "segment": None},
    ]

    raw_products = [
        {"product_id": "P-1", "name": "Gadget A", "category": "Tech", "cost_price": "45.50", "retail_price": "99.99", "stock_level": "100"},
        {"product_id": "P-1", "name": "Duplicate Gadget", "category": "Tech", "cost_price": 50.0, "retail_price": 100.0, "stock_level": 50},
        {"product_id": "P-2", "name": "Invalid Prices", "category": "Tech", "cost_price": "invalid", "retail_price": None, "stock_level": "bad"},
    ]

    raw_orders = [
        {"order_id": "O-1", "customer_id": "C-1", "order_date": "2024-01-15 10:00:00", "status": "completed", "total_amount": "199.98"},
        {"order_id": "O-1", "customer_id": "C-1", "order_date": "2024-01-15 10:00:00", "status": "completed", "total_amount": 199.98},
        {"order_id": "O-2", "customer_id": "C-999_ORPHAN", "order_date": "2024-01-16", "status": "completed", "total_amount": 50.0},
        {"order_id": "O-3", "customer_id": "C-5", "order_date": "invalid_date", "status": "completed", "total_amount": 50.0},
    ]

    raw_items = [
        {"order_item_id": "I-1", "order_id": "O-1", "product_id": "P-1", "quantity": "2", "unit_price": "99.99", "line_total": "199.98"},
        {"order_item_id": "I-2", "order_id": "O-999_ORPHAN", "product_id": "P-1", "quantity": 1, "unit_price": 99.99, "line_total": 99.99},
        {"order_item_id": "I-3", "order_id": "O-1", "product_id": "P-999_ORPHAN", "quantity": 1, "unit_price": 99.99, "line_total": 99.99},
    ]

    c_df, p_df, o_df, i_df = validate_and_clean_data(raw_customers, raw_products, raw_orders, raw_items)

    # Assertions
    # C-1 kept, duplicates and missing emails dropped
    assert len(c_df) == 2
    assert set(c_df["customer_id"]) == {"C-1", "C-5"}
    assert c_df.loc[c_df["customer_id"] == "C-5", "segment"].iloc[0] == "Consumer"

    # Products: P-1 kept, P-2 numeric coercion
    assert len(p_df) == 2
    p2_row = p_df[p_df["product_id"] == "P-2"].iloc[0]
    assert p2_row["cost_price"] == 10.0  # default fallback
    assert p2_row["retail_price"] == 20.0  # default fallback
    assert p2_row["stock_level"] == 0

    # Orders: O-1 kept, duplicate O-1 dropped, O-2 (orphan customer) dropped, O-3 (invalid date) dropped
    assert len(o_df) == 1
    assert o_df.iloc[0]["order_id"] == "O-1"
    assert o_df.iloc[0]["total_amount"] == 199.98

    # Order items: I-1 kept, I-2 (orphan order) dropped, I-3 (orphan product) dropped
    assert len(i_df) == 1
    assert i_df.iloc[0]["order_item_id"] == "I-1"
    assert i_df.iloc[0]["quantity"] == 2
    assert i_df.iloc[0]["line_total"] == 199.98

