import logging
import random
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.orm import Session

from backend.database import engine, SessionLocal, Base
from backend.models import Customer, Product, Order, OrderItem

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Fixed seed for reproducibility
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

CATEGORIES = {
    "Electronics": [
        ("Noise-Cancelling Headphones", 80.0, 199.99),
        ("Mechanical Keyboard", 45.0, 119.99),
        ("Ultra-Wide 4K Monitor", 220.0, 449.99),
        ("Wireless Ergonomic Mouse", 25.0, 69.99),
        ("Smart Fitness Watch", 60.0, 149.99),
    ],
    "Apparel": [
        ("Merino Wool Crewneck", 30.0, 89.99),
        ("Waterproof Rain Shell", 50.0, 139.99),
        ("Slim Fit Stretch Chinos", 22.0, 64.99),
        ("Breathable Running Shoes", 40.0, 119.99),
        ("Cotton Everyday Tee 3-Pack", 15.0, 44.99),
    ],
    "Home & Kitchen": [
        ("Stainless Steel Chef's Knife", 35.0, 89.99),
        ("Cast Iron Dutch Oven", 45.0, 129.99),
        ("Pour-Over Coffee Dripper Set", 18.0, 49.99),
        ("Cordless Stick Vacuum", 90.0, 229.99),
        ("Air Purifier HEPA H13", 65.0, 159.99),
    ],
    "Books & Media": [
        ("System Architecture Manual", 15.0, 49.99),
        ("Data Intensive Applications", 18.0, 59.99),
        ("Pragmatic Programmer Guide", 14.0, 44.99),
        ("Business Strategy Foundations", 12.0, 39.99),
        ("Clean Code Principles", 16.0, 48.99),
    ],
    "Beauty & Personal Care": [
        ("Hydrating Hyaluronic Serum", 12.0, 38.0),
        ("Mineral Broad-Spectrum Sunscreen", 10.0, 28.0),
        ("Sonic Toothbrush Pro", 28.0, 79.99),
        ("Botanical Cleansing Gel", 8.0, 24.0),
        ("Restorative Night Cream", 16.0, 48.0),
    ],
}

SEGMENTS = ["Enterprise", "SMB", "Consumer"]
CUSTOMER_NAMES = [
    ("Alice Chen", "alice.chen@example.com", "Enterprise"),
    ("Marcus Brody", "marcus.brody@corp.net", "SMB"),
    ("Elena Rostova", "elena.r@consumer.org", "Consumer"),
    ("David Kim", "david.kim@enterprise.io", "Enterprise"),
    ("Sophia Taylor", "sophia.t@techstart.co", "SMB"),
    ("James Wilson", "jwilson99@consumer.org", "Consumer"),
    ("Amara Okafor", "amara.o@globalcorp.com", "Enterprise"),
    ("Liam O'Connor", "liam.oc@consumer.net", "Consumer"),
    ("Priya Sharma", "priya.sharma@apexsol.com", "SMB"),
    ("Carlos Mendoza", "cmendoza@consumer.org", "Consumer"),
    ("Chloe Bennett", "chloe.b@innovate.co", "SMB"),
    ("Alexander Wright", "alex.w@enterprise.com", "Enterprise"),
    ("Fatima Al-Mansoor", "fatima.m@gulfcorp.com", "Enterprise"),
    ("Lucas Silva", "lucas.silva@consumer.br", "Consumer"),
    ("Zoe Jenkins", "zoe.jenkins@startup.io", "SMB"),
    ("Benjamin Hayes", "bhayes@consumer.net", "Consumer"),
    ("Aria Montgomery", "aria.m@consumer.org", "Consumer"),
    ("Vikram Patel", "vikram.p@indiacorp.in", "SMB"),
    ("Olivia Martin", "olivia.m@consumer.com", "Consumer"),
    ("Nathan Drake", "nathan.d@adventures.org", "Consumer"),
]


