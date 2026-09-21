"""Business logic exposed through the Model Context Protocol server."""

from typing import Any

from pydantic import BaseModel

from src.retrieval.models import RetrievalQuery


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


class FinancialCalculator:
    """Deterministic financial calculations used by MCP and application code."""

    @staticmethod
    def calculate_growth_rate(prior_value: float, current_value: float) -> GrowthRateResult:
        if prior_value == 0:
            raise ValueError("prior_value must not be zero")
        absolute_change = current_value - prior_value
        return GrowthRateResult(
            absolute_change=absolute_change,
            percentage_growth=(absolute_change / prior_value) * 100,
        )

    @staticmethod
    def calculate_ebitda(
        revenue: float,
        cogs: float,
        operating_expenses: float,
        depreciation: float = 0.0,
        amortization: float = 0.0,
    ) -> EbitdaResult:
        if revenue == 0:
            raise ValueError("revenue must not be zero when calculating EBITDA margin")
        gross_profit = revenue - cogs
        operating_income_ebit = gross_profit - operating_expenses
        ebitda = operating_income_ebit + depreciation + amortization
        return EbitdaResult(
            gross_profit=gross_profit,
            operating_income_ebit=operating_income_ebit,
            ebitda=ebitda,
            ebitda_margin_percent=(ebitda / revenue) * 100,
        )


def financial_search(retrieval_engine: Any, query: str) -> dict[str, Any]:
    """Run hybrid retrieval and serialize its result for an MCP client."""
    result = retrieval_engine.retrieve(query)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(result)


def build_dashboard_payload(retrieval_engine: Any, query: str) -> dict[str, Any]:
    """Return validated structured records for a Power BI MCP connector."""
    result = retrieval_engine.retrieve(
        RetrievalQuery(query_text=query, top_k_graph=0, retrieval_mode="auto")
    )
    contexts = result.ranked_contexts if hasattr(result, "ranked_contexts") else []
    rows = []
    for context in contexts:
        if context.source_type != "structured_record":
            continue
        metadata = context.metadata
        rows.append({
            "metric": metadata.get("metric"),
            "period": metadata.get("period"),
            "value": metadata.get("value"),
            "source_file": metadata.get("source_file"),
            "sheet_name": metadata.get("sheet_name"),
            "citation_id": context.id,
        })
    return {"query": query, "rows": rows, "source_count": len(rows)}


def inspect_graph_entity(graph_driver: Any, entity_name: str) -> dict[str, Any]:
    """Return a graph entity and its immediate relationships."""
    query = """
    MATCH (entity:FinancialEntity {name: $entity_name})
    OPTIONAL MATCH (entity)-[relation]-(connected:FinancialEntity)
    RETURN entity.name AS entity_name,
           entity.category AS category,
           collect({
               type: type(relation),
               direction: CASE WHEN startNode(relation) = entity THEN 'outgoing' ELSE 'incoming' END,
               connected_entity: connected.name,
               properties: properties(relation)
           }) AS relations
    """
    with graph_driver.session() as session:
        record = session.run(query, entity_name=entity_name).single()
    if record is None:
        return {"entity_name": entity_name, "category": None, "relations": []}
    data = dict(record)
    return {
        "entity_name": data.get("entity_name", entity_name),
        "category": data.get("category"),
        "relations": [
            dict(relation)
            for relation in data.get("relations", [])
            if relation.get("connected_entity")
        ],
    }
