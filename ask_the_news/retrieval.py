
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path

import numpy as np

from ask_the_news.config import (
    ARTICLE_AGGREGATION,
    ARTICLE_AGGREGATION_BONUS,
    ARTICLE_AGGREGATION_POOL_MULT,
    RETRIEVAL_TOP_K,
    TIMELINE_BUCKET_GRANULARITY,
    TIMELINE_MAX_ARTICLES,
    TIMELINE_MAX_PER_BUCKET,
    TIMELINE_RECALL_K,
    VECTOR_INDEX_IDS_PATH,
    VECTOR_INDEX_PATH,
)
from ask_the_news.embeddings import EmbeddingModel
from ask_the_news.models import Article, Citation, QAContext, QueryBundle, RetrievedChunk, TimelineContext, TimelineItem
from ask_the_news.query_router import build_query_bundle, guardrail_query
from ask_the_news.storage import SQLiteStorage


def article_aware_chunk_rerank(
    chunks: list[RetrievedChunk],
    top_k: int,
    second_chunk_bonus: float = ARTICLE_AGGREGATION_BONUS,
) -> list[RetrievedChunk]:
    """Rerank a candidate chunk pool using article-level aggregate scores.

    For each article, the aggregate score is `top_chunk_score + bonus *
    second_chunk_score`. Articles with multiple high-scoring chunks rank
    above articles with one strong chunk that may be a coincidence.
    Within an article, chunks keep their raw cosine score order.

    Returns at most `top_k` chunks, with ranks renumbered 1..top_k.
    """
    if not chunks:
        return []

    by_article: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for item in chunks:
        by_article[item.chunk.article_id].append(item)
    for items in by_article.values():
        items.sort(key=lambda x: x.score, reverse=True)

    def aggregate(items: list[RetrievedChunk]) -> float:
        top = [x.score for x in items[:2]]
        if not top:
            return 0.0
        return top[0] + (second_chunk_bonus * top[1] if len(top) > 1 else 0.0)

    sorted_articles = sorted(by_article.items(), key=lambda kv: -aggregate(kv[1]))

    out: list[RetrievedChunk] = []
    new_rank = 1
    for _, items in sorted_articles:
        for item in items:
            out.append(RetrievedChunk(chunk=item.chunk, score=item.score, rank=new_rank))
            new_rank += 1
            if len(out) >= top_k:
                return out
    return out


