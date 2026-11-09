import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# Ensure root path is accessible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from backend.tools import (
        get_kpis,
        get_monthly_revenue,
        get_category_performance,
        get_top_products
    )
    from backend.agent import BIAgent
    DIRECT_BACKEND_AVAILABLE = True
except Exception:
    DIRECT_BACKEND_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("frontend.app")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# Page Configuration
st.set_page_config(
    page_title="DDL Labs - Executive BI & AI Data Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main {
        background-color: #F8FAFC;
    }
    .kpi-card {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px 0 rgba(0, 0, 0, 0.04);
        border: 1px solid #E2E8F0;
        margin-bottom: 12px;
    }
    .kpi-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0F172A;
    }
    .kpi-subtext {
        font-size: 0.8rem;
        color: #10B981;
        font-weight: 500;
        margin-top: 4px;
    }
    .stChatMessage {
        border-radius: 10px;
        padding: 12px;
    }
    .chip-button {
        display: inline-block;
        padding: 6px 12px;
        margin: 4px;
        background-color: #EEF2F6;
        border: 1px solid #CBD5E1;
        border-radius: 16px;
        font-size: 0.85rem;
        cursor: pointer;
    }
    .header-bar {
        padding: 14px 20px;
        background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%);
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
    }
</style>
""", unsafe_allow_html=True)


# --- Data Fetching Helpers ---
def fetch_kpis() -> Dict[str, Any]:
    try:
        r = httpx.get(f"{API_BASE_URL}/api/kpis", timeout=3.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    if DIRECT_BACKEND_AVAILABLE:
        return get_kpis()
    return {"total_revenue": 0.0, "total_completed_orders": 0, "average_order_value": 0.0, "total_unique_customers": 0}


def fetch_monthly_revenue() -> List[Dict[str, Any]]:
    try:
        r = httpx.get(f"{API_BASE_URL}/api/analytics/monthly", timeout=3.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    if DIRECT_BACKEND_AVAILABLE:
        return get_monthly_revenue()
    return []


def fetch_category_performance() -> List[Dict[str, Any]]:
    try:
        r = httpx.get(f"{API_BASE_URL}/api/analytics/categories", timeout=3.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    if DIRECT_BACKEND_AVAILABLE:
        return get_category_performance()
    return []


def fetch_top_products() -> List[Dict[str, Any]]:
    try:
        r = httpx.get(f"{API_BASE_URL}/api/analytics/products/top?limit=5", timeout=3.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    if DIRECT_BACKEND_AVAILABLE:
        return get_top_products(metric="revenue", limit=5)
    return []


def send_chat_message(prompt: str) -> Dict[str, Any]:
    try:
        r = httpx.post(f"{API_BASE_URL}/api/chat", json={"message": prompt, "session_id": "dashboard"}, timeout=15.0)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"Backend API call failed: {e}. Falling back to internal agent.")
    if DIRECT_BACKEND_AVAILABLE:
        if "agent_instance" not in st.session_state:
            st.session_state["agent_instance"] = BIAgent()
        res = st.session_state["agent_instance"].process_query(prompt)
        return res
    return {
        "response": "Could not connect to the BI analytics engine. Please ensure backend service is running.",
        "tool_used": "error",
        "data": {},
        "chart_spec": None
    }


# --- Sidebar ---
with st.sidebar:
    st.image("https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=300&auto=format&fit=crop&q=60", use_container_width=True)
    st.title("DDL Analytics")
    st.caption("AI-Powered Business Intelligence Platform")
    st.markdown("---")
    st.markdown("### Architecture Status")
    st.success("Database: SQLite (`bi_analytics.db`)")
    st.info("LLM Integration: Function Calling + Strict Grounding")
    st.markdown("---")
    st.markdown("### Take-Home Scope")
    st.markdown("""
    - Verified Transactional Schema
    - Deterministic Multi-Step Diagnostics
    - Zero Hallucination Guarantee
    - Plotly Dynamic Charts
    """)
    if st.button("🔄 Refresh Data Cache"):
        st.cache_data.clear()
        st.rerun()


# --- Top Header ---
st.markdown("""
<div class="header-bar">
    <h2 style="margin: 0; font-size: 1.7rem; font-weight: 700;">Executive Business Intelligence Dashboard</h2>
    <p style="margin: 4px 0 0 0; opacity: 0.85; font-size: 0.95rem;">Empirical E-Commerce Performance, Cohort Trends & AI Diagnostic Agent</p>
