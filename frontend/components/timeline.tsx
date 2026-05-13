"use client";

import type { TimelineItem } from "@/lib/api";
import { useHorizontalWheel } from "@/lib/use-horizontal-wheel";
import { NewsCard } from "./news-card";

type TimelineProps = {
  items: TimelineItem[];
  pending: boolean;
  hasArticle: boolean;
  onBuild: () => void;
  onSelect: (articleId: string) => void;
};

export function Timeline({
  items,
  pending,
  hasArticle,
  onBuild,
  onSelect,
}: TimelineProps) {
  return (
    <section className="mt-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">Timeline</h3>
          <p className="mt-0.5 text-xs text-gray-500">
            Related coverage along a horizontal time axis. Click any card to switch the current story.
          </p>
        </div>
        <button
          type="button"
          onClick={onBuild}
          disabled={!hasArticle || pending}
          className="shrink-0 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? "Building…" : "Build timeline"}
        </button>
      </div>

      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-6 py-16 text-center text-sm text-gray-500">
          {pending
            ? "Building timeline…"
            : "Click “Build timeline” to surface related coverage."}
        </div>
      ) : (
        <TimelineTrack items={items} onSelect={onSelect} />
      )}
    </section>
  );
}

function TimelineTrack({
  items,
  onSelect,
}: {
  items: TimelineItem[];
  onSelect: (id: string) => void;
}) {
  const scrollRef = useHorizontalWheel<HTMLDivElement>();
  // The track scrolls horizontally; the axis line is inside the scrolling
  // content so it travels with the cards instead of staying anchored to the
  // viewport edge.
  return (
    <div ref={scrollRef} className="overflow-x-auto py-2 scrollbar-thin">
      <div className="relative flex min-h-90 w-fit items-stretch">
        <div
          className="pointer-events-none absolute inset-x-4 top-1/2 h-px -translate-y-1/2 bg-gray-300"
          aria-hidden
        />
        {items.slice(0, 10).map((item, i) => (
          <TimelineColumn
            key={`${item.article_id}-${i}`}
            item={item}
            position={i % 2 === 0 ? "top" : "bottom"}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function TimelineColumn({
  item,
  position,
  onSelect,
}: {
  item: TimelineItem;
  position: "top" | "bottom";
  onSelect: (id: string) => void;
}) {
  const card = (
    <NewsCard
      section="Timeline"
      title={item.title}
      date={item.published_at}
      snippet={item.summary}
      onClick={() => onSelect(item.article_id)}
    />
  );

  return (
    <div className="relative grid w-60 shrink-0 grid-rows-[1fr_auto_auto_1fr] gap-1 px-2">
      <div className="flex items-end justify-center pb-3">
        {position === "top" ? card : null}
      </div>
      <div className="relative z-10 flex justify-center">
        <div className="h-3.5 w-3.5 rounded-full border-[3px] border-blue-600 bg-white" />
      </div>
      <div className="text-center text-xs font-semibold text-gray-500">
        {item.published_at}
      </div>
      <div className="flex items-start justify-center pt-3">
        {position === "bottom" ? card : null}
      </div>
    </div>
  );
}