class LocalVectorRetriever:
    def __init__(
        self,
        storage: SQLiteStorage | None = None,
        embedder: EmbeddingModel | None = None,
        index_path: Path = VECTOR_INDEX_PATH,
        ids_path: Path = VECTOR_INDEX_IDS_PATH,
    ) -> None:
        self.storage = storage or SQLiteStorage()
        self.embedder = embedder or EmbeddingModel()
        self.index_path = Path(index_path)
        self.ids_path = Path(ids_path)

    def build_index(self) -> tuple[int, int]:
        chunks = self.storage.list_chunks()
        embeddings = self.embedder.encode_texts([chunk.embedding_text for chunk in chunks])
        matrix = np.asarray(embeddings, dtype=np.float32)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.index_path, matrix)
        self.ids_path.write_text(json.dumps([chunk.chunk_id for chunk in chunks]), encoding="utf-8")
        return len(chunks), matrix.shape[1] if len(chunks) else 0

    def _load_index(self) -> tuple[np.ndarray, list[str]]:
        if not self.index_path.exists() or not self.ids_path.exists():
            raise FileNotFoundError("Vector index files do not exist. Build the index first.")
        matrix = np.load(self.index_path)
        chunk_ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
        return matrix, chunk_ids

    def search(self, query: QueryBundle, top_k: int = RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
        matrix, chunk_ids = self._load_index()
        if matrix.size == 0 or not chunk_ids:
            return []

        query_vector = np.asarray(self.embedder.encode_query(query.retrieval_text()), dtype=np.float32)
        scores = matrix @ query_vector
        pool_size = min(top_k, scores.shape[0])
        top_indices = np.argsort(scores)[::-1][:pool_size]
        chunks_by_id = {chunk.chunk_id: chunk for chunk in self.storage.list_chunks_by_ids([chunk_ids[index] for index in top_indices])}

        results: list[RetrievedChunk] = []
        for rank, index in enumerate(top_indices, start=1):
            chunk_id = chunk_ids[index]
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            results.append(RetrievedChunk(chunk=chunk, score=float(scores[index]), rank=rank))
        return results

    def build_qa_context(self, query: QueryBundle, top_k: int = RETRIEVAL_TOP_K) -> QAContext:
        if ARTICLE_AGGREGATION:
            pool = self.search(query, top_k=top_k * ARTICLE_AGGREGATION_POOL_MULT)
            retrieved_chunks = article_aware_chunk_rerank(pool, top_k=top_k)
        else:
            retrieved_chunks = self.search(query, top_k=top_k)
        citations = citations_from_chunks(retrieved_chunks, self.storage)
        return QAContext(query=query, retrieved_chunks=retrieved_chunks, citations=citations)

    def build_timeline_context(self, query: QueryBundle, top_k: int = RETRIEVAL_TOP_K) -> TimelineContext:
        retrieved_chunks = self.search(query, top_k=max(top_k, TIMELINE_RECALL_K))
        related_articles, items = build_timeline_candidates(
            retrieved_chunks,
            self.storage,
            max_articles=TIMELINE_MAX_ARTICLES,
            max_per_bucket=TIMELINE_MAX_PER_BUCKET,
            bucket_granularity=TIMELINE_BUCKET_GRANULARITY,
        )
        return TimelineContext(query=query, related_articles=related_articles, items=items)


def articles_from_chunks(retrieved_chunks: list[RetrievedChunk], storage: SQLiteStorage) -> list[Article]:
    article_ids: list[str] = []
    seen: set[str] = set()
    for item in retrieved_chunks:
        if item.chunk.article_id in seen:
            continue
        seen.add(item.chunk.article_id)
        article_ids.append(item.chunk.article_id)
    articles = storage.list_articles_by_ids(article_ids)
    order = {article_id: idx for idx, article_id in enumerate(article_ids)}
    return sorted(articles, key=lambda article: order.get(article.article_id, 10**9))


def citations_from_chunks(retrieved_chunks: list[RetrievedChunk], storage: SQLiteStorage) -> list[Citation]:
    articles = articles_from_chunks(retrieved_chunks, storage)
    snippet_by_article: dict[str, str] = {}
    for item in retrieved_chunks:
        snippet_by_article.setdefault(item.chunk.article_id, item.chunk.text[:240])
    return [
        Citation(
            article_id=article.article_id,
            title=article.title,
            published_at=article.published_at,
            url=article.url,
            source=article.source,
            snippet=snippet_by_article.get(article.article_id, ""),
        )
        for article in articles
    ]


def timeline_items_from_articles(articles: list[Article]) -> list[TimelineItem]:
    ordered = sorted(articles, key=lambda article: (article.published_at, article.title))
    return [
        TimelineItem(
            article_id=article.article_id,
            published_at=article.published_at,
            title=article.title,
            url=article.url,
            source=article.source,
            summary=article.summary_text[:240],
        )
        for article in ordered
    ]


def build_timeline_candidates(
    retrieved_chunks: list[RetrievedChunk],
    storage: SQLiteStorage,
    max_articles: int = TIMELINE_MAX_ARTICLES,
    max_per_bucket: int = TIMELINE_MAX_PER_BUCKET,
    bucket_granularity: str = TIMELINE_BUCKET_GRANULARITY,
) -> tuple[list[Article], list[TimelineItem]]:
    if not retrieved_chunks:
        return [], []

    article_groups: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for item in retrieved_chunks:
        article_groups[item.chunk.article_id].append(item)

    articles = storage.list_articles_by_ids(list(article_groups))
    articles_by_id = {article.article_id: article for article in articles}

    ranked_articles: list[dict] = []
    for article_id, matches in article_groups.items():
        article = articles_by_id.get(article_id)
        if article is None:
            continue

        ordered_matches = sorted(matches, key=lambda item: item.score, reverse=True)
        top_scores = [item.score for item in ordered_matches[:2]]
        aggregate_score = top_scores[0]
        if len(top_scores) > 1:
            aggregate_score += 0.15 * top_scores[1]

        representative_text = ordered_matches[0].chunk.text
        ranked_articles.append(
            {
                "article": article,
                "score": aggregate_score,
                "representative_text": representative_text,
            }
        )

    ranked_articles.sort(
        key=lambda record: (
            -record["score"],
            record["article"].published_at,
            record["article"].title,
        )
    )

    bucket_counts: dict[str, int] = defaultdict(int)
    selected: list[dict] = []
    selected_ids: set[str] = set()

    for record in ranked_articles:
        bucket = timeline_bucket(record["article"].published_at, granularity=bucket_granularity)
        if bucket_counts[bucket] >= max_per_bucket:
            continue
        selected.append(record)
        selected_ids.add(record["article"].article_id)
        bucket_counts[bucket] += 1
        if len(selected) >= max_articles:
            break

    if len(selected) < min(max_articles, len(ranked_articles)):
        for record in ranked_articles:
            article_id = record["article"].article_id
            if article_id in selected_ids:
                continue
            selected.append(record)
            selected_ids.add(article_id)
            if len(selected) >= max_articles:
                break

    selected.sort(
        key=lambda record: (
            record["article"].published_at,
            -record["score"],
            record["article"].title,
        )
    )

    related_articles = [record["article"] for record in selected]
    items = [
        TimelineItem(
            article_id=record["article"].article_id,
            published_at=record["article"].published_at,
            title=record["article"].title,
            url=record["article"].url,
            source=record["article"].source,
            summary=timeline_summary(record["article"], record["representative_text"]),
        )
        for record in selected
    ]
    return related_articles, items


def timeline_bucket(published_at: str, granularity: str = TIMELINE_BUCKET_GRANULARITY) -> str:
    try:
        parsed = date.fromisoformat(published_at[:10])
    except ValueError:
        return published_at[:7] or "unknown"

    if granularity == "month":
        return f"{parsed.year:04d}-{parsed.month:02d}"

    iso_year, iso_week, _ = parsed.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def timeline_summary(article: Article, representative_text: str) -> str:
    description = " ".join(article.description.split()).strip()
    snippet = " ".join(representative_text.split()).strip()
    if description:
        return description[:240]
    return snippet[:240]


def build_index_command() -> None:
    retriever = LocalVectorRetriever()
    chunk_count, dimension = retriever.build_index()
    print(f"Built local vector index for {chunk_count} chunks with dimension {dimension}.")


def search_command(query: str, article_id: str = "", top_k: int = RETRIEVAL_TOP_K) -> None:
    storage = SQLiteStorage()
    current_article = storage.get_article(article_id) if article_id else None
    guardrail = guardrail_query(query, current_article=current_article)
    if not guardrail.should_retrieve:
        print("guardrail=blocked")
        print(f"reason={guardrail.reason}")
        print(f"user_message={guardrail.user_message}")
        return

    bundle = build_query_bundle(query, current_article=current_article)
    retriever = LocalVectorRetriever(storage=storage)
    context = retriever.build_qa_context(bundle, top_k=top_k)

    print(f"mode={bundle.mode}")
    if bundle.route_reason:
        print(f"reason={bundle.route_reason}")
    print("")
    for item in context.retrieved_chunks:
        print(f"[rank={item.rank} score={item.score:.4f}] {item.chunk.title}")
        print(f"article_id={item.chunk.article_id} chunk_index={item.chunk.chunk_index}")
        print(f"text={item.chunk.text[:260]}")
        print("")
    print("citations")
    for citation in context.citations:
        print(f"- {citation.title} | {citation.published_at} | {citation.url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local retrieval helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("build-index", help="Build the local chunk embedding index.")

    search_parser = subparsers.add_parser("search", help="Run a retrieval preview.")
    search_parser.add_argument("query")
    search_parser.add_argument("--article-id", default="")
    search_parser.add_argument("--top-k", type=int, default=RETRIEVAL_TOP_K)

    args = parser.parse_args()

    if args.command == "build-index":
        build_index_command()
        return

    if args.command == "search":
        search_command(args.query, article_id=args.article_id, top_k=args.top_k)


if __name__ == "__main__":
    main()
