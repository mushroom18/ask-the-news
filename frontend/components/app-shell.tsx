"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchArticle,
  postTimeline,
  type Article,
  type TimelineItem,
} from "@/lib/api";
import { ArticleView } from "./article-view";
import { Carousel } from "./carousel";
import { ChatPanel } from "./chat-panel";
import { Timeline } from "./timeline";

type AppShellProps = {
  articles: Article[];
};

export function AppShell({ articles }: AppShellProps) {
  const [articlesById, setArticlesById] = useState<Map<string, Article>>(
    () => new Map(articles.map((a) => [a.article_id, a])),
  );
  const [selectedId, setSelectedId] = useState<string>(
    articles[0]?.article_id ?? "",
  );
  const [articleFetching, setArticleFetching] = useState(false);

  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);
  const [timelinePending, setTimelinePending] = useState(false);

  // Whenever the user switches to a different article, the timeline that was
  // built for the *previous* article is no longer relevant — clear it.
  useEffect(() => {
    setTimelineItems([]);
  }, [selectedId]);

  const currentArticle = useMemo(
    () => articlesById.get(selectedId) ?? null,
    [articlesById, selectedId],
  );

  const selectArticle = useCallback(
    async (id: string) => {
      if (!id) return;
      setSelectedId(id);
      if (articlesById.has(id)) return;
      setArticleFetching(true);
      try {
        const { article } = await fetchArticle(id);
        if (article) {
          setArticlesById((prev) => {
            const next = new Map(prev);
            next.set(id, article);
            return next;
          });
        }
      } catch (err) {
        console.error("Failed to load article", id, err);
      } finally {
        setArticleFetching(false);
      }
    },
    [articlesById],
  );

  const buildTimeline = useCallback(async () => {
    if (!currentArticle || timelinePending) return;
    setTimelinePending(true);
    try {
      const response = await postTimeline({
        question: "",
        current_article_id: currentArticle.article_id,
      });
      if (response.ok) {
        setTimelineItems(response.items ?? []);
      } else {
        setTimelineItems([]);
        console.warn("Timeline build failed:", response.message);
      }
    } catch (err) {
      console.error("Timeline request errored", err);
      setTimelineItems([]);
    } finally {
      setTimelinePending(false);
    }
  }, [currentArticle, timelinePending]);

  return (
    <main className="mx-auto max-w-7xl px-6 pb-16 pt-6">
      <header className="mb-5 border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          Ask the News
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Read a featured BBC story, then ask about it or surface a timeline of
          related coverage.
        </p>
      </header>

      <Carousel
        articles={articles}
        activeId={selectedId}
        onSelect={selectArticle}
      />

      <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[3fr_2fr]">
        <ArticleView article={currentArticle} loading={articleFetching} />
        <ChatPanel currentArticle={currentArticle} />
      </div>

      <Timeline
        items={timelineItems}
        pending={timelinePending}
        hasArticle={!!currentArticle}
        onBuild={buildTimeline}
        onSelect={selectArticle}
      />
    </main>
  );
}
