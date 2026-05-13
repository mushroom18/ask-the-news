"use client";

type NewsCardProps = {
  section?: string;
  title: string;
  date: string;
  snippet?: string;
  active?: boolean;
  onClick?: () => void;
};

export function NewsCard({
  section,
  title,
  date,
  snippet,
  active = false,
  onClick,
}: NewsCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        flex w-60 shrink-0 flex-col gap-1.5 rounded-xl border bg-white p-4 text-left
        shadow-sm transition-all
        hover:-translate-y-0.5 hover:border-blue-500 hover:shadow-md
        ${active ? "border-blue-500 bg-blue-50" : "border-gray-200"}
      `}
    >
      <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600">
        {section || "News"}
      </span>
      <span className="line-clamp-3 text-sm font-semibold leading-snug text-gray-900">
        {title}
      </span>
      {snippet ? (
        <span className="line-clamp-2 text-xs leading-relaxed text-gray-600">
          {snippet}
        </span>
      ) : null}
      <span className="mt-auto pt-1 text-xs font-medium text-gray-500">{date}</span>
    </button>
  );
}
