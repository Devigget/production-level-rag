"""Deterministic retrieval for normalized financial table records."""

import re
from collections.abc import Iterable

from src.ingestion.models import FinancialChunk, FinancialRecord

from .models import RetrievedContext


class StructuredFinancialStore:
    def __init__(self) -> None:
        self.records: list[FinancialRecord] = []

    def upsert(self, chunks: Iterable[FinancialChunk]) -> int:
        chunks = list(chunks)
        incoming = [record for chunk in chunks for record in chunk.structured_records]
        by_id = {
            (record.source_file, record.sheet_name, record.metric, record.period): record
            for record in self.records
        }
        by_id.update(
            ((record.source_file, record.sheet_name, record.metric, record.period), record)
            for record in incoming
        )
        self.records = list(by_id.values())
        return len(self.records)

    def search(self, query: str, limit: int = 10) -> list[RetrievedContext]:
        query_terms = set(re.findall(r"[a-z0-9_]+", query.lower()))
        matches: list[tuple[int, FinancialRecord]] = []
        for record in self.records:
            record_terms = set(re.findall(r"[a-z0-9_]+", f"{record.metric} {record.period}".lower()))
            overlap = len(query_terms & record_terms)
            if overlap:
                matches.append((overlap, record))
        matches.sort(key=lambda item: item[0], reverse=True)
        return [self._to_context(record, score) for score, record in matches[:limit]]

    @staticmethod
    def _to_context(record: FinancialRecord, score: int) -> RetrievedContext:
        return RetrievedContext(
            id=f"{record.source_file}:{record.metric}:{record.period}",
            content=f"{record.metric} for {record.period}: {record.raw_value}",
            source_type="structured_record",
            initial_score=float(score),
            metadata={
                "metric": record.metric,
                "period": record.period,
                "value": record.value,
                "source_file": record.source_file,
                "sheet_name": record.sheet_name,
            },
        )