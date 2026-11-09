import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Customer, Product, Order, OrderItem


def _get_session(session: Optional[Session] = None) -> tuple[Session, bool]:
    """Helper to obtain a session and a flag indicating whether to close it."""
    if session is not None:
        return session, False
    return SessionLocal(), True


def get_kpis(start_date: Optional[str] = None, end_date: Optional[str] = None, session: Optional[Session] = None) -> Dict[str, Any]:
    """Calculate core e-commerce KPIs for completed orders.

    Args:
        start_date: Optional ISO/YYYY-MM-DD start date filter.
        end_date: Optional ISO/YYYY-MM-DD end date filter.
        session: Optional SQLAlchemy session.

    Returns:
        Dictionary with total_revenue, total_completed_orders, average_order_value, and total_unique_customers.
    """
    db, should_close = _get_session(session)
    try:
        query = db.query(Order).filter(Order.status == "completed")

        if start_date:
            try:
                s_dt = datetime.fromisoformat(start_date)
                query = query.filter(Order.order_date >= s_dt)
            except ValueError:
                pass
        if end_date:
            try:
                e_dt = datetime.fromisoformat(end_date)
                # include end of the day if date only
                if len(end_date) <= 10:
                    e_dt = e_dt + timedelta(days=1, microseconds=-1)
                query = query.filter(Order.order_date <= e_dt)
            except ValueError:
                pass

        total_completed_orders = query.count()
        total_rev_result = query.with_entities(func.sum(Order.total_amount)).scalar()
        total_revenue = round(float(total_rev_result or 0.0), 2)

        unique_customers = query.with_entities(func.count(distinct(Order.customer_id))).scalar() or 0
        aov = round(total_revenue / total_completed_orders, 2) if total_completed_orders > 0 else 0.0

        return {
            "total_revenue": total_revenue,
            "total_completed_orders": total_completed_orders,
            "average_order_value": aov,
            "total_unique_customers": unique_customers,
            "filter_applied": {
                "start_date": start_date,
                "end_date": end_date
            }
        }
    finally:
        if should_close:
            db.close()