</div>
""", unsafe_allow_html=True)


# --- 1. Top KPI Summary Bar ---
kpis = fetch_kpis()
kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

with kpi_col1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Total Net Revenue</div>
        <div class="kpi-value">${kpis.get('total_revenue', 0.0):,.2f}</div>
        <div class="kpi-subtext">Completed Orders</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Completed Orders</div>
        <div class="kpi-value">{kpis.get('total_completed_orders', 0):,}</div>
        <div class="kpi-subtext">Net Fulfilled</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Average Order Value</div>
        <div class="kpi-value">${kpis.get('average_order_value', 0.0):,.2f}</div>
        <div class="kpi-subtext">Revenue / Completed Order</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col4:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Active Transacting Customers</div>
        <div class="kpi-value">{kpis.get('total_unique_customers', 0):,}</div>
        <div class="kpi-subtext">Unique Customer Accounts</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# --- 2. Interactive Visualizations Section ---
st.subheader("📈 Executive Performance Charts")
chart_tab1, chart_tab2, chart_tab3 = st.tabs([
    "📅 Monthly Revenue & Growth",
    "🏷️ Category Revenue Breakdown",
    "🏆 Top 5 Products by Sales"
])

with chart_tab1:
    monthly_data = fetch_monthly_revenue()
    if monthly_data:
        months = [d["month"] for d in monthly_data]
        revenues = [d["revenue"] for d in monthly_data]
        orders = [d["order_count"] for d in monthly_data]
        growths = [d.get("mom_growth_pct") or 0.0 for d in monthly_data]

        fig_month = go.Figure()
        # Bar for revenue
        fig_month.add_trace(go.Bar(
            x=months,
            y=revenues,
            name="Revenue ($)",
            marker_color="#3B82F6",
            yaxis="y1"
        ))
        # Line for order count
        fig_month.add_trace(go.Scatter(
            x=months,
            y=orders,
            name="Order Count",
            marker=dict(size=8, color="#F59E0B"),
            line=dict(color="#F59E0B", width=3),
            yaxis="y2"
        ))
        fig_month.update_layout(
            title="Monthly Revenue vs. Order Volume Trajectory",
            xaxis=dict(title="Month"),
            yaxis=dict(title="Net Revenue ($)", showgrid=True),
            yaxis2=dict(
                title="Order Count",
                overlaying="y",
                side="right",
                showgrid=False
            ),
            legend=dict(x=0.01, y=0.99),
            template="plotly_white",
            height=380,
            margin=dict(l=40, r=40, t=50, b=40)
        )
        st.plotly_chart(fig_month, use_container_width=True)
    else:
        st.info("No monthly revenue data available.")

with chart_tab2:
    cat_data = fetch_category_performance()
    if cat_data:
        cat_names = [c["category"] for c in cat_data]
        cat_revs = [c["total_revenue"] for c in cat_data]
        fig_cat = px.pie(
            values=cat_revs,
            names=cat_names,
            title="Category Revenue Share (%)",
            color_discrete_sequence=px.colors.qualitative.Prism,
            hole=0.4
        )
        fig_cat.update_layout(
            template="plotly_white",
            height=380,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("No category performance data available.")

with chart_tab3:
    prod_data = fetch_top_products()
    if prod_data:
        p_names = [p["name"] for p in prod_data]
        p_revs = [p["revenue"] for p in prod_data]
        p_cats = [p["category"] for p in prod_data]

        fig_prod = go.Figure(go.Bar(
            x=p_revs,
            y=p_names,
            orientation="h",
            marker=dict(color="#10B981"),
            text=[f"${r:,.2f} ({c})" for r, c in zip(p_revs, p_cats)],
            textposition="inside"
        ))
        fig_prod.update_layout(
            title="Top 5 Products Ranked by Sales Revenue",
            xaxis=dict(title="Revenue ($)"),
            yaxis=dict(autorange="reversed"),
            template="plotly_white",
            height=380,
            margin=dict(l=40, r=40, t=50, b=40)
        )
        st.plotly_chart(fig_prod, use_container_width=True)
    else:
        st.info("No product ranking data available.")

st.markdown("<br><hr>", unsafe_allow_html=True)


# --- 3. AI Business Intelligence Analyst Console ---
st.subheader("💬 AI Business Analyst Console")
st.caption("Ask natural language business questions. All numbers are strictly computed by deterministic tools.")

# Initialize chat session history
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": "Hello! I am your AI Business Intelligence Analyst. Ask me about your business performance, customer churn, product metrics, or request an in-depth revenue decline diagnosis.",
            "tool_used": "welcome",
            "chart_spec": None
        }
    ]

# Quick Action Prompt Chips
st.markdown("**Quick Prompts:**")
chip_cols = st.columns(5)
quick_prompts = [
    "What were the top 5 products by revenue?",
    "Show monthly revenue as a chart.",
    "Which customers have not purchased recently?",
    "Why did revenue decline last month?",
    "What is the average order value by category?"
]

selected_prompt = None
for i, prompt in enumerate(quick_prompts):
    with chip_cols[i]:
        if st.button(prompt, key=f"chip_{i}", use_container_width=True):
            selected_prompt = prompt

# Display conversation feed
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart_spec"):
            try:
                st.plotly_chart(msg["chart_spec"], use_container_width=True)
            except Exception as e:
                logger.error(f"Error rendering chart_spec: {e}")
        if msg.get("tool_used") and msg["tool_used"] not in ["welcome", "none (out_of_scope)", "error"]:
            st.caption(f"🔧 Tool Executed: `{msg['tool_used']}` (Grounded)")

# Process user input (either from chat input or chip click)
user_query = st.chat_input("Ask a business analytics question...")
active_input = selected_prompt or user_query

if active_input:
    # Append user message
    st.session_state["messages"].append({"role": "user", "content": active_input})
    with st.chat_message("user"):
        st.markdown(active_input)

    # Generate assistant response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing verified transactional data..."):
            result = send_chat_message(active_input)
            response_text = result.get("response", "No response generated.")
            chart_spec = result.get("chart_spec")
            tool_used = result.get("tool_used", "none")

            st.markdown(response_text)
            if chart_spec:
                try:
                    st.plotly_chart(chart_spec, use_container_width=True)
                except Exception as e:
                    logger.error(f"Error rendering dynamic chart: {e}")

            if tool_used and tool_used not in ["welcome", "none (out_of_scope)", "error"]:
                st.caption(f"🔧 Tool Executed: `{tool_used}` (Grounded)")

            st.session_state["messages"].append({
                "role": "assistant",
                "content": response_text,
                "tool_used": tool_used,
                "chart_spec": chart_spec
            })

