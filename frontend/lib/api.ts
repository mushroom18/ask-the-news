export type Article = {
  article_id: string;
  title: string;
  published_at: string;
  authors: string[];
  description: string;
  section: string;
  content: string;
  url: string;
  top_image: string;
  source: string;
};

export type Citation = {
  article_id: string;
  title: string;
  published_at: string;
  url: string;
  source: string;
  snippet: string;
};

export type TimelineItem = {
  article_id: string;
  published_at: string;
  title: string;
  url: string;
  source: string;
  summary: string;
};

export type QueryResponse = {
  ok: boolean;
  blocked?: boolean;
  message: string;
  query_mode: string;
  route_reason?: string;
  citations: Citation[];
};

export type TimelineResponse = {
  ok: boolean;
  message: string;
  query_mode: string;
  route_reason?: string;
  items: TimelineItem[];
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

if (!API_BASE_URL) {
  // Surfaced loudly in dev so misconfig is obvious.
  console.warn("NEXT_PUBLIC_API_BASE_URL is not set");
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`${url} returned HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function fetchFeatured(limit = 24): Promise<{ articles: Article[] }> {
  return jsonFetch(`/featured?limit=${limit}`, { cache: "no-store" });
}

export function fetchArticle(articleId: string): Promise<{ article: Article | null }> {
  return jsonFetch(`/article/${encodeURIComponent(articleId)}`, { cache: "no-store" });
}

export function postQuery(payload: {
  question: string;
  current_article_id?: string;
  top_k?: number;
}): Promise<QueryResponse> {
  return jsonFetch(`/query`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function postTimeline(payload: {
  question: string;
  current_article_id?: string;
}): Promise<TimelineResponse> {
  return jsonFetch(`/timeline`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
