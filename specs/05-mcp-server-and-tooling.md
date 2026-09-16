# Spec 05: Model Context Protocol (MCP) Server & Financial Tooling

## 1. Goal & Scope
Build a standardized Model Context Protocol (MCP) server:
- Expose your financial hybrid retrieval and analytical calculations as callable tools.
- Implement tools for:
  1. `financial_search`: Executes hybrid vector + GraphRAG retrieval with reranking.
  2. `calculate_growth_rate`: Computes percentage change and CAGR between periods.
  3. `calculate_ebitda`: Computes EBITDA from revenue, operating expenses, depreciation, and amortization.
  4. `inspect_graph_entity`: Direct lookup of a financial node and its immediate relations in Neo4j.
- Run via standard STDIO or SSE transport compatible with MCP hosts (e.g., Claude Desktop, Cursor).

## 2. Target File Tree
- `src/mcp/tools.py`               # Standalone business logic and calculation engines
- `src/mcp/server.py`              # MCP server definition registering tools
- `tests/test_mcp.py`              # Tool validation and execution tests

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

class GrowthRateInput(BaseModel):
    prior_value: float
    current_value: float

class GrowthRateResult(BaseModel):
    absolute_change: float
    percentage_growth: float

class EbitdaInput(BaseModel):
    revenue: float
    cogs: float
    operating_expenses: float
    depreciation: float = 0.0
    amortization: float = 0.0

class EbitdaResult(BaseModel):
    gross_profit: float
    operating_income_ebit: float
    ebitda: float
    ebitda_margin_percent: float

class EntityInspectionInput(BaseModel):
    entity_name: str