"""Extract financial entities and relations from ingestion chunks."""

import re
from typing import Any

from pydantic import BaseModel, Field

from src.ingestion.models import FinancialChunk


class GraphEntity(BaseModel):
    name: str
    category: str


class GraphRelation(BaseModel):
    source_entity: str
    target_entity: str
    relationship_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ExtractedGraphData(BaseModel):
    entities: list[GraphEntity]
    relations: list[GraphRelation]


class GraphExtractor:
    """Extract document, line-item, quarter, and reported-value relationships."""

    def extract(self, chunk: FinancialChunk) -> ExtractedGraphData:
        entities: dict[tuple[str, str], GraphEntity] = {}
        relations: list[GraphRelation] = []

        def add_entity(name: str, category: str) -> None:
            if name:
                entities[(name, category)] = GraphEntity(name=name, category=category)

        add_entity(chunk.source_file, "Document")
        rows = self._markdown_rows(chunk.content)
        if rows:
            headers, data_rows = rows
            for row in data_rows:
                if not row or not row[0]:
                    continue
                metric = row[0]
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
                    add_entity(header, "Quarter" if re.search(r"Q\d", header, re.IGNORECASE) else "Metric")
                    relations.append(
                        GraphRelation(
                            source_entity=metric,
                            target_entity=header,
                            relationship_type="HAS_VALUE",
                            properties={
                                "value": value,
                                "chunk_id": chunk.chunk_id,
                                "content": chunk.content,
                                "source_file": chunk.source_file,
                            },
                        )
                    )
        else:
            for phrase in re.findall(r"\b(?:Revenue|Expenses?|Profit|Income|EBITDA)\b", chunk.content, re.IGNORECASE):
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