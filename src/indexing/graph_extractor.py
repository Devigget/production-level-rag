"""Extract financial entities and relations from ingestion chunks."""

import re
from typing import Any

from pydantic import BaseModel, Field

from src.ingestion.models import FinancialChunk


class GraphEntity(BaseModel):
    name: str
    category: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphRelation(BaseModel):
    source_entity: str
    target_entity: str
    relationship_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ExtractedGraphData(BaseModel):
    entities: list[GraphEntity]
    relations: list[GraphRelation]


def _parse_numeric(val: Any) -> float | None:
    if val is None:
        return None
    cleaned = str(val).strip().replace(",", "").replace("$", "")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_quarter_info(name: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    q_match = re.search(r"Q([1-4])", name, re.I)
    if q_match:
        info["quarter"] = int(q_match.group(1))
    y_match = re.search(r"(20\d\d|19\d\d)", name)
    if y_match:
        info["year"] = int(y_match.group(1))
    return info


class GraphExtractor:
    """Extract document, line-item, quarter, and reported-value relationships."""

    def extract(self, chunk: FinancialChunk) -> ExtractedGraphData:
        entities: dict[tuple[str, str], GraphEntity] = {}
        relations: list[GraphRelation] = []

        def add_entity(name: str, category: str, properties: dict[str, Any] | None = None) -> None:
            if name and not name.lower().startswith("unnamed:"):
                props = dict(properties or {})
                if category == "Quarter" and not props:
                    props = _parse_quarter_info(name)
                entities[(name, category)] = GraphEntity(name=name, category=category, properties=props)

        add_entity(chunk.source_file, "Document")
        rows = self._markdown_rows(chunk.content)
        if rows:
            headers, data_rows = rows

            # Identify quarter headers and establish chronological sequence
            quarter_headers: list[str] = []
            for h in headers[1:]:
                if h and not h.lower().startswith("unnamed:") and re.search(r"Q\d", h, re.I):
                    quarter_headers.append(h)

            for i in range(len(quarter_headers) - 1):
                relations.append(
                    GraphRelation(
                        source_entity=quarter_headers[i],
                        target_entity=quarter_headers[i + 1],
                        relationship_type="NEXT_PERIOD",
                        properties={
                            "chunk_id": chunk.chunk_id,
                            "source_file": chunk.source_file,
                        },
                    )
                )

            for row in data_rows:
                if not row or not row[0]:
                    continue
                metric = row[0]
                if metric.lower().startswith("unnamed:") or metric.lower() in {"line item", "metric", "category", "account", "quarter"} or "synthetic" in metric.lower():
                    continue
                add_entity(metric, "Metric")
                relations.append(
                    GraphRelation(
                        source_entity=chunk.source_file,
                        target_entity=metric,
                        relationship_type="REPORTED_METRIC",
                        properties={
                            "chunk_id": chunk.chunk_id,
                            "content": chunk.content,
                            "source_file": chunk.source_file,
                        },
                    )
                )
                for header, value in zip(headers[1:], row[1:]):
                    if not header or not value:
                        continue
                    if header.lower().startswith("unnamed:"):
                        continue
                    is_quarter = bool(re.search(r"Q\d", header, re.I))
                    category = "Quarter" if is_quarter else "Metric"
                    add_entity(header, category)
                    relations.append(
                        GraphRelation(
                            source_entity=metric,
                            target_entity=header,
                            relationship_type="HAS_VALUE",
                            properties={
                                "value": value,
                                "numeric_value": _parse_numeric(value),
                                "chunk_id": chunk.chunk_id,
                                "content": chunk.content,
                                "source_file": chunk.source_file,
                            },
                        )
                    )
        else:
            for phrase in re.findall(r"\b(?:Revenue|Expenses?|Profit|Income|EBITDA)\b", chunk.content, re.I):
                metric = phrase.title()
                add_entity(metric, "Metric")
                relations.append(
                    GraphRelation(
                        source_entity=chunk.source_file,
                        target_entity=metric,
                        relationship_type="MENTIONS",
                        properties={
                            "chunk_id": chunk.chunk_id,
                            "content": chunk.content,
                            "source_file": chunk.source_file,
                        },
                    )
                )
        return ExtractedGraphData(entities=list(entities.values()), relations=relations)

    @staticmethod
    def _markdown_rows(content: str) -> tuple[list[str], list[list[str]]] | None:
        lines = [line.strip() for line in content.splitlines() if line.strip().startswith("|")]
        if len(lines) < 3:
            return None
        parse = lambda line: [cell.strip().replace("\\|", "|") for cell in line.strip("|").split("|")]
        headers = parse(lines[0])
        data_rows = [parse(line) for line in lines[2:]]
        return headers, data_rows