def get_monthly_revenue(session: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Aggregates completed orders by month (YYYY-MM) with revenue, order count, and MoM % growth.

    Returns:
        List of dicts with month, revenue, order_count, and mom_growth_pct.
    """
    db, should_close = _get_session(session)
    try:
        # SQLite strftime for month grouping
        month_col = func.strftime("%Y-%m", Order.order_date)
        rows = (
            db.query(
                month_col.label("month"),
                func.sum(Order.total_amount).label("revenue"),
                func.count(Order.order_id).label("order_count"),
                func.avg(Order.total_amount).label("aov")
            )
            .filter(Order.status == "completed")
            .group_by("month")
            .order_by("month")
            .all()
        )

        results = []
        prev_rev = None
        for r in rows:
            rev = round(float(r.revenue or 0.0), 2)
            mom_growth = None
            if prev_rev is not None and prev_rev > 0:
                mom_growth = round(((rev - prev_rev) / prev_rev) * 100.0, 2)
            results.append({
                "month": r.month,
                "revenue": rev,
                "order_count": int(r.order_count),
                "aov": round(float(r.aov or 0.0), 2),
                "mom_growth_pct": mom_growth
            })
            prev_rev = rev

        return results
    finally:
        if should_close:
            db.close()


def get_top_products(metric: str = "revenue", limit: int = 5, session: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Returns top products ranked by revenue or quantity sold.

    Args:
        metric: 'revenue' or 'quantity'.
        limit: Number of top products to return (default: 5).
        session: Optional SQLAlchemy session.
    """
    db, should_close = _get_session(session)
    try:
        query = (
            db.query(
                Product.product_id,
                Product.name,
                Product.category,
                func.sum(OrderItem.line_total).label("revenue"),
                func.sum(OrderItem.quantity).label("quantity_sold")
            )
            .join(OrderItem, Product.product_id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.order_id)
            .filter(Order.status == "completed")
            .group_by(Product.product_id, Product.name, Product.category)
        )

        if metric == "quantity":
            query = query.order_by(func.sum(OrderItem.quantity).desc())
        else:
            query = query.order_by(func.sum(OrderItem.line_total).desc())

        rows = query.limit(limit).all()

        results = []
        for r in rows:
            rev = round(float(r.revenue or 0.0), 2)
            qty = int(r.quantity_sold or 0)
            results.append({
                "product_id": r.product_id,
                "name": r.name,
                "category": r.category,
                "total_sales": rev if metric == "revenue" else qty,
                "revenue": rev,
                "quantity_sold": qty
            })
        return results
    finally:
        if should_close:
            db.close()


def get_category_performance(session: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Breakdown of orders, total revenue, and contribution percentage per category."""
    db, should_close = _get_session(session)
    try:
        # Total revenue across all completed orders for contribution calc
        total_rev = (
            db.query(func.sum(OrderItem.line_total))
            .join(Order, OrderItem.order_id == Order.order_id)
            .filter(Order.status == "completed")
            .scalar()
        ) or 0.0

        rows = (
            db.query(
                Product.category,
                func.count(distinct(OrderItem.order_id)).label("order_count"),
                func.sum(OrderItem.line_total).label("revenue"),
                func.sum(OrderItem.quantity).label("units_sold")
            )
            .join(OrderItem, Product.product_id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.order_id)
            .filter(Order.status == "completed")
            .group_by(Product.category)
            .order_by(func.sum(OrderItem.line_total).desc())
            .all()
        )

        results = []
        for r in rows:
            cat_rev = round(float(r.revenue or 0.0), 2)
            contribution = round((cat_rev / total_rev * 100.0), 2) if total_rev > 0 else 0.0
            results.append({
                "category": r.category,
                "order_count": int(r.order_count),
                "total_revenue": cat_rev,
                "units_sold": int(r.units_sold or 0),
                "contribution_pct": contribution
            })
        return results
    finally:
        if should_close:
            db.close()


def get_customer_metrics(session: Optional[Session] = None) -> Dict[str, Any]:
    """Returns customer lifecycle metrics and top 5 LTV customers:

    - total_customers
    - new_customers (first purchase in past 30 days relative to latest order date)
    - repeat_customers (>1 completed order)
    - inactive_churned_customers (no orders in past 60 days relative to latest order date)
    - top_5_ltv_customers (by lifetime spend on completed orders)
    """
    db, should_close = _get_session(session)
    try:
        total_customers = db.query(Customer).count()

        # Find latest completed order date as anchor
        max_order_date = db.query(func.max(Order.order_date)).filter(Order.status == "completed").scalar()
        if not max_order_date:
            anchor_date = datetime.utcnow()
        else:
            anchor_date = max_order_date

        thirty_days_ago = anchor_date - timedelta(days=30)
        sixty_days_ago = anchor_date - timedelta(days=60)

        # First completed order date per customer
        first_orders = (
            db.query(
                Order.customer_id,
                func.min(Order.order_date).label("first_order_date"),
                func.max(Order.order_date).label("last_order_date"),
                func.count(Order.order_id).label("completed_orders"),
                func.sum(Order.total_amount).label("total_spend")
            )
            .filter(Order.status == "completed")
            .group_by(Order.customer_id)
            .subquery()
        )

        # 1. New customers (first purchase >= thirty_days_ago)
        new_customers_count = (
            db.query(func.count(first_orders.c.customer_id))
            .filter(first_orders.c.first_order_date >= thirty_days_ago)
            .scalar() or 0
        )

        # 2. Repeat customers (> 1 completed order)
        repeat_customers_count = (
            db.query(func.count(first_orders.c.customer_id))
            .filter(first_orders.c.completed_orders > 1)
            .scalar() or 0
        )

        # 3. Inactive/churned customers (last order < sixty_days_ago)
        # Note: customers who placed an order before, but last order is older than 60 days
        inactive_customers_count = (
            db.query(func.count(first_orders.c.customer_id))
            .filter(first_orders.c.last_order_date < sixty_days_ago)
            .scalar() or 0
        )

        # 4. Top 5 LTV customers
        top_ltv_rows = (
            db.query(
                Customer.customer_id,
                Customer.name,
                Customer.email,
                Customer.segment,
                func.sum(Order.total_amount).label("total_spend"),
                func.count(Order.order_id).label("order_count")
            )
            .join(Order, Customer.customer_id == Order.customer_id)
            .filter(Order.status == "completed")
            .group_by(Customer.customer_id, Customer.name, Customer.email, Customer.segment)
            .order_by(func.sum(Order.total_amount).desc())
            .limit(5)
            .all()
        )

        top_5_ltv = [
            {
                "customer_id": r.customer_id,
                "name": r.name,
                "email": r.email,
                "segment": r.segment,
                "total_spend": round(float(r.total_spend or 0.0), 2),
                "order_count": int(r.order_count)
            }
            for r in top_ltv_rows
        ]

        return {
            "anchor_reference_date": anchor_date.strftime("%Y-%m-%d"),
            "total_customers": total_customers,
            "new_customers": new_customers_count,
            "repeat_customers": repeat_customers_count,
            "inactive_churned_customers": inactive_customers_count,
            "top_5_ltv_customers": top_5_ltv
        }
    finally:
        if should_close:
            db.close()


def diagnose_revenue_decline(target_month: Optional[str] = None, session: Optional[Session] = None) -> Dict[str, Any]:
    """Multi-step diagnostic tool that isolates the root cause of month-over-month revenue decline.

    Steps:
      1. Identifies the target month and preceding reference month.
      2. Net revenue variance (absolute & %).
      3. Price vs. Volume effect (order count change vs. AOV change).
      4. Category-level drop-offs (breakdown of which categories drove the decline).
      5. Customer churn & retention impact (drop in repeat buyers vs. new buyers).

    Returns:
        Structured diagnostic dictionary with empirical evidence and business conclusions.
    """
    db, should_close = _get_session(session)
    try:
        monthly_data = get_monthly_revenue(session=db)
        if len(monthly_data) < 2:
            return {
                "error": "Insufficient historical data (need at least 2 completed months to diagnose decline).",
                "monthly_data": monthly_data
            }

        # Find target month
        idx_target = -1
        if target_month:
            for idx, item in enumerate(monthly_data):
                if item["month"] == target_month:
                    idx_target = idx
                    break
            if idx_target == -1:
                return {"error": f"Target month '{target_month}' not found in records."}
            if idx_target == 0:
                return {"error": f"Target month '{target_month}' is the earliest month with no preceding comparison period."}
        else:
            # Automatically find latest month with MoM decline
            for i in range(len(monthly_data) - 1, 0, -1):
                growth = monthly_data[i].get("mom_growth_pct")
                if growth is not None and growth < 0:
                    idx_target = i
                    break
            if idx_target == -1:
                # If no negative month, default to the last month
                idx_target = len(monthly_data) - 1

        curr_month_obj = monthly_data[idx_target]
        prev_month_obj = monthly_data[idx_target - 1]

        curr_month = curr_month_obj["month"]
        prev_month = prev_month_obj["month"]

        # 1. Net revenue variance
        rev_curr = curr_month_obj["revenue"]
        rev_prev = prev_month_obj["revenue"]
        rev_delta = round(rev_curr - rev_prev, 2)
        rev_pct_change = round(((rev_curr - rev_prev) / rev_prev * 100.0), 2) if rev_prev > 0 else 0.0

        # 2. Price vs Volume Effect (Decomposition)
        # Revenue = Orders * AOV
        # delta_Rev approx = (Orders_curr - Orders_prev) * AOV_prev  [Volume Effect]
        #                   + (AOV_curr - AOV_prev) * Orders_curr     [Price/AOV Effect]
        orders_curr = curr_month_obj["order_count"]
        orders_prev = prev_month_obj["order_count"]
        aov_curr = curr_month_obj["aov"]
        aov_prev = prev_month_obj["aov"]

        volume_effect = round((orders_curr - orders_prev) * aov_prev, 2)
        price_effect = round((aov_curr - aov_prev) * orders_curr, 2)
        orders_pct_change = round(((orders_curr - orders_prev) / orders_prev * 100.0), 2) if orders_prev > 0 else 0.0
        aov_pct_change = round(((aov_curr - aov_prev) / aov_prev * 100.0), 2) if aov_prev > 0 else 0.0

        primary_driver = "Volume Drop (Fewer Orders Placed)" if abs(volume_effect) > abs(price_effect) else "Price/Basket Size Drop (Lower AOV)"

        # 3. Category Level Breakdown
        # Query category revenue in curr_month vs prev_month
        month_col = func.strftime("%Y-%m", Order.order_date)

        cat_curr_rows = (
            db.query(
                Product.category,
                func.sum(OrderItem.line_total).label("revenue")
            )
            .join(OrderItem, Product.product_id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.order_id)
            .filter(Order.status == "completed", month_col == curr_month)
            .group_by(Product.category)
            .all()
        )
        cat_curr = {r.category: float(r.revenue or 0.0) for r in cat_curr_rows}

        cat_prev_rows = (
            db.query(
                Product.category,
                func.sum(OrderItem.line_total).label("revenue")
            )
            .join(OrderItem, Product.product_id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.order_id)
            .filter(Order.status == "completed", month_col == prev_month)
            .group_by(Product.category)
            .all()
        )
        cat_prev = {r.category: float(r.revenue or 0.0) for r in cat_prev_rows}

        all_cats = set(cat_curr.keys()).union(set(cat_prev.keys()))
        category_variances = []
        for cat in all_cats:
            c_rev = round(cat_curr.get(cat, 0.0), 2)
            p_rev = round(cat_prev.get(cat, 0.0), 2)
            delta = round(c_rev - p_rev, 2)
            pct = round((delta / p_rev * 100.0), 2) if p_rev > 0 else 0.0
            category_variances.append({
                "category": cat,
                "previous_revenue": p_rev,
                "current_revenue": c_rev,
                "revenue_delta": delta,
                "pct_change": pct
            })

        category_variances.sort(key=lambda x: x["revenue_delta"])
        most_impacted_category = category_variances[0] if category_variances else None

        # 4. Customer Churn & Retention Impact
        # Check orders from customers who purchased in prev_month vs new in curr_month
        prev_customers = set(
            r[0] for r in db.query(Order.customer_id)
            .filter(Order.status == "completed", month_col == prev_month)
            .distinct().all()
        )
        curr_customers = set(
            r[0] for r in db.query(Order.customer_id)
            .filter(Order.status == "completed", month_col == curr_month)
            .distinct().all()
        )

        retained_customers = curr_customers.intersection(prev_customers)
        churned_from_prev = prev_customers.difference(curr_customers)
        new_in_curr = curr_customers.difference(prev_customers)

        retention_rate = round((len(retained_customers) / len(prev_customers) * 100.0), 2) if prev_customers else 0.0

        # Synthesis
        findings = [
            f"Net Revenue changed by ${rev_delta:,.2f} ({rev_pct_change:+.1f}%) from {prev_month} to {curr_month}.",
            f"Primary Driver: {primary_driver}. Order volume changed by {orders_pct_change:+.1f}% ({orders_prev} -> {orders_curr} orders), while AOV changed by {aov_pct_change:+.1f}% (${aov_prev:.2f} -> ${aov_curr:.2f}).",
            f"Category Breakdown: Category '{most_impacted_category['category']}' suffered the largest contraction with a drop of ${abs(most_impacted_category['revenue_delta']):,.2f} ({most_impacted_category['pct_change']:+.1f}%)." if most_impacted_category else "No single category accounted for majority decline.",
            f"Customer Dynamics: {len(churned_from_prev)} customers from {prev_month} did not purchase in {curr_month} (Retention rate: {retention_rate}%). {len(new_in_curr)} new customers were acquired in {curr_month}."
        ]

        return {
            "status": "success",
            "target_month": curr_month,
            "comparison_month": prev_month,
            "revenue_summary": {
                "previous_revenue": rev_prev,
                "current_revenue": rev_curr,
                "revenue_delta": rev_delta,
                "pct_change": rev_pct_change
            },
            "decomposition": {
                "primary_driver": primary_driver,
                "volume_effect_usd": volume_effect,
                "price_effect_usd": price_effect,
                "orders_previous": orders_prev,
                "orders_current": orders_curr,
                "orders_pct_change": orders_pct_change,
                "aov_previous": aov_prev,
                "aov_current": aov_curr,
                "aov_pct_change": aov_pct_change
            },
            "category_drop_offs": category_variances,
            "most_impacted_category": most_impacted_category,
            "customer_retention": {
                "active_customers_prev": len(prev_customers),
                "active_customers_curr": len(curr_customers),
                "retained_customers": len(retained_customers),
                "churned_customers": len(churned_from_prev),
                "new_acquired_customers": len(new_in_curr),
                "retention_rate_pct": retention_rate
            },
            "executive_findings": findings
        }
    finally:
        if should_close:
            db.close()


def generate_chart_spec(chart_type: str, metric: str, group_by: str, session: Optional[Session] = None) -> Dict[str, Any]:
    """Generates a Plotly-compatible JSON spec for interactive client-side rendering.

    Args:
        chart_type: 'bar', 'line', 'pie', 'scatter'
        metric: 'revenue', 'order_count', 'aov', 'units_sold'
        group_by: 'month', 'category', 'product'
    """
    db, should_close = _get_session(session)
    try:
        data_records = []
        x_col = ""
        y_col = ""
        title = ""

        if group_by == "month":
            records = get_monthly_revenue(session=db)
            x_col = "month"
            y_col = metric if metric in ["revenue", "order_count", "aov"] else "revenue"
            title = f"Monthly {y_col.replace('_', ' ').title()}"
            data_records = records
        elif group_by == "category":
            records = get_category_performance(session=db)
            x_col = "category"
            y_col = "total_revenue" if metric == "revenue" else ("order_count" if metric == "order_count" else "contribution_pct")
            title = f"Category {y_col.replace('_', ' ').title()}"
            data_records = records
        elif group_by == "product":
            records = get_top_products(metric="revenue", limit=8, session=db)
            x_col = "name"
            y_col = "revenue" if metric == "revenue" else "quantity_sold"
            title = f"Top Products by {y_col.replace('_', ' ').title()}"
            data_records = records
        else:
            # Fallback to monthly revenue
            data_records = get_monthly_revenue(session=db)
            x_col = "month"
            y_col = "revenue"
            title = "Monthly Revenue"

        # Construct Plotly JSON spec
        x_vals = [d.get(x_col) for d in data_records]
        y_vals = [d.get(y_col) for d in data_records]

        trace: Dict[str, Any] = {}
        if chart_type in ["pie", "donut"]:
            trace = {
                "type": "pie",
                "labels": x_vals,
                "values": y_vals,
                "hole": 0.4 if chart_type == "donut" else 0.0,
                "textinfo": "label+percent",
                "marker": {
                    "colors": ["#2563EB", "#38BDF8", "#F59E0B", "#10B981", "#8B5CF6", "#EC4899", "#64748B"]
                }
            }
        elif chart_type == "line":
            trace = {
                "type": "scatter",
                "mode": "lines+markers",
                "x": x_vals,
                "y": y_vals,
                "line": {"color": "#2563EB", "width": 3},
                "marker": {"size": 8, "color": "#1D4ED8"}
            }
        else:  # bar
            trace = {
                "type": "bar",
                "x": x_vals,
                "y": y_vals,
                "marker": {
                    "color": "#3B82F6",
                    "line": {"color": "#1D4ED8", "width": 1.5}
                }
            }

        layout = {
            "title": {"text": title, "font": {"size": 16, "family": "Inter, sans-serif"}},
            "xaxis": {"title": x_col.title(), "showgrid": True, "gridcolor": "#E2E8F0"},
            "yaxis": {"title": y_col.replace('_', ' ').title(), "showgrid": True, "gridcolor": "#E2E8F0"},
            "template": "plotly_white",
            "margin": {"l": 50, "r": 30, "t": 50, "b": 50},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)"
        }

        return {
            "chart_type": chart_type,
            "metric": y_col,
            "group_by": x_col,
            "spec": {
                "data": [trace],
                "layout": layout
            },
            "raw_data": data_records
        }
    finally:
        if should_close:
            db.close()


# Registry of tools for LLM agent
AVAILABLE_TOOLS = {
    "get_kpis": get_kpis,
    "get_monthly_revenue": get_monthly_revenue,
    "get_top_products": get_top_products,
    "get_category_performance": get_category_performance,
    "get_customer_metrics": get_customer_metrics,
    "diagnose_revenue_decline": diagnose_revenue_decline,
    "generate_chart_spec": generate_chart_spec,
}

TOOL_DEFINITIONS = [
    {
        "name": "get_kpis",
        "description": "Fetch high-level e-commerce business KPIs: Total Revenue, Total Completed Orders, Average Order Value (AOV), and Total Unique Customers. Supports optional date filtering.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Optional start date in YYYY-MM-DD format."},
                "end_date": {"type": "string", "description": "Optional end date in YYYY-MM-DD format."}
            },
            "required": []
        }
    },
    {
        "name": "get_monthly_revenue",
        "description": "Fetch aggregated completed orders by month (YYYY-MM) with revenue, order count, and month-over-month (MoM) % growth.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_top_products",
        "description": "Fetch top performing products ranked by revenue or quantity sold.",
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "quantity"],
                    "description": "Metric to rank products by ('revenue' or 'quantity'). Default is 'revenue'."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of top products to return. Default is 5."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_category_performance",
        "description": "Fetch performance metrics broken down by product category: total revenue, order count, units sold, and revenue contribution percentage.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_customer_metrics",
        "description": "Fetch customer analytics including total customers, new customers in the past 30 days, repeat customers (>1 order), inactive/churned customers (no orders in 60 days), and top 5 LTV customers.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "diagnose_revenue_decline",
        "description": "Conduct a multi-step root cause diagnostic of revenue decline between months. Decomposes revenue delta into Price vs Volume effects, category drop-offs, and customer retention dynamics.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_month": {
                    "type": "string",
                    "description": "Optional month to diagnose in YYYY-MM format. If omitted, the most recent month with a revenue decline is automatically diagnosed."
                }
            },
            "required": []
        }
    },
    {
        "name": "generate_chart_spec",
        "description": "Generate a Plotly chart specification for dynamic visualization of business metrics.",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "donut"],
                    "description": "Visual chart type."
                },
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "order_count", "aov", "quantity"],
                    "description": "Metric to plot."
                },
                "group_by": {
                    "type": "string",
                    "enum": ["month", "category", "product"],
                    "description": "Dimension to group by."
                }
            },
            "required": ["chart_type", "metric", "group_by"]
        }
    }
]

