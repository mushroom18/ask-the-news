"use client";

import type { Article } from "@/lib/api";
import { useHorizontalWheel } from "@/lib/use-horizontal-wheel";
import { NewsCard } from "./news-card";

type CarouselProps = {
  articles: Article[];
  activeId: string;
  onSelect: (id: string) => void;
};

export function Carousel({ articles, activeId, onSelect }: CarouselProps) {
  const scrollRef = useHorizontalWheel<HTMLDivElement>();

  if (articles.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
        No featured stories yet.
      </div>
    );
  }
  return (
    <div
      ref={scrollRef}
      className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-3 pt-1 -mx-1 px-1 scrollbar-thin"
    >
      {articles.map((article) => (
        <div key={article.article_id} className="snap-start">
          <NewsCard
            section={article.section || "News"}
            title={article.title}
            date={article.published_at}
            active={article.article_id === activeId}
            onClick={() => onSelect(article.article_id)}
          />
        </div>
      ))}
    </div>
  );
}
