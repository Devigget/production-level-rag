from unittest.mock import MagicMock

from src.retrieval.engine import HybridRetrievalEngine
from src.retrieval.graph_search import GraphSearcher
from src.retrieval.models import RetrievedContext, RetrievalQuery
from src.retrieval.reranker import CrossEncoderReranker


def context(identifier: str, score: float, source: str = "vector_chunk") -> RetrievedContext:
    return RetrievedContext(
        id=identifier,
        content=f"content for {identifier}",
        source_type=source,
        initial_score=score,
    )


def test_hybrid_engine_deduplicates_by_context_id():
    vector = MagicMock()
    vector.search.return_value = [context("same", 0.8), context("vector-only", 0.7)]
    graph = MagicMock()
    graph.search.return_value = [context("same", 0.9, "graph_subgraph"), context("graph-only", 0.6)]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda query, items, top_n: items[:top_n]

    result = HybridRetrievalEngine(vector, graph, reranker).retrieve(
        RetrievalQuery(query_text="revenue", final_top_n=10)
    )

    assert result.total_candidates_evaluated == 3
    assert [item.id for item in result.ranked_contexts] == ["same", "vector-only", "graph-only"]
    assert result.ranked_contexts[0].initial_score == 0.9


def test_engine_uses_mock_retrieval_and_limits_results():
    vector = MagicMock()
    vector.search.return_value = [context("one", 0.8)]
    graph = MagicMock()
    graph.search.return_value = [context("two", 0.7, "graph_subgraph")]
    reranker = MagicMock()
    reranker.rerank.return_value = [context("two", 0.7, "graph_subgraph")]

    result = HybridRetrievalEngine(vector, graph, reranker).retrieve(
        RetrievalQuery(query_text="revenue", top_k_vector=2, top_k_graph=3, final_top_n=1)
    )

    vector.search.assert_called_once_with("revenue", 2, None)
    graph.search.assert_called_once_with("revenue", 3)
    assert len(result.ranked_contexts) == 1


def test_engine_skips_graph_search_when_graph_expansion_is_disabled():
    vector = MagicMock()
    vector.search.return_value = [context("vector-only", 0.8)]
    graph = MagicMock()
    reranker = MagicMock()
    reranker.rerank.return_value = [context("vector-only", 0.8)]

    result = HybridRetrievalEngine(vector, graph, reranker).retrieve(
        RetrievalQuery(query_text="revenue", top_k_graph=0)
    )

    graph.search.assert_not_called()
    assert result.ranked_contexts[0].id == "vector-only"


def test_empty_retrieval_returns_empty_result_without_reranking():
    vector = MagicMock()
    vector.search.return_value = []
    graph = MagicMock()
    graph.search.return_value = []
    reranker = MagicMock()

    result = HybridRetrievalEngine(vector, graph, reranker).retrieve("nothing")

    assert result.ranked_contexts == []
    assert result.total_candidates_evaluated == 0
    reranker.rerank.assert_called_once_with("nothing", [], 5)


def test_cross_encoder_reranker_sorts_scores_descending():
    model = MagicMock()
    model.predict.return_value = [0.1, 0.9, 0.4]
    contexts = [context("low", 0.1), context("high", 0.2), context("middle", 0.3)]

    ranked = CrossEncoderReranker(model=model).rerank("query", contexts)

    assert [item.id for item in ranked] == ["high", "middle", "low"]
    assert [item.rerank_score for item in ranked] == [0.9, 0.4, 0.1]


def test_graph_search_maps_cypher_records_to_contexts():
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value = [
        {
            "id": "pnl:sample_pnl",
            "content": "$1200000",
            "score": 1.0,
            "metadata": {"hops": 1},
        }
    ]

    result = GraphSearcher(driver=driver).search("revenue", limit=2)

    assert result[0].source_type == "graph_subgraph"
    assert result[0].id == "pnl:sample_pnl"
    session.run.assert_called_once()