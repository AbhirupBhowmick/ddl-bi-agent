import pytest
from backend.agent import BIAgent
from backend.tools import get_kpis


@pytest.fixture
def agent():
    return BIAgent()


def test_out_of_scope_weather_prompt(agent):
    res = agent.process_query("What is the weather in New York tomorrow?")
    assert res["tool_used"] == "none (out_of_scope)"
    assert res["chart_spec"] is None
    assert "outside these transactional analytics boundaries" in res["response"] or "specialize exclusively" in res["response"]


def test_out_of_scope_salary_prompt(agent):
    res = agent.process_query("Can you tell me the employee salaries in marketing?")
    assert res["tool_used"] == "none (out_of_scope)"
    assert res["chart_spec"] is None
    assert "analytics boundaries" in res["response"].lower()


def test_out_of_scope_political_trivia(agent):
    res = agent.process_query("Who is the president of France?")
    assert res["tool_used"] == "none (out_of_scope)"
    assert res["chart_spec"] is None


def test_grounded_kpi_figures_match_tool(agent):
    """Verifies that the generated response quotes the EXACT numbers returned by the tool."""
    kpi_data = get_kpis()
    res = agent.process_query("What are the total revenue and orders?")

    assert res["tool_used"] == "get_kpis"
    data = res["data"]
    assert data["total_revenue"] == kpi_data["total_revenue"]
    assert data["total_completed_orders"] == kpi_data["total_completed_orders"]

    # Verify that formatted text contains the exact string representation of revenue or orders
    formatted_rev = f"{kpi_data['total_revenue']:,.2f}"
    orders_str = f"{kpi_data['total_completed_orders']:,}"

    assert formatted_rev in res["response"] or str(int(kpi_data["total_revenue"])) in res["response"]
    assert orders_str in res["response"] or str(kpi_data["total_completed_orders"]) in res["response"]


def test_chart_spec_generation_grounding(agent):
    res = agent.process_query("Show monthly revenue as a chart")
    assert res["tool_used"] in ["generate_chart_spec", "get_monthly_revenue"]
    assert res["chart_spec"] is not None
    assert "data" in res["chart_spec"]
    assert "layout" in res["chart_spec"]

