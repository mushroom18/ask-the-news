import { AppShell } from "@/components/app-shell";
import { fetchFeatured } from "@/lib/api";

export default async function Home() {
  let articles: Awaited<ReturnType<typeof fetchFeatured>>["articles"] = [];
  let fetchError: string | null = null;

  try {
    const result = await fetchFeatured(24);
    articles = result.articles;
  } catch (error) {
    fetchError = error instanceof Error ? error.message : String(error);
  }

  if (fetchError) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
        <div className="w-full max-w-md rounded-2xl border border-red-200 bg-white p-8 shadow-sm">
          <h1 className="mb-1 text-2xl font-semibold text-gray-900">Ask the News</h1>
          <p className="mb-4 text-sm text-gray-500">Could not reach the backend.</p>
          <code className="block rounded bg-red-50 p-3 text-xs text-red-700">
            {fetchError}
          </code>
        </div>
      </main>
    );
  }

  return <AppShell articles={articles} />;
}
