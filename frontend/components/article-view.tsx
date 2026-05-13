"use client";

import { useMemo, useState } from "react";
import type { Article } from "@/lib/api";

type ArticleViewProps = {
  article: Article | null;
  loading?: boolean;
};

export function ArticleView({ article, loading = false }: ArticleViewProps) {
  const [expanded, setExpanded] = useState(false);

  const paragraphs = useMemo(
    () =>
      article?.content
        ? article.content.split("\n").map((p) => p.trim()).filter(Boolean)
        : [],
    [article?.content],
  );

  if (loading && !article) {
    return (
      <section className="flex h-160 items-center justify-center rounded-2xl border border-gray-200 bg-white p-8 text-sm text-gray-500 shadow-sm">
        Loading article…
      </section>
    );
  }

  if (!article) {
    return (
      <section className="flex h-160 items-center justify-center rounded-2xl border border-gray-200 bg-white p-8 text-sm text-gray-500 shadow-sm">
        Pick a story from the carousel above to start reading.
      </section>
    );
  }

  const visibleParagraphs = paragraphs.slice(0, 2);
  const hiddenParagraphs = paragraphs.slice(2);

  return (
    <article className="h-160 overflow-y-auto rounded-2xl border border-gray-200 bg-white px-8 py-7 shadow-sm scrollbar-thin">
      {article.top_image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="mb-5 block max-h-72 w-full rounded-xl object-cover"
          src={article.top_image}
          alt=""
        />
      ) : null}

      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-gray-500">
        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-blue-600">
          {article.section || "General"}
        </span>
        <span>{article.published_at}</span>
        {article.authors.length > 0 ? <span>By {article.authors.join(", ")}</span> : null}
        {article.source ? <span>· {article.source}</span> : null}
      </div>

      <h2 className="mb-4 text-3xl font-bold leading-tight tracking-tight text-gray-900">
        {article.title}
      </h2>

      {article.description ? (
        <p className="mb-5 text-[17px] font-medium leading-relaxed text-gray-800">
          {article.description}
        </p>
      ) : null}

      <div className="space-y-4 text-[15px] leading-relaxed text-gray-800">
        {visibleParagraphs.map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
        {hiddenParagraphs.length > 0 && expanded
          ? hiddenParagraphs.map((paragraph, i) => <p key={i + 2}>{paragraph}</p>)
          : null}
      </div>

      {hiddenParagraphs.length > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 text-sm font-semibold text-blue-600 hover:text-blue-700"
        >
          {expanded
            ? "Show less ↑"
            : `Continue reading (${hiddenParagraphs.length} more paragraph${
                hiddenParagraphs.length === 1 ? "" : "s"
              }) ↓`}
        </button>
      ) : null}

      {article.url ? (
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-6 inline-block text-sm font-semibold text-blue-600 hover:text-blue-700"
        >
          Read on {article.source || "source"} ↗
        </a>
      ) : null}
    </article>
  );
}