def generate_raw_synthetic_data():
    """Generates synthetic records spanning 6 months (2024-01 to 2024-06)

    Intentional design:
    - Month 1 (Jan 2024): Base level ~350 orders
    - Month 2 (Feb 2024): Growth ~410 orders
    - Month 3 (Mar 2024): Growth ~480 orders
    - Month 4 (Apr 2024): Growth ~550 orders
    - Month 5 (May 2024): Peak month ~620 orders
    - Month 6 (Jun 2024): Sharp decline ~390 orders, with Electronics category dropping significantly
    """
    logger.info("Generating synthetic raw records...")

    # 1. Customers
    customers = []
    # Seed known fixed customers first
    for idx, (name, email, seg) in enumerate(CUSTOMER_NAMES, start=1):
        cust_id = f"CUST-{idx:04d}"
        created_at = datetime(2023, 10, 1) + timedelta(days=random.randint(0, 90))
        customers.append({
            "customer_id": cust_id,
            "name": name,
            "email": email,
            "created_at": created_at,
            "segment": seg
        })

    # Add additional customers up to 120 total
    for idx in range(len(CUSTOMER_NAMES) + 1, 121):
        cust_id = f"CUST-{idx:04d}"
        created_at = datetime(2023, 11, 1) + timedelta(days=random.randint(0, 180))
        seg = random.choices(SEGMENTS, weights=[0.2, 0.35, 0.45])[0]
        customers.append({
            "customer_id": cust_id,
            "name": f"Customer {idx}",
            "email": f"customer.{idx}@example.com",
            "created_at": created_at,
            "segment": seg
        })

    # Introduce raw dirty entries to test ingestion pipeline:
    # 1 duplicate customer
    customers.append(customers[0].copy())
    # 1 customer with missing email
    customers.append({
        "customer_id": "CUST-DIRTY-1",
        "name": "Missing Email Person",
        "email": None,
        "created_at": datetime(2024, 1, 1),
        "segment": "Consumer"
    })

    # 2. Products
    products = []
    prod_counter = 1
    for category, items in CATEGORIES.items():
        for name, cost, retail in items:
            prod_id = f"PROD-{prod_counter:04d}"
            stock = random.randint(20, 250)
            products.append({
                "product_id": prod_id,
                "name": name,
                "category": category,
                "cost_price": cost,
                "retail_price": retail,
                "stock_level": stock
            })
            prod_counter += 1

    # 3. Orders & Order Items
    orders = []
    order_items = []
    order_counter = 1
    item_counter = 1

    # Target parameters per month (Year 2024)
    monthly_targets = [
        {"year": 2024, "month": 1, "order_count": 340, "electronics_weight": 0.25},
        {"year": 2024, "month": 2, "order_count": 400, "electronics_weight": 0.26},
        {"year": 2024, "month": 3, "order_count": 470, "electronics_weight": 0.28},
        {"year": 2024, "month": 4, "order_count": 540, "electronics_weight": 0.29},
        {"year": 2024, "month": 5, "order_count": 610, "electronics_weight": 0.32},  # Peak
        {"year": 2024, "month": 6, "order_count": 380, "electronics_weight": 0.12},  # Sharp drop in total orders & electronics
    ]

    valid_customer_ids = [c["customer_id"] for c in customers if c.get("email")]
    prod_by_cat = {}
    for p in products:
        prod_by_cat.setdefault(p["category"], []).append(p)

    for target in monthly_targets:
        y = target["year"]
        m = target["month"]
        days_in_month = 28 if m == 2 else (30 if m in [4, 6, 9, 11] else 31)
        count = target["order_count"]
        elec_w = target["electronics_weight"]
        other_w = (1.0 - elec_w) / 4.0

        cat_weights = [
            elec_w if c == "Electronics" else other_w
            for c in CATEGORIES.keys()
        ]

        # Realistic customer lifecycle cohorts:
        # - Cohort Active (0..79): Ongoing repeat customers
        # - Cohort Churned (80..104): Purchased only in months 1-3, inactive in past 60 days
        # - Cohort New (105..119): Newly acquired in months 5-6
        cohort_active = valid_customer_ids[:80]
        cohort_churned = valid_customer_ids[80:105]
        cohort_new = valid_customer_ids[105:]

        if m in [1, 2, 3]:
            customer_pool = cohort_active + cohort_churned
        elif m == 4:
            customer_pool = cohort_active
        elif m == 5:
            customer_pool = cohort_active[:50] * 3 + cohort_active[50:] + cohort_new
        elif m == 6:
            # Churn and repeat slump in month 6: only limited active and few new
            customer_pool = cohort_active[:30] + cohort_new[:5]
        else:
            customer_pool = valid_customer_ids

        for _ in range(count):
            order_id = f"ORD-{order_counter:06d}"
            cust_id = random.choice(customer_pool)
            day = random.randint(1, days_in_month)
            hour = random.randint(8, 21)
            minute = random.randint(0, 59)
            order_date = datetime(y, m, day, hour, minute)

            # Status distribution: ~92% completed, ~5% cancelled, ~3% refunded
            status = random.choices(["completed", "cancelled", "refunded"], weights=[0.92, 0.05, 0.03])[0]

            # Choose 1 to 4 items
            num_items = random.choices([1, 2, 3, 4], weights=[0.5, 0.3, 0.15, 0.05])[0]
            # Pick categories based on month weights
            chosen_categories = random.choices(list(CATEGORIES.keys()), weights=cat_weights, k=num_items)

            order_total = 0.0
            for cat in chosen_categories:
                chosen_product = random.choice(prod_by_cat[cat])
                qty = random.choices([1, 2, 3], weights=[0.8, 0.15, 0.05])[0]
                unit_price = chosen_product["retail_price"]
                line_total = round(unit_price * qty, 2)
                order_total += line_total

                item_id = f"ITEM-{item_counter:07d}"
                order_items.append({
                    "order_item_id": item_id,
                    "order_id": order_id,
                    "product_id": chosen_product["product_id"],
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total
                })
                item_counter += 1

            orders.append({
                "order_id": order_id,
                "customer_id": cust_id,
                "order_date": order_date,
                "status": status,
                "total_amount": round(order_total, 2)
            })
            order_counter += 1

    return customers, products, orders, order_items


