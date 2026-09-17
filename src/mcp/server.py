"""FastMCP server exposing financial retrieval and analysis tools."""

from typing import Any

from .tools import FinancialCalculator
from .tools import financial_search as run_financial_search
from .tools import inspect_graph_entity as run_inspect_graph_entity

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # MCP 2.x renamed FastMCP to MCPServer.
    try:
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ModuleNotFoundError:  # pragma: no cover - minimal installations
        FastMCP = None  # type: ignore[assignment,misc]


def create_server(
    retrieval_engine: Any | None = None,
    graph_driver: Any | None = None,
    calculator: FinancialCalculator | None = None,
) -> Any:
    """Create an MCP server with injectable application dependencies."""
    if FastMCP is None:
        raise ImportError("MCP support requires the 'mcp' package")

    app = FastMCP("financial-rag")
    calculator = calculator or FinancialCalculator()

    @app.tool()
    def calculate_growth_rate(prior_value: float, current_value: float) -> dict[str, float]:
        return calculator.calculate_growth_rate(prior_value, current_value).model_dump()

    @app.tool()
    def calculate_ebitda(
        revenue: float,
        cogs: float,
        operating_expenses: float,
        depreciation: float = 0.0,
        amortization: float = 0.0,
    ) -> dict[str, float]:
        return calculator.calculate_ebitda(
            revenue, cogs, operating_expenses, depreciation, amortization
        ).model_dump()

    @app.tool()
    def financial_search(query: str) -> dict[str, Any]:
        if retrieval_engine is None:
            raise RuntimeError("retrieval_engine is not configured")
        return run_financial_search(retrieval_engine, query)

    @app.tool()
    def inspect_graph_entity(entity_name: str) -> dict[str, Any]:
        if graph_driver is None:
            raise RuntimeError("graph_driver is not configured")
        return run_inspect_graph_entity(graph_driver, entity_name)

    return app


if FastMCP is not None:
    mcp = create_server()

    if __name__ == "__main__":
        mcp.run()
