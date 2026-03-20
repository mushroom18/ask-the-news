from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Article:
    """Canonical article-level record used for UI, citations, and timeline nodes."""

    article_id: str
    title: str
    published_at: str
    authors: list[str] = field(default_factory=list)
    description: str = ""
    section: str = ""
    content: str = ""
    url: str = ""
    top_image: str = ""
    source: str = "BBC News"

    @property
    def summary_text(self) -> str:
        return self.description or self.content


@dataclass
class Chunk:
    """Retrieval unit used for embedding search and answer synthesis."""

    chunk_id: str
    article_id: str
    title: str
    published_at: str
    description: str
    section: str
    url: str
    chunk_index: int
    text: str
    embedding_text: str


@dataclass
class QueryBundle:
    """Expanded query object that keeps the user question tied to the current article."""

    user_query: str
    mode: str = "global"
    current_article_id: str = ""
    current_article_title: str = ""
    current_article_description: str = ""
    current_article_section: str = ""
    route_reason: str = ""

    def retrieval_text(self) -> str:
        if self.mode == "global":
            return self.user_query.strip()

        parts = [
            f"Current article title: {self.current_article_title}".strip(),
            f"Current article description: {self.current_article_description}".strip(),
            f"Current article section: {self.current_article_section}".strip(),
            f"User question: {self.user_query}".strip(),
        ]
        return "\n".join(part for part in parts if part and not part.endswith(": "))


@dataclass
class QueryRoute:
    mode: str
    reason: str = ""


@dataclass
class QueryGuardrailResult:
    should_retrieve: bool
    reason: str = ""
    user_message: str = ""


@dataclass
class RetrievedChunk:
    """Chunk plus retrieval metadata from hybrid/vector search."""

    chunk: Chunk
    score: float
    rank: int = 0


@dataclass
class Citation:
    """Article-level citation shown to the user after generation."""

    article_id: str
    title: str
    published_at: str
    url: str
    source: str
    snippet: str = ""


@dataclass
class TimelineItem:
    """A single event node rendered in the timeline UI."""

    article_id: str
    published_at: str
    title: str
    url: str
    source: str
    summary: str = ""


@dataclass
class QAContext:
    """Context assembled for answer generation."""

    query: QueryBundle
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


@dataclass
class TimelineContext:
    """Context assembled for timeline generation."""

    query: QueryBundle
    related_articles: list[Article] = field(default_factory=list)
    items: list[TimelineItem] = field(default_factory=list)