def validate_and_clean_data(customers, products, orders, order_items):
    """Validates types, removes duplicates, handles missing values, and ensures referential integrity."""
    logger.info("Executing data validation and cleansing pipeline...")

    # DataFrames for cleansing
    cust_df = pd.DataFrame(customers)
    prod_df = pd.DataFrame(products)
    orders_df = pd.DataFrame(orders)
    items_df = pd.DataFrame(order_items)

    # 1. Deduplication
    initial_cust_count = len(cust_df)
    cust_df = cust_df.drop_duplicates(subset=["customer_id"])
    cust_df = cust_df.drop_duplicates(subset=["email"])
    if len(cust_df) < initial_cust_count:
        logger.warning(f"Deduplicated {initial_cust_count - len(cust_df)} duplicate customer records.")

    # 2. Missing values handling
    # Drop customers without email or customer_id
    missing_email_mask = cust_df["email"].isna() | (cust_df["email"].str.strip() == "")
    if missing_email_mask.any():
        dropped_count = missing_email_mask.sum()
        logger.warning(f"Dropping {dropped_count} customer records with missing/empty email.")
        cust_df = cust_df[~missing_email_mask]

    # Fill default segments if missing
    cust_df["segment"] = cust_df["segment"].fillna("Consumer")

    # 3. Product validation
    prod_df = prod_df.drop_duplicates(subset=["product_id"])
    prod_df["cost_price"] = pd.to_numeric(prod_df["cost_price"], errors="coerce").fillna(10.0)
    prod_df["retail_price"] = pd.to_numeric(prod_df["retail_price"], errors="coerce").fillna(20.0)
    prod_df["stock_level"] = pd.to_numeric(prod_df["stock_level"], errors="coerce").fillna(0).astype(int)

    # 4. Orders validation
    orders_df = orders_df.drop_duplicates(subset=["order_id"])
    orders_df["total_amount"] = pd.to_numeric(orders_df["total_amount"], errors="coerce").fillna(0.0)
    orders_df["order_date"] = pd.to_datetime(orders_df["order_date"], errors="coerce")
    orders_df = orders_df.dropna(subset=["order_date"])

    # Enforce referential integrity: order must reference a valid customer
    valid_cust_ids = set(cust_df["customer_id"])
    orphan_orders = ~orders_df["customer_id"].isin(valid_cust_ids)
    if orphan_orders.any():
        logger.warning(f"Dropping {orphan_orders.sum()} orders with invalid customer_id.")
        orders_df = orders_df[~orphan_orders]

    # 5. Order items validation
    items_df = items_df.drop_duplicates(subset=["order_item_id"])
    valid_order_ids = set(orders_df["order_id"])
    valid_prod_ids = set(prod_df["product_id"])

    valid_items_mask = items_df["order_id"].isin(valid_order_ids) & items_df["product_id"].isin(valid_prod_ids)
    if (~valid_items_mask).any():
        logger.warning(f"Dropping {(~valid_items_mask).sum()} order items with invalid order_id or product_id.")
        items_df = items_df[valid_items_mask]

    items_df["quantity"] = pd.to_numeric(items_df["quantity"], errors="coerce").fillna(1).astype(int)
    items_df["unit_price"] = pd.to_numeric(items_df["unit_price"], errors="coerce").fillna(0.0)
    items_df["line_total"] = pd.to_numeric(items_df["line_total"], errors="coerce").fillna(0.0)

    logger.info(
        f"Validation summary: Customers={len(cust_df)}, Products={len(prod_df)}, "
        f"Orders={len(orders_df)}, OrderItems={len(items_df)}"
    )

    return cust_df, prod_df, orders_df, items_df


