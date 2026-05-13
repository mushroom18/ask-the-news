"use client";

import { useEffect, useRef, useState } from "react";
import { postQuery, type Article, type Citation } from "@/lib/api";

type Message =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; citations: Citation[] };

type ChatPanelProps = {
  currentArticle: Article | null;
};

const RETRIEVAL_TOP_K = 8;

function exampleQuestions(article: Article | null): string[] {
  if (!article) {
    return [
      "Summarize the most important development.",
      "What happened before this?",
    ];
  }
  const subject =
    article.title.length > 72 ? `${article.title.slice(0, 70)}…` : article.title;
  return [
    `Summarize the key development in ${subject}.`,
    "What happened before this?",
  ];
}

export function ChatPanel({ currentArticle }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Reset chat when the current article changes — fresh context, fresh history.
  useEffect(() => {
    setMessages([]);
    setInput("");
  }, [currentArticle?.article_id]);

  // Auto-scroll to bottom whenever a new message arrives.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, pending]);

  const suggestions = exampleQuestions(currentArticle);

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || pending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: trimmed }]);
    setPending(true);
    try {
      const response = await postQuery({
        question: trimmed,
        current_article_id: currentArticle?.article_id ?? "",
        top_k: RETRIEVAL_TOP_K,
      });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: response.message || "(no answer returned)",
          citations: response.citations ?? [],
        },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `Error: ${message}`, citations: [] },
      ]);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="flex h-160 flex-col gap-3 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto rounded-xl bg-gray-50 p-3 scrollbar-thin"
      >
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-gray-500">
            Ask a question about the current story.
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {pending ? (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-tl-md border border-gray-200 bg-white px-4 py-2 text-sm text-gray-500">
                  Thinking…
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Suggestion chips (inline text links) */}
      <div className="text-xs text-gray-600">
        <span className="mr-2 font-semibold text-gray-700">💡 Try:</span>
        {suggestions.map((q, i) => (
          <span key={i}>
            {i > 0 ? <span className="mx-1.5 text-gray-300">·</span> : null}
            <button
              type="button"
              onClick={() => setInput(q)}
              disabled={pending}
              className="cursor-pointer rounded px-1.5 py-0.5 text-blue-600 transition-colors hover:bg-blue-50 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
              {q}
            </button>
          </span>
        ))}
      </div>

      {/* Unified input + send button (single pill bar) */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 p-1 pl-3 transition-colors focus-within:border-blue-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this story or a broader topic…"
          disabled={pending}
          className="flex-1 bg-transparent px-1 py-1.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          aria-label="Send"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-lg font-bold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          ↑
        </button>
      </form>
    </section>
  );
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-md bg-blue-600 px-4 py-2 text-sm leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] space-y-2">
        <div className="whitespace-pre-wrap rounded-2xl rounded-tl-md border border-gray-200 bg-white px-4 py-3 text-sm leading-relaxed text-gray-900">
          {message.content}
        </div>
        {message.citations.length > 0 ? (
          <div className="space-y-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs">
            <div className="mb-1 font-semibold text-gray-700">Sources</div>
            <ul className="space-y-0.5">
              {message.citations.map((c, i) => (
                <li key={`${c.article_id}-${i}`} className="leading-relaxed">
                  <span className="mr-1 font-mono text-gray-400">[{i + 1}]</span>
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    {c.title}
                  </a>
                  <span className="ml-1 text-gray-500">· {c.published_at}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
