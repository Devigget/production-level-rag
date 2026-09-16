import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from src.mcp.tools import FinancialCalculator, financial_search, inspect_graph_entity


def test_growth_rate_calculation():
    result = FinancialCalculator.calculate_growth_rate(100, 125)

    assert result.absolute_change == 25
    assert result.percentage_growth == 25


def test_growth_rate_rejects_zero_prior_value():
    with pytest.raises(ValueError, match="prior_value"):
        FinancialCalculator.calculate_growth_rate(0, 10)


def test_ebitda_calculation():
    result = FinancialCalculator.calculate_ebitda(1_000, 400, 250, 50, 25)

    assert result.gross_profit == 600
    assert result.operating_income_ebit == 350
    assert result.ebitda == 425
    assert result.ebitda_margin_percent == 42.5


def test_ebitda_rejects_zero_revenue_for_margin():
    with pytest.raises(ValueError, match="revenue"):
        FinancialCalculator.calculate_ebitda(0, 0, 0)


def test_financial_search_bridge_serializes_retrieval_result():
    retrieval = MagicMock()
    retrieval.retrieve.return_value.model_dump.return_value = {"query": "revenue"}

    assert financial_search(retrieval, "revenue") == {"query": "revenue"}
    retrieval.retrieve.assert_called_once_with("revenue")


def test_graph_inspection_uses_parameterized_entity_lookup():
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value.single.return_value = {
        "entity_name": "Revenue",
        "category": "metric",
        "relations": [{"type": "RELATED", "connected_entity": "Sales"}],
    }

    result = inspect_graph_entity(driver, "Revenue")

    assert result["relations"][0]["connected_entity"] == "Sales"
    session.run.assert_called_once()
    assert session.run.call_args.kwargs["entity_name"] == "Revenue"


def test_mcp_server_registers_expected_tool_signatures():
    pytest.importorskip("mcp")
    from src.mcp.server import create_server

    server = create_server()
    tools = server.list_tools()
    if inspect.isawaitable(tools):
        tools = asyncio.run(tools)
    names = {tool.name for tool in tools}

    assert {"calculate_growth_rate", "calculate_ebitda", "financial_search", "inspect_graph_entity"} <= names
    growth_tool = next(tool for tool in tools if tool.name == "calculate_growth_rate")
    schema = getattr(growth_tool, "parameters", None) or growth_tool.input_schema
    assert set(schema["properties"]) == {"prior_value", "current_value"}
