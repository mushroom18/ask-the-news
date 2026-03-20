from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from datasets import load_dataset

from ask_the_news.config import CHUNK_MAX_WORDS, CHUNK_MIN_WORDS, CHUNK_OVERLAP_WORDS, CHUNK_PREVIEW_LIMIT, CHUNK_SPLIT_THRESHOLD, CHUNK_TARGET_WORDS, DATA_PATH, EMBEDDING_PREVIEW_CHARS, HF_DATASET_REPO, HF_DATASET_SUBSETS, MAX_ARTICLES
from ask_the_news.models import Article, Chunk
from ask_the_news.storage import SQLiteStorage


BBC_NOISE_PATTERNS = [
    r"^\s*Listen to the best of BBC [A-Za-z\s]+ on Sounds.*$",
    r"^\s*Follow BBC [A-Za-z\s]+ on Facebook.*$",
    r"^\s*Do you have a story BBC .* should cover\?\s*$",
    r"^\s*Listen to highlights from .* on BBC Sounds.*$",
]

BBC_INLINE_NOISE_PATTERNS = [
    r"[•·]\s*None",
    r"Slide\s+\d+\s+of\s+\d+",
]


def article_id_from_link(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]


def clean_title(title: str) -> str:
    cleaned = " ".join(title.split()).strip()
    cleaned = re.sub(r"\s*-\s*BBC\s+(News|Sport)\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def load_articles(path: Path = DATA_PATH) -> list[Article]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        raw_articles = json.load(handle)
    return [Article(**item) for item in raw_articles]


def save_articles(articles: list[Article], path: Path = DATA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump([article.__dict__ for article in articles], handle, ensure_ascii=False, indent=2)


def load_hf_articles(
    repo_id: str = HF_DATASET_REPO,
    subsets: list[str] | None = None,
    limit: int = MAX_ARTICLES,
) -> list[Article]:
    selected_subsets = subsets or HF_DATASET_SUBSETS
    if not selected_subsets:
        raise ValueError("HF_DATASET_SUBSETS must be set before loading the Hugging Face dataset.")

    articles: list[Article] = []
    seen_links: set[str] = set()
    subset_count = len(selected_subsets)
    base_quota = max(1, limit // subset_count)
    remainder = max(0, limit % subset_count)

    for index, subset in enumerate(selected_subsets):
        dataset = load_dataset(repo_id, subset, split="train", streaming=True)
        subset_quota = base_quota + (1 if index < remainder else 0)
        subset_articles = 0

        for record in dataset:
            link = str(record.get("link") or "").strip()
            if not link or link in seen_links:
                continue

            article = Article(
                article_id=article_id_from_link(link),
                title=clean_title(str(record.get("title") or "")),
                published_at=str(record.get("published_date") or "").strip()[:10],
                description=str(record.get("description") or "").strip(),
                section=str(record.get("section") or "").strip(),
                content=str(record.get("content") or "").strip(),
                url=link,
                top_image=str(record.get("top_image") or "").strip(),
            )
            if not article.title or not article.content:
                continue

            seen_links.add(link)
            articles.append(article)
            subset_articles += 1

            if subset_articles >= subset_quota or len(articles) >= limit:
                break

        if len(articles) >= limit:
            break

    return articles


def split_paragraphs(text: str) -> list[str]:
    cleaned_text = text
    for pattern in BBC_INLINE_NOISE_PATTERNS:
        cleaned_text = re.sub(pattern, " ", cleaned_text, flags=re.IGNORECASE)

    paragraphs = []
    for part in re.split(r"\n\s*\n+", cleaned_text):
        cleaned = " ".join(part.split())
        if not cleaned:
            continue
        if any(re.match(pattern, cleaned, flags=re.IGNORECASE) for pattern in BBC_NOISE_PATTERNS):
            continue
        paragraphs.append(cleaned)
    if paragraphs:
        return paragraphs
    normalized = " ".join(cleaned_text.split())
    if normalized and not any(re.match(pattern, normalized, flags=re.IGNORECASE) for pattern in BBC_NOISE_PATTERNS):
        return [normalized]
    return []


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [" ".join(sentence.split()) for sentence in sentences if sentence.strip()]


def merge_short_paragraphs(paragraphs: list[str], min_words: int = CHUNK_MIN_WORDS) -> list[str]:
    if not paragraphs:
        return []

    merged: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        candidate = f"{buffer} {paragraph}".strip() if buffer else paragraph
        if len(candidate.split()) < min_words:
            buffer = candidate
            continue

        if buffer:
            merged.append(candidate)
            buffer = ""
        else:
            merged.append(paragraph)

    if buffer:
        if merged:
            merged[-1] = f"{merged[-1]} {buffer}".strip()
        else:
            merged.append(buffer)

    return merged


def split_long_paragraph(paragraph: str, target_words: int = CHUNK_TARGET_WORDS, max_words: int = CHUNK_MAX_WORDS) -> list[str]:
    if len(paragraph.split()) <= max_words:
        return [paragraph]

    sentences = split_sentences(paragraph)
    if len(sentences) <= 1:
        words = paragraph.split()
        pieces: list[str] = []
        start = 0
        while start < len(words):
            end = min(start + target_words, len(words))
            pieces.append(" ".join(words[start:end]).strip())
            start = end
        return pieces

    pieces: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current and current_words + sentence_words > max_words:
            pieces.append(" ".join(current).strip())
            current = [sentence]
            current_words = sentence_words
            continue

        current.append(sentence)
        current_words += sentence_words

        if current_words >= target_words:
            pieces.append(" ".join(current).strip())
            current = []
            current_words = 0

    if current:
        trailing_text = " ".join(current).strip()
        if pieces and len(trailing_text.split()) < CHUNK_MIN_WORDS:
            pieces[-1] = f"{pieces[-1]} {trailing_text}".strip()
        else:
            pieces.append(trailing_text)

    return pieces


def apply_sentence_overlap(chunks: list[str], overlap_words: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    # TODO: cap overlap so the merged chunk does not exceed CHUNK_MAX_WORDS.
    # Current behavior may inflate some chunks after overlap is applied.
    if overlap_words <= 0 or len(chunks) <= 1:
        return chunks

    overlapped: list[str] = []
    previous_sentences: list[str] = []

    for index, chunk in enumerate(chunks):
        sentences = split_sentences(chunk)
        if index == 0 or not previous_sentences:
            overlapped.append(chunk)
        else:
            carry: list[str] = []
            carry_words = 0
            for sentence in reversed(previous_sentences):
                sentence_words = len(sentence.split())
                if carry and carry_words + sentence_words > overlap_words:
                    break
                carry.insert(0, sentence)
                carry_words += sentence_words
                if carry_words >= overlap_words:
                    break
            merged = " ".join(carry + sentences).strip()
            overlapped.append(merged)
        previous_sentences = sentences

    return overlapped


def paragraph_first_chunks(
    text: str,
    target_words: int = CHUNK_TARGET_WORDS,
    min_words: int = CHUNK_MIN_WORDS,
    split_threshold: int = CHUNK_SPLIT_THRESHOLD,
    max_words: int = CHUNK_MAX_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[str]:
    paragraphs = split_paragraphs(text)
    merged = merge_short_paragraphs(paragraphs, min_words=min_words)

    chunks: list[str] = []
    for paragraph in merged:
        paragraph_words = len(paragraph.split())
        if paragraph_words <= split_threshold:
            chunks.append(paragraph)
            continue
        chunks.extend(split_long_paragraph(paragraph, target_words=target_words, max_words=max_words))

    normalized_chunks = [" ".join(chunk.split()).strip() for chunk in chunks if chunk.strip()]
    normalized_chunks = apply_sentence_overlap(normalized_chunks, overlap_words=overlap_words)
    return normalized_chunks


def normalize_embedding_value(value: str) -> str:
    return " ".join(value.split()).strip()


def build_embedding_text(article: Article, chunk_text: str) -> str:
    fields: list[tuple[str, str]] = [
        ("Title", article.title),
        ("Section", article.section),
        ("Published date", article.published_at),
        ("Description", article.description),
        ("Chunk", chunk_text),
    ]
    lines = []
    for label, value in fields:
        normalized = normalize_embedding_value(value)
        if not normalized:
            continue
        lines.append(f"{label}: {normalized}")
    return "\n".join(lines)


def build_chunks_for_article(
    article: Article,
    target_words: int = CHUNK_TARGET_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[Chunk]:
    chunk_texts = paragraph_first_chunks(
        article.content,
        target_words=target_words,
        overlap_words=overlap_words,
    )
    if not chunk_texts:
        return []

    chunks: list[Chunk] = []
    for chunk_index, chunk_text in enumerate(chunk_texts):
        chunks.append(
            Chunk(
                chunk_id=f"{article.article_id}-chunk-{chunk_index}",
                article_id=article.article_id,
                title=article.title,
                published_at=article.published_at,
                description=article.description,
                section=article.section,
                url=article.url,
                chunk_index=chunk_index,
                text=chunk_text,
                embedding_text=build_embedding_text(article, chunk_text),
            )
        )

    return chunks


def build_chunks(articles: list[Article]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for article in articles:
        chunks.extend(build_chunks_for_article(article))
    return chunks


def import_hf_sample(
    repo_id: str = HF_DATASET_REPO,
    subsets: list[str] | None = None,
    limit: int = MAX_ARTICLES,
    path: Path = DATA_PATH,
) -> list[Article]:
    articles = load_hf_articles(repo_id=repo_id, subsets=subsets, limit=limit)
    save_articles(articles, path=path)
    return articles


def sync_sample_to_sqlite() -> tuple[int, int]:
    articles = load_articles()
    chunks = build_chunks(articles)
    storage = SQLiteStorage()
    storage.sync_articles_and_chunks(articles, chunks)
    return len(articles), len(chunks)


def chunk_preview_report(
    articles: list[Article],
    preview_limit: int = CHUNK_PREVIEW_LIMIT,
) -> str:
    if not articles:
        return "No articles available for chunk preview."

    lines: list[str] = []
    for article in articles[:preview_limit]:
        chunks = build_chunks_for_article(article)
        lines.append(f"Article: {article.title}")
        lines.append(f"Published: {article.published_at}")
        lines.append(f"Section: {article.section or 'Unknown'}")
        lines.append(f"Chunks: {len(chunks)}")
        for chunk in chunks[:2]:
            word_count = len(chunk.text.split())
            embedding_preview = chunk.embedding_text[:EMBEDDING_PREVIEW_CHARS].replace("\n", " | ")
            lines.append(f"  - chunk_index={chunk.chunk_index} words={word_count}")
            lines.append(f"    text={chunk.text[:220]}")
            lines.append(f"    embedding_text={embedding_preview}")
        lines.append("")
    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a small BBC sample and inspect chunking.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-sample", help="Import a small sample from the Hugging Face BBC dataset.")
    import_parser.add_argument("--limit", type=int, default=MAX_ARTICLES)

    preview_parser = subparsers.add_parser("preview-chunks", help="Preview paragraph-aware chunking on the imported sample.")
    preview_parser.add_argument("--limit", type=int, default=CHUNK_PREVIEW_LIMIT)

    sqlite_parser = subparsers.add_parser("sync-sqlite", help="Write the current sample articles and chunks into SQLite.")
    _ = sqlite_parser

    args = parser.parse_args()

    if args.command == "import-sample":
        articles = import_hf_sample(limit=args.limit)
        print(f"Imported {len(articles)} articles into {DATA_PATH}")
        return

    if args.command == "preview-chunks":
        articles = load_articles()
        print(chunk_preview_report(articles, preview_limit=args.limit))
        return

    if args.command == "sync-sqlite":
        article_count, chunk_count = sync_sample_to_sqlite()
        print(f"Synced {article_count} articles and {chunk_count} chunks into SQLite.")


if __name__ == "__main__":
    main()
