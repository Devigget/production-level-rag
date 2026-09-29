# Spec 05: Model Context Protocol (MCP) Server & Financial Tooling

## 1. Goal & Scope
Build a standardized Model Context Protocol (MCP) server exposing financial retrieval, analytical calculations, and Power BI dashboard payloads to external agents (e.g., Claude Desktop, Cursor, OpenAI Agents):
- **Deterministic Math & Financial Calculations**:
  - LLMs must not perform direct arithmetic. Calculations (EBITDA, growth rates, margins) are executed via strictly typed Python tools with division-by-zero safeguards.
- **Exposed MCP Tools**:
  1. `financial_search`: Executes routed hybrid retrieval (structured + vector + graph) with optional `store_id` isolation.
  2. `calculate_growth_rate`: Computes absolute change and percentage growth between financial periods. Rejects zero prior values safely.
  3. `calculate_ebitda`: Computes gross profit, operating income (EBIT), EBITDA, and EBITDA margin percentage from revenue, COGS, OpEx, depreciation, and amortization.
  4. `inspect_graph_entity`: Parameterized entity lookup traversing connected nodes and relationship properties in Neo4j.
  5. `build_dashboard_payload`: Converts retrieved contexts into structured, verified rows ready for ingestion by Power BI and Grafana connectors.
- **Transports & Compatibility**:
  - Exposes tools via STDIO and SSE transports adhering to the official Model Context Protocol specifications.

## 2. Target File Tree
- `src/mcp/tools.py`               # Standalone financial calculation engines & retrieval adapters
- `src/mcp/server.py`              # FastMCP server registration and transport startup
- `tests/test_mcp.py`              # 8-test verification suite for tools and server signatures

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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
    store_id: Optional[str] = None
    limit: int = 10

class EntityInspectionResult(BaseModel):
    entity: str
    connections: List[Dict[str, Any]]

class DashboardPayloadResult(BaseModel):
    rows: List[Dict[str, Any]]
    source_count: int
```

## 4. Tool Implementation Details

### 4.1. Growth Rate Calculation (`calculate_growth_rate`)
- **Formula**:
  - Absolute Change: $\Delta = V_{\text{current}} - V_{\text{prior}}$
  - Percentage Growth: $G = \frac{V_{\text{current}} - V_{\text{prior}}}{V_{\text{prior}}} \times 100$
- **Guardrail**: If $V_{\text{prior}} == 0$, raises a `ValueError("prior_value must be non-zero to calculate percentage growth")` to prevent division-by-zero errors.

### 4.2. EBITDA Calculation (`calculate_ebitda`)
- **Formulas**:
  - Gross Profit: $\text{Revenue} - \text{COGS}$
  - Operating Income (EBIT): $\text{Gross Profit} - \text{OpEx}$
  - EBITDA: $\text{EBIT} + \text{Depreciation} + \text{Amortization}$
  - EBITDA Margin %: $\frac{\text{EBITDA}}{\text{Revenue}} \times 100$
- **Guardrail**: If $\text{Revenue} \le 0$, raises a `ValueError("Revenue must be positive to compute EBITDA margin")`.

### 4.3. Graph Entity Inspection (`inspect_graph_entity`)
Executes parameterized Cypher query against Neo4j:
```cypher
MATCH (e {name: $entity_name})
OPTIONAL MATCH (e)-[r]-(target)
WHERE ($store_id IS NULL OR r.store_id = $store_id OR e.store_id = $store_id)
RETURN e.name AS entity, type(r) AS relationship, target.name AS target, properties(r) AS properties
LIMIT $limit
```

### 4.4. Power BI Dashboard Payload Builder (`build_dashboard_payload`)
Filters retrieved candidates specifically for `source_type == "structured_record"`, extracting:
- `metric`: Financial KPI name (e.g., Revenue, COGS, EBITDA)
- `period`: Fiscal quarter or year (e.g., Q1 2025)
- `value`: Floating-point numeric value
- `source_file`: Provenance filename
- `citation_id`: Chunk identifier

## 5. Verification & Acceptance Criteria
Verified by **8 passing tests** in `tests/test_mcp.py`:
1. `test_growth_rate_calculation`: Confirms mathematical accuracy for positive and negative growth.
2. `test_growth_rate_rejects_zero_prior_value`: Confirms ValueError on zero baseline.
3. `test_ebitda_calculation`: Confirms calculations for Gross Profit, EBIT, EBITDA, and EBITDA Margin.
4. `test_ebitda_rejects_zero_revenue_for_margin`: Confirms rejection of zero/negative revenue.
5. `test_financial_search_bridge_serializes_retrieval_result`: Confirms serialization of hybrid retrieval into MCP response.
6. `test_dashboard_payload_contains_only_structured_records`: Confirms strict filtering to structured record candidates.
7. `test_graph_inspection_uses_parameterized_entity_lookup`: Confirms safe parameterized Cypher execution.
8. `test_mcp_server_registers_expected_tool_signatures`: Confirms registration of all 5 tool schemas in the FastMCP server.