def ingest_into_database(cust_df, prod_df, orders_df, items_df, session: Session = None):
    """Ingests validated DataFrames into SQLite database using SQLAlchemy."""
    close_session_on_exit = False
    if session is None:
        Base.metadata.create_all(bind=engine)
        session = SessionLocal()
        close_session_on_exit = True

    try:
        # Clear existing data to allow clean re-seeding
        session.query(OrderItem).delete()
        session.query(Order).delete()
        session.query(Product).delete()
        session.query(Customer).delete()
        session.commit()

        logger.info("Inserting customers...")
        for _, row in cust_df.iterrows():
            session.add(Customer(
                customer_id=str(row["customer_id"]),
                name=str(row["name"]),
                email=str(row["email"]),
                created_at=row["created_at"].to_pydatetime() if hasattr(row["created_at"], "to_pydatetime") else row["created_at"],
                segment=str(row["segment"])
            ))
        session.commit()

        logger.info("Inserting products...")
        for _, row in prod_df.iterrows():
            session.add(Product(
                product_id=str(row["product_id"]),
                name=str(row["name"]),
                category=str(row["category"]),
                cost_price=float(row["cost_price"]),
                retail_price=float(row["retail_price"]),
                stock_level=int(row["stock_level"])
            ))
        session.commit()

        logger.info("Inserting orders...")
        for _, row in orders_df.iterrows():
            session.add(Order(
                order_id=str(row["order_id"]),
                customer_id=str(row["customer_id"]),
                order_date=row["order_date"].to_pydatetime() if hasattr(row["order_date"], "to_pydatetime") else row["order_date"],
                status=str(row["status"]),
                total_amount=float(row["total_amount"])
            ))
        session.commit()

        logger.info("Inserting order items...")
        for _, row in items_df.iterrows():
            session.add(OrderItem(
                order_item_id=str(row["order_item_id"]),
                order_id=str(row["order_id"]),
                product_id=str(row["product_id"]),
                quantity=int(row["quantity"]),
                unit_price=float(row["unit_price"]),
                line_total=float(row["line_total"])
            ))
        session.commit()

        logger.info("Database ingestion completed successfully.")

    except Exception as e:
        session.rollback()
        logger.error(f"Error during ingestion: {e}")
        raise
    finally:
        if close_session_on_exit:
            session.close()


def run_pipeline():
    """Top-level pipeline execution."""
    customers, products, orders, order_items = generate_raw_synthetic_data()
    c_df, p_df, o_df, i_df = validate_and_clean_data(customers, products, orders, order_items)
    ingest_into_database(c_df, p_df, o_df, i_df)


if __name__ == "__main__":
    run_pipeline()

