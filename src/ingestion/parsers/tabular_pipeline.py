"""Dual-path ingestion for tabular files (.xlsx, .xls, .csv).

Path 1: Vector Store Ingestion via Header-Injected Row Serialization.
Path 2: Graph DB Ingestion via LLM Schema Blueprint to Deterministic Parameterized Cypher.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.ingestion.models import FinancialChunk, FinancialRecord

logger = logging.getLogger(__name__)


def serialize_tabular_row(
    row: dict[str, Any],
    store_name: str,
    row_index: int,
) -> str:
    """Serialize a single tabular record into an explicit key-value header-injected string."""
    fields = [f"Store: {store_name}", f"Row: {row_index}"]
    for col, val in row.items():
        if pd.notna(val) and str(val).strip() != "":
            clean_val = str(val).replace("\n", " ").strip()
            fields.append(f"{col}: {clean_val}")
    return " | ".join(fields)


def dataframe_to_markdown_clean(dataframe: pd.DataFrame) -> str:
    """Render dataframe as clean Markdown table."""
    normalized = dataframe.fillna("").astype(str)
    headers = [str(c).replace("|", "\\|") for c in normalized.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in normalized.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in row) + " |")
    return "\n".join(lines)


def _numeric_value(value: object) -> float | None:
    cleaned = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_tabular_vector_chunks(
    dataframe: pd.DataFrame,
    store_id: str,
    store_name: str,
    doc_id: str,
    source_file: str,
    sheet_name: str,
) -> list[FinancialChunk]:
    """Build header-injected row chunks for dense vector embedding and retrieval."""
    chunks: list[FinancialChunk] = []
    if dataframe.empty:
        return chunks

    metric_col = dataframe.columns[0]
    for idx, row in dataframe.iterrows():
        row_dict = row.to_dict()
        serialized_text = serialize_tabular_row(row_dict, store_name, idx)
        
        # Build structured records
        metric_val = str(row_dict.get(metric_col, "")).strip()
        row_structured_records = []
        if metric_val and metric_val.lower() != "nan":
            for col in dataframe.columns[1:]:
                val = str(row_dict.get(col, "")).strip()
                if val and val.lower() != "nan":
                    rec = FinancialRecord(
                        metric=metric_val,
                        period=str(col),
                        value=_numeric_value(val),
                        raw_value=val,
                        source_file=source_file,
                        sheet_name=sheet_name,
                        store_id=store_id,
                        doc_id=doc_id,
                    )
                    row_structured_records.append(rec)

        chunks.append(
            FinancialChunk(
                chunk_id=f"{source_file}:{sheet_name}:row-{idx}",
                content=serialized_text,
                chunk_type="table",
                source_file=source_file,
                store_id=store_id,
                doc_id=doc_id,
                source_type="tabular",
                metadata={
                    "store_id": store_id,
                    "store_name": store_name,
                    "doc_id": doc_id,
                    "source_type": "tabular",
                    "row_index": int(idx),
                    "sheet_name": sheet_name,
                },
                structured_records=row_structured_records,
            )
        )

    return chunks


def extract_schema_blueprint(
    dataframe: pd.DataFrame,
    llm_invoker: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """Extract schema blueprint using LLM with deterministic fallback."""
    columns = [str(c) for c in dataframe.columns]
    if not columns:
        return {}

    # 1. Deterministic heuristic baseline
    key_col = columns[0]
    category_col = None
    metric_edges = []
    
    for col in columns[1:]:
        is_temporal = bool(re.search(r"Q\d|20\d\d|19\d\d|date|period|month|year", col, re.I))
        temporal_node = "Quarter" if re.search(r"Q\d", col, re.I) else "Date" if "date" in col.lower() else "Period"
        metric_edges.append({
            "edge_name": "REPORTED_VALUE",
            "value_column": col,
            "target_temporal_node": temporal_node,
            "temporal_value": col,
        })

    heuristic_blueprint = {
        "entity_label": "Metric",
        "key_column": key_col,
        "category_label": "Category" if category_col else None,
        "relationship_name": "IN_CATEGORY" if category_col else None,
        "metric_edges": metric_edges,
    }

    # 2. Try LLM Schema Profiling if LLM invoker provided
    if llm_invoker:
        preview_rows = dataframe.head(3).to_dict(orient="records")
        prompt = (
            "Analyze this table schema and return a JSON blueprint with:\n"
            "- entity_label: Node label for main subject (e.g. 'Metric', 'Product', 'Account')\n"
            "- key_column: Name of primary column containing the entity names\n"
            "- category_label: Optional category label or null\n"
            "- relationship_name: Relationship name to category or null\n"
            "- metric_edges: Array of objects with edge_name, value_column, target_temporal_node (e.g. 'Quarter', 'Year', 'Date')\n\n"
            f"Columns: {columns}\n"
            f"Preview:\n{json.dumps(preview_rows, default=str)}\n\n"
            "Return valid JSON ONLY, no explanation."
        )
        try:
            response = llm_invoker(prompt)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if "key_column" in parsed and parsed["key_column"] in columns:
                    return parsed
        except Exception as exc:
            logger.warning("LLM schema blueprint extraction failed: %s. Using heuristic.", exc)

    return heuristic_blueprint


def compile_cypher_statements(
    blueprint: dict[str, Any],
) -> list[str]:
    """Compile schema blueprint into parameterized Cypher batch MERGE statements."""
    statements: list[str] = []
    key_col = blueprint.get("key_column")
    entity_label = blueprint.get("entity_label", "Metric")
    if not key_col:
        return statements

    # 1. Setup Root Store and Document
    statements.append(
        """
        MERGE (s:Store {id: $store_id})
        ON CREATE SET s.name = $store_name
        MERGE (d:Document {id: $doc_id})
        ON CREATE SET d.filename = $filename, d.store_id = $store_id
        MERGE (s)-[:HAS_DOCUMENT]->(d)
        """
    )

    # 2. Batch merge entities with store-scoped composite IDs
    statements.append(
        f"""
        UNWIND $rows AS row
        WITH row WHERE row['{key_col}'] IS NOT NULL AND toString(row['{key_col}']) <> ''
        MERGE (e:{entity_label} {{id: $store_id + '#' + toString(row['{key_col}'])}})
        SET e.name = toString(row['{key_col}']),
            e.store_id = $store_id,
            e.category = '{entity_label}'
        WITH e
        MATCH (s:Store {{id: $store_id}})
        MATCH (d:Document {{id: $doc_id}})
        MERGE (s)-[:CONTAINS]->(e)
        MERGE (d)-[:DEFINES]->(e)
        """
    )

    # 3. Batch merge metric edges with temporal nodes
    for edge in blueprint.get("metric_edges", []):
        val_col = edge.get("value_column")
        temporal_node = edge.get("target_temporal_node", "Period")
        temporal_val = edge.get("temporal_value", val_col)
        edge_name = edge.get("edge_name", "HAS_VALUE")
        if not val_col:
            continue

        statements.append(
            f"""
            UNWIND $rows AS row
            WITH row WHERE row['{key_col}'] IS NOT NULL AND row['{val_col}'] IS NOT NULL AND toString(row['{val_col}']) <> ''
            MATCH (e:{entity_label} {{id: $store_id + '#' + toString(row['{key_col}'])}})
            MERGE (t:{temporal_node} {{id: $store_id + '#' + '{temporal_val}'}})
            SET t.name = '{temporal_val}', t.store_id = $store_id
            MERGE (e)-[r:{edge_name} {{doc_id: $doc_id, store_id: $store_id}}]->(t)
            SET r.value = toString(row['{val_col}']),
                r.source_file = $filename
            """
        )

    return statements


def execute_cypher_ingestion(
    driver: Any,
    database: str,
    statements: list[str],
    store_id: str,
    store_name: str,
    doc_id: str,
    filename: str,
    dataframe: pd.DataFrame,
) -> int:
    """Run compiled parameterized Cypher statements in Neo4j."""
    if not statements or dataframe.empty:
        return 0
    records = dataframe.to_dict(orient="records")
    # Clean records to handle NaN
    clean_records = [
        {str(k): ("" if pd.isna(v) else str(v)) for k, v in rec.items()}
        for rec in records
    ]
    params = {
        "store_id": store_id,
        "store_name": store_name,
        "doc_id": doc_id,
        "filename": filename,
        "rows": clean_records,
    }
    nodes_affected = 0
    try:
        with driver.session(database=database) as session:
            for statement in statements:
                res = session.run(statement, **params)
                summary = res.consume()
                counters = getattr(summary, "counters", None)
                if counters:
                    nodes_affected += counters.nodes_created + counters.relationships_created
    except Exception as exc:
        logger.error("Failed to execute Cypher batch ingestion: %s", exc)
    return nodes_affected
