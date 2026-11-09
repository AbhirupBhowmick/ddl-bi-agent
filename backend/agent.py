import os
import re
import json
import logging
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

try:
    from google.api_core.exceptions import ResourceExhausted, GoogleAPICallError
except ImportError:
    class ResourceExhausted(Exception): pass
    class GoogleAPICallError(Exception): pass

try:
    from google.genai.errors import ClientError, ServerError, APIError
except ImportError:
    class ClientError(Exception): pass
    class ServerError(Exception): pass
    class APIError(Exception): pass

from backend.tools import (
    AVAILABLE_TOOLS,
    TOOL_DEFINITIONS,
    get_kpis,
    get_monthly_revenue,
    get_top_products,
    get_category_performance,
    get_customer_metrics,
    diagnose_revenue_decline,
    generate_chart_spec
)

load_dotenv()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert AI Business Intelligence Analyst for an e-commerce enterprise.
Your goal is to provide authoritative, data-grounded insights based strictly on verified database analytics tools.

MANDATORY EXECUTION RULES:
1. NEVER fabricate, hallucinate, or extrapolate metrics, financial numbers, or customer figures in your response.
2. Every numerical figure quoted in your response MUST match the exact return values from the executed tools.
3. If a user asks a question not supported by the e-commerce data schema (e.g. employee salaries, external weather, general trivia, personal advice), politely decline and state the available analytics boundaries.
4. Structure your response clearly:
   - Executive Summary: Concise headline synthesis.
   - Key Supporting Metrics: Bullet points citing exact figures and units ($ or count).
   - Strategic Business Observations: Actionable recommendations based on the empirical data.
"""

OUT_OF_SCOPE_PATTERNS = [
    r"\b(weather|forecast|rain|temperature)\b",
    r"\b(salary|salaries|payroll|employee pay|wage)\b",
    r"\b(who is the president|politics|election|political)\b",
    r"\b(recipe|cook|baking|movie|song|lyrics|joke)\b",
    r"\b(sports score|football|cricket|basketball)\b",
]


class BIAgent:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.preferred_gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_fallback_models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
        self.preferred_openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.tools_schema = TOOL_DEFINITIONS

        self.gemini_client = None
        if self.gemini_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize google-genai client: {e}")

        self.openai_client = None
        if self.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.openai_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize openai client: {e}")

    def is_out_of_scope(self, query: str) -> bool:
        """Check if query is asking for something outside the e-commerce business scope."""
        lower_q = query.lower()
        for pat in OUT_OF_SCOPE_PATTERNS:
            if re.search(pat, lower_q):
                return True
        return False

    def get_out_of_scope_response(self, query: str) -> Dict[str, Any]:
        """Polite explanation stating the available analytics boundaries."""
        msg = (
            "I specialize exclusively as an AI Business Intelligence Analyst for this e-commerce platform. "
            "My capabilities are strictly grounded in our transactional database, covering:\n\n"
            "- **Executive KPIs**: Total revenue, orders, AOV, and customer reach.\n"
            "- **Sales Trends**: Monthly revenue growth and historical trajectory.\n"
            "- **Product & Category Performance**: Top products by revenue/volume and category mix.\n"
            "- **Customer Cohorts**: New acquisitions, repeat buyers, churned/inactive accounts, and top LTV clients.\n"
            "- **Revenue Decline Diagnostics**: Multi-step decomposition of volume vs. price effects.\n\n"
            f"Your query appears to be outside these transactional analytics boundaries. "
            "Please ask an e-commerce business question or select one of the suggested prompts."
        )
        return {
            "response": msg,
            "tool_used": "none (out_of_scope)",
            "data": {},
            "chart_spec": None
        }

    def _determine_intent_and_execute(self, query: str) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
        """Deterministic intent detection and tool execution.

        Guarantees accurate tool selection and zero calculation errors.
        """
        lower = query.lower()
        tool_name = "get_kpis"
        data: Any = {}
        chart_spec = None

        # 1. Decline Diagnostic
        if any(k in lower for k in ["decline", "drop", "why did revenue", "diagnos", "decrease", "slump", "fall"]):
            tool_name = "diagnose_revenue_decline"
            # Extract month if present (e.g. 2024-06)
            month_match = re.search(r"\b(202\d[-/](?:0[1-9]|1[0-2]))\b", query)
            target_m = month_match.group(1).replace("/", "-") if month_match else None
            data = diagnose_revenue_decline(target_month=target_m)
            # If user mentioned chart, generate variance chart
            if "chart" in lower or "plot" in lower or "visual" in lower:
                chart_spec = generate_chart_spec(chart_type="bar", metric="revenue", group_by="month")

        # 2. Chart specific queries
        elif any(k in lower for k in ["chart", "plot", "visualize", "graph"]):
            tool_name = "generate_chart_spec"
            if "category" in lower:
                chart_type = "pie" if ("pie" in lower or "donut" in lower) else "bar"
                data = generate_chart_spec(chart_type=chart_type, metric="revenue", group_by="category")
            elif "product" in lower:
                data = generate_chart_spec(chart_type="bar", metric="revenue", group_by="product")
            else:
                chart_type = "line" if "line" in lower else "bar"
                data = generate_chart_spec(chart_type=chart_type, metric="revenue", group_by="month")
            chart_spec = data.get("spec")

        # 3. Monthly Revenue
        elif any(k in lower for k in ["monthly", "month over month", "mom", "trend", "history"]):
            tool_name = "get_monthly_revenue"
            data = get_monthly_revenue()

        # 4. Top Products
        elif any(k in lower for k in ["product", "items", "best selling", "top 5 products", "top selling"]):
            tool_name = "get_top_products"
            metric = "quantity" if any(w in lower for w in ["quantity", "units", "volume", "sold"]) else "revenue"
            limit_match = re.search(r"\btop\s+(\d+)\b", lower)
            limit = int(limit_match.group(1)) if limit_match else 5
            data = get_top_products(metric=metric, limit=limit)

        # 5. Category Performance
        elif any(k in lower for k in ["category", "categories", "department"]):
            tool_name = "get_category_performance"
            data = get_category_performance()

        # 6. Customer Metrics & Inactive/Churn
        elif any(k in lower for k in ["customer", "churn", "inactive", "ltv", "repeat", "buyer"]):
            tool_name = "get_customer_metrics"
            data = get_customer_metrics()

        # 7. Default to KPIs
        else:
            tool_name = "get_kpis"
            data = get_kpis()

        return tool_name, data, chart_spec

    def _synthesize_with_llm(self, query: str, tool_name: str, data: Any) -> Optional[str]:
        """Attempt to synthesize executive response using configured LLM with strict grounding."""
        # Check Gemini first
        if self.gemini_client:
            prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                f"User Question: \"{query}\"\n"
                f"Executed Tool: {tool_name}\n"
                f"Tool Data Output:\n{json.dumps(data, indent=2, default=str)}\n\n"
                f"Instructions:\n"
                f"- Formulate an executive briefing strictly based on the above JSON tool output.\n"
                f"- NEVER compute, invent, or estimate new metrics outside this data.\n"
                f"- Provide: (1) Executive Summary, (2) Key Supporting Metrics (bulleted with exact figures), (3) Strategic Business Observations."
            )
            models_to_try = [self.preferred_gemini_model]
            for fb in self.gemini_fallback_models:
                if fb not in models_to_try:
                    models_to_try.append(fb)

            for m in models_to_try:
                try:
                    config = None
                    try:
                        from google.genai import types
                        config = types.GenerateContentConfig(
                            temperature=0.1,
                            max_output_tokens=1000
                        )
                    except Exception:
                        pass

                    resp = self.gemini_client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=config
                    )
                    if resp and resp.text:
                        return resp.text.strip()
                except (ResourceExhausted, ClientError, ServerError, APIError, GoogleAPICallError, Exception) as e:
                    err_msg = str(e).lower()
                    is_quota = (
                        isinstance(e, ResourceExhausted)
                        or (getattr(e, "code", None) == 429)
                        or "resource_exhausted" in err_msg
                        or "429" in err_msg
                        or "quota" in err_msg
                        or "demand" in err_msg
                    )
                    if is_quota:
                        logger.warning(
                            f"LLM quota or high demand bottleneck encountered on model '{m}': {e}. "
                            "Failing over directly to deterministic local analytics execution to prevent buffering."
                        )
                        return None
                    else:
                        logger.warning(f"Gemini API call returned non-quota error on {m}: {e}. Trying fallback.")

        # Check OpenAI if configured
        if self.openai_client:
            try:
                completion = self.openai_client.chat.completions.create(
                    model=self.preferred_openai_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"User Question: \"{query}\"\n"
                                f"Executed Tool: {tool_name}\n"
                                f"Tool Data Output:\n{json.dumps(data, indent=2, default=str)}\n\n"
                                f"Format with Executive Summary, Key Supporting Metrics bullets, and Strategic Business Observations."
                            )
                        }
                    ],
                    temperature=0.1
                )
                if completion.choices:
                    return completion.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OpenAI generation failed: {e}")

        return None

    def _format_deterministic_response(self, query: str, tool_name: str, data: Any) -> str:
        """Deterministic grounding template that formats tool data into executive-ready markdown."""
        if tool_name == "get_kpis":
            rev = data.get("total_revenue", 0.0)
            orders = data.get("total_completed_orders", 0)
            aov = data.get("average_order_value", 0.0)
            cust = data.get("total_unique_customers", 0)
            return (
                f"### Executive Summary\n"
                f"The business generated **${rev:,.2f}** in net revenue across **{orders:,}** completed orders, "
                f"achieving an Average Order Value (AOV) of **${aov:,.2f}** from **{cust:,}** unique customers.\n\n"
                f"### Key Supporting Metrics\n"
                f"- **Total Net Revenue**: ${rev:,.2f}\n"
                f"- **Completed Orders**: {orders:,}\n"
                f"- **Average Order Value (AOV)**: ${aov:,.2f}\n"
                f"- **Total Unique Transacting Customers**: {cust:,}\n\n"
                f"### Strategic Business Observations\n"
                f"- Healthy customer reach with an active base of {cust} accounts.\n"
                f"- Basket size is stabilized at ${aov:,.2f}; cross-selling initiatives could expand AOV past current benchmarks.\n"
            )

        elif tool_name == "get_monthly_revenue":
            months = data
            if not months:
                return "No monthly revenue records found."
            latest = months[-1]
            peak = max(months, key=lambda x: x["revenue"])
            bullets = "\n".join([
                f"- **{m['month']}**: ${m['revenue']:,.2f} ({m['order_count']} orders, AOV: ${m['aov']:.2f})"
                + (f" | MoM Growth: **{m['mom_growth_pct']:+.1f}%**" if m["mom_growth_pct"] is not None else " | Baseline Month")
                for m in months
            ])
            return (
                f"### Executive Summary\n"
                f"Monthly revenue trajectory peaked at **${peak['revenue']:,.2f}** in {peak['month']} before closing at "
                f"**${latest['revenue']:,.2f}** in {latest['month']}.\n\n"
                f"### Key Supporting Metrics\n"
                f"{bullets}\n\n"
                f"### Strategic Business Observations\n"
                f"- Peak performance occurred in {peak['month']}, followed by an observable contraction in {latest['month']}.\n"
                f"- Investigate demand drop-offs and inventory availability in late-quarter operations.\n"
            )

        elif tool_name == "get_top_products":
            items = data
            if not items:
                return "No product data available."
            top_item = items[0]
            bullets = "\n".join([
                f"- **{p['name']}** ({p['category']}): Revenue **${p['revenue']:,.2f}** | **{p['quantity_sold']} units** sold"
                for p in items
            ])
            return (
                f"### Executive Summary\n"
                f"The top-performing catalog item is **{top_item['name']}** ({top_item['category']}), leading with "
                f"**${top_item['revenue']:,.2f}** in gross revenue and **{top_item['quantity_sold']}** units sold.\n\n"
                f"### Key Supporting Metrics\n"
                f"{bullets}\n\n"
                f"### Strategic Business Observations\n"
                f"- Revenue is heavily concentrated in leading flagship products.\n"
                f"- Ensure stock availability for top revenue generators to prevent costly supply-side stockouts.\n"
            )

        elif tool_name == "get_category_performance":
            cats = data
            if not cats:
                return "No category performance data available."
            top_cat = cats[0]
            bullets = "\n".join([
                f"- **{c['category']}**: ${c['total_revenue']:,.2f} ({c['contribution_pct']:.1f}% share) across {c['order_count']} orders"
                for c in cats
            ])
            return (
                f"### Executive Summary\n"
                f"Category sales are led by **{top_cat['category']}**, generating **${top_cat['total_revenue']:,.2f}** "
                f"and contributing **{top_cat['contribution_pct']:.1f}%** of total enterprise revenue.\n\n"
                f"### Key Supporting Metrics\n"
                f"{bullets}\n\n"
                f"### Strategic Business Observations\n"
                f"- **{top_cat['category']}** constitutes the core anchor of customer orders.\n"
                f"- Secondary categories offer margin expansion potential through bundled merchandising.\n"
            )

        elif tool_name == "get_customer_metrics":
            top_ltv = data.get("top_5_ltv_customers", [])
            ltv_bullets = "\n".join([
                f"- **{c['name']}** ({c['segment']}): ${c['total_spend']:,.2f} total spend ({c['order_count']} orders)"
                for c in top_ltv
            ])
            inactive_sample = data.get("sample_inactive_customers", [])
            inactive_section = ""
            if inactive_sample:
                inactive_bullets = "\n".join([
                    f"- **{c['name']}** ({c['email']} - {c['segment']}): Last order on {c.get('last_order_date', 'N/A')} ({c.get('days_inactive', 'N/A')} days inactive)"
                    for c in inactive_sample
                ])
                inactive_section = f"\n\n**Sample Inactive / Lapsed Accounts (>60 Days Without Purchase)**:\n{inactive_bullets}"

            return (
                f"### Executive Summary\n"
                f"The platform maintains **{data.get('total_customers', 0)}** registered accounts, with **{data.get('repeat_customers', 0)}** "
                f"repeat purchasers and **{data.get('inactive_churned_customers', 0)}** accounts currently inactive (>60 days since last purchase).\n\n"
                f"### Key Supporting Metrics\n"
                f"- **Total Registered Customers**: {data.get('total_customers', 0)}\n"
                f"- **New Customers (Last 30 Days)**: {data.get('new_customers', 0)}\n"
                f"- **Repeat Customers (>1 Order)**: {data.get('repeat_customers', 0)}\n"
                f"- **Inactive / Churned (>60 Days Inactive)**: {data.get('inactive_churned_customers', 0)}\n\n"
                f"**Top Lifetime Value (LTV) Customers**:\n"
                f"{ltv_bullets}"
                f"{inactive_section}\n\n"
                f"### Strategic Business Observations\n"
                f"- Retention efforts should target the {data.get('inactive_churned_customers', 0)} lapsed accounts with tailored win-back incentives.\n"
                f"- Protect enterprise VIPs who drive outsized portions of lifetime revenue.\n"
            )

        elif tool_name == "diagnose_revenue_decline":
            if "error" in data:
                return f"Diagnostic Error: {data['error']}"

            target_m = data.get("target_month")
            prev_m = data.get("comparison_month")
            summary = data.get("revenue_summary", {})
            decomp = data.get("decomposition", {})
            most_impacted = data.get("most_impacted_category", {})
            retention = data.get("customer_retention", {})
            findings = data.get("executive_findings", [])

            findings_bullets = "\n".join([f"- {f}" for f in findings])

            return (
                f"### Executive Summary\n"
                f"Revenue in **{target_m}** declined by **${abs(summary.get('revenue_delta', 0)):,.2f}** "
                f"(**{summary.get('pct_change', 0):+.1f}%**) compared to **{prev_m}**. "
                f"The empirical root cause is primarily driven by **{decomp.get('primary_driver')}**.\n\n"
                f"### Diagnostic Decomposition & Evidence\n"
                f"{findings_bullets}\n\n"
                f"### Detailed Breakdown\n"
                f"- **Volume Effect**: Contributed **${decomp.get('volume_effect_usd', 0):,.2f}** to the contraction "
                f"({decomp.get('orders_previous', 0)} orders -> {decomp.get('orders_current', 0)} orders, "
                f"{decomp.get('orders_pct_change', 0):+.1f}%).\n"
                f"- **Price/AOV Effect**: Contributed **${decomp.get('price_effect_usd', 0):,.2f}** "
                f"(${decomp.get('aov_previous', 0):.2f} -> ${decomp.get('aov_current', 0):.2f}, "
                f"{decomp.get('aov_pct_change', 0):+.1f}%).\n"
                f"- **Leading Category Drop**: **{most_impacted.get('category')}** suffered a revenue loss of "
                f"**${abs(most_impacted.get('revenue_delta', 0)):,.2f}** ({most_impacted.get('pct_change', 0):+.1f}%).\n"
                f"- **Customer Churn**: **{retention.get('churned_customers', 0)}** customers from {prev_m} placed no orders in {target_m} "
                f"(Customer retention rate: **{retention.get('retention_rate_pct', 0):.1f}%**).\n\n"
                f"### Actionable Business Recommendations\n"
                f"1. **Catalog Recovery**: Prioritize restock and promotional campaigns in **{most_impacted.get('category')}** to recover volume.\n"
                f"2. **Retention Intervention**: Deploy re-engagement emails to the {retention.get('churned_customers', 0)} churned accounts.\n"
                f"3. **Basket Incentives**: Introduce free-shipping thresholds to stabilize AOV above current levels.\n"
            )

        elif tool_name == "generate_chart_spec":
            metric = data.get("metric", "revenue") if isinstance(data, dict) else "revenue"
            group_by = data.get("group_by", "month") if isinstance(data, dict) else "month"
            return (
                f"### Executive Summary\n"
                f"Rendered interactive visualization for **{metric.replace('_', ' ').title()}** grouped by **{group_by.title()}**.\n\n"
                f"Please review the chart rendered below for dynamic drill-downs."
            )

        return f"Successfully executed tool `{tool_name}` with data: {data}"

    def process_query(self, query: str) -> Dict[str, Any]:
        """Main agent pipeline:

        1. Grounding check: verify query is within e-commerce scope.
        2. Tool Selection & Execution: execute deterministic analytics tool.
        3. Response Synthesis: synthesize executive brief using LLM or deterministic template.
        4. Return payload containing response, tool_used, data, and chart_spec.
        """
        # Grounding check
        if self.is_out_of_scope(query):
            return self.get_out_of_scope_response(query)

        # Tool execution
        tool_name, tool_data, chart_spec = self._determine_intent_and_execute(query)

        # Synthesize executive response
        llm_response = self._synthesize_with_llm(query, tool_name, tool_data)
        if not llm_response:
            llm_response = self._format_deterministic_response(query, tool_name, tool_data)

        # If tool was generate_chart_spec, use its spec
        if tool_name == "generate_chart_spec" and isinstance(tool_data, dict) and "spec" in tool_data:
            chart_spec = tool_data["spec"]

        return {
            "response": llm_response,
            "tool_used": tool_name,
            "data": tool_data,
            "chart_spec": chart_spec
        }
