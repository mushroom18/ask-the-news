from __future__ import annotations

import inspect
from html import escape
from textwrap import shorten

import gradio as gr
import httpx

from ask_the_news.config import API_BASE_URL, RETRIEVAL_TOP_K
from ask_the_news.models import Article, Citation, TimelineItem
from ask_the_news.service import NewsService


LOCAL_SERVICE = NewsService()

EMPTY_CHAT: list[dict[str, str]] = []
EMPTY_SOURCES = (
    "<div class='sources-empty'>Ask a question to surface relevant articles.</div>"
)
EMPTY_TIMELINE = (
    "<div class='timeline-empty'>Click <b>Build timeline</b> above to surface related"
    " coverage on a horizontal time axis.</div>"
)


HEAD_HTML = """
<script>
window.atnSetArticleId = function(id) {
  const root = document.querySelector('#selected-article-id');
  if (!root) return;
  const el = root.querySelector('textarea, input');
  if (!el) return;
  const proto = el.tagName === 'TEXTAREA'
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  setter.call(el, id);
  el.dispatchEvent(new Event('input', { bubbles: true }));
};
</script>
"""


UI_CSS = """
:root {
  --bg: #f9fafb;
  --surface: #ffffff;
  --border: #e5e7eb;
  --border-strong: #d1d5db;
  --text: #111827;
  --muted: #6b7280;
  --subtle: #4b5563;
  --accent: #2563eb;
  --accent-soft: #eff6ff;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(17,24,39,0.06);
}

.gradio-container {
  background: var(--bg) !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, "Helvetica Neue", Arial, system-ui, sans-serif !important;
  color: var(--text);
  max-width: 1320px !important;
}

.ath-header {
  padding: 28px 4px 16px;
  border-bottom: 1px solid var(--border);
  margin: 0 0 20px;
}

.ath-header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}

.ath-header p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}

/* ------------- Shared news card (carousel + timeline) ------------- */
.news-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 6px;
  user-select: none;
}
.news-card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.news-card.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.news-card .news-card-section {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
}
.news-card .news-card-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-card .news-card-snippet {
  font-size: 12px;
  line-height: 1.5;
  color: var(--subtle);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-card .news-card-date {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
  margin-top: auto;
  padding-top: 4px;
}

/* ------------- Featured carousel ------------- */
.carousel {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 4px 4px 16px;
  scroll-snap-type: x mandatory;
  scrollbar-width: thin;
}
.carousel::-webkit-scrollbar { height: 8px; }
.carousel::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 4px;
}
.carousel .news-card {
  flex: 0 0 240px;
  scroll-snap-align: start;
}
.carousel-empty {
  color: var(--muted);
  padding: 20px;
  text-align: center;
}

/* ------------- Article view (main left) ------------- */
.article-view {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 28px 32px;
  box-shadow: var(--shadow-sm);
}
.article-hero-img {
  width: 100%;
  border-radius: 12px;
  margin-bottom: 20px;
  display: block;
  max-height: 360px;
  object-fit: cover;
}
.article-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.article-section-tag {
  background: var(--accent-soft);
  color: var(--accent);
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 700;
  text-transform: uppercase;
  font-size: 10.5px;
  letter-spacing: 0.06em;
}
.article-view h2 {
  margin: 0 0 16px;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--text);
}
.article-description {
  font-size: 17px;
  line-height: 1.6;
  color: #1f2937;
  margin: 0 0 20px;
  font-weight: 500;
}
.article-content {
  font-size: 15px;
  line-height: 1.75;
  color: #374151;
}
.article-content p {
  margin: 0 0 16px;
}
.article-source-link {
  display: inline-block;
  margin-top: 24px;
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
  font-size: 14px;
}
.article-source-link:hover {
  text-decoration: underline;
}
.article-empty {
  color: var(--muted);
  text-align: center;
  padding: 60px 20px;
  font-size: 14px;
}

/* ------------- Chat column ------------- */
.chat-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.chips-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chips-row button {
  background: var(--surface) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 999px !important;
  padding: 6px 14px !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  white-space: nowrap !important;
}
.chips-row button:hover {
  border-color: var(--accent) !important;
  color: var(--accent) !important;
}

/* ------------- Timeline (horizontal) ------------- */
.timeline-section {
  margin: 32px 0 0;
}
.timeline-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 0 4px;
}
.timeline-section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}
.timeline-section-header .timeline-section-hint {
  font-size: 12px;
  color: var(--muted);
}
.timeline-horizontal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px 8px;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.timeline-track {
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  min-height: 380px;
  padding: 8px 24px;
  scrollbar-width: thin;
}
.timeline-track::-webkit-scrollbar { height: 8px; }
.timeline-track::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 4px;
}
.timeline-item {
  position: relative;
  display: grid;
  grid-template-rows: 1fr auto auto 1fr;
  width: 240px;
  flex-shrink: 0;
  margin: 0 10px;
}
.timeline-item::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  margin-top: -7px;
  height: 2px;
  background: var(--border);
  z-index: 0;
}
.timeline-cell {
  display: flex;
  z-index: 1;
}
.timeline-cell.top {
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 14px;
}
.timeline-cell.bottom {
  align-items: flex-start;
  justify-content: center;
  padding-top: 14px;
}
.timeline-cell .news-card {
  flex: none;
  width: 100%;
  min-height: 120px;
}
.timeline-marker {
  width: 14px;
  height: 14px;
  background: var(--surface);
  border: 3px solid var(--accent);
  border-radius: 50%;
  margin: 0 auto;
  z-index: 2;
  position: relative;
}
.timeline-date {
  text-align: center;
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
  margin-top: 6px;
}
.timeline-empty {
  text-align: center;
  color: var(--muted);
  padding: 80px 20px;
  font-size: 14px;
}

/* ------------- Sources (footer accordion) ------------- */
.sources-section {
  margin-top: 24px;
}
.sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 4px;
}
.source-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.source-card .source-index {
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.08em;
}
.source-card .source-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}
.source-card .source-title a {
  color: var(--text);
  text-decoration: none;
}
.source-card .source-title a:hover {
  color: var(--accent);
  text-decoration: underline;
}
.source-card .source-meta {
  font-size: 12px;
  color: var(--muted);
}
.source-card .source-snippet {
  font-size: 12.5px;
  color: var(--subtle);
  line-height: 1.55;
}
.sources-empty {
  color: var(--muted);
  padding: 16px;
  text-align: center;
  font-size: 13px;
}
"""


def article_from_dict(payload: dict) -> Article:
    return Article(**payload)


def citation_from_dict(payload: dict) -> Citation:
    return Citation(**payload)


def timeline_item_from_dict(payload: dict) -> TimelineItem:
    return TimelineItem(**payload)


def request_api(method: str, path: str, payload: dict | None = None) -> dict | None:
    if not API_BASE_URL:
        return None
    url = f"{API_BASE_URL.rstrip('/')}{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, url, json=payload)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


def load_ui_articles(limit: int = 24) -> list[Article]:
    response = request_api("GET", f"/featured?limit={limit}")
    if response and response.get("articles"):
        return [article_from_dict(item) for item in response["articles"]]
    return LOCAL_SERVICE.featured_articles(limit=limit)


def get_article(article_id: str) -> Article | None:
    if not article_id:
        return None
    response = request_api("GET", f"/article/{article_id}")
    if response and response.get("article"):
        return article_from_dict(response["article"])
    return LOCAL_SERVICE.get_article(article_id)


def initial_article_id(articles: list[Article]) -> str:
    return articles[0].article_id if articles else ""


def example_questions(article: Article | None) -> list[str]:
    return LOCAL_SERVICE.example_questions(article)


def suggestion_updates(questions: list[str]) -> list[dict]:
    return [gr.update(value=question) for question in questions]


def render_news_card(
    article_id: str,
    title: str,
    date: str,
    section: str = "",
    snippet: str = "",
    active: bool = False,
) -> str:
    section_html = escape(section.upper()) if section else "STORY"
    title_html = escape(shorten(title, width=110, placeholder="..."))
    snippet_html = escape(shorten(snippet, width=120, placeholder="...")) if snippet else ""
    snippet_block = f"<div class='news-card-snippet'>{snippet_html}</div>" if snippet_html else ""
    active_class = " active" if active else ""
    aid = escape(article_id)
    return (
        f"<article class='news-card{active_class}' "
        f"onclick=\"atnSetArticleId('{aid}')\" "
        f"data-article-id='{aid}'>"
        f"<div class='news-card-section'>{section_html}</div>"
        f"<div class='news-card-title'>{title_html}</div>"
        f"{snippet_block}"
        f"<div class='news-card-date'>{escape(date)}</div>"
        f"</article>"
    )


def render_carousel(articles: list[Article], active_id: str = "") -> str:
    if not articles:
        return "<div class='carousel-empty'>No featured stories yet.</div>"
    cards = [
        render_news_card(
            article_id=article.article_id,
            title=article.title,
            date=article.published_at,
            section=article.section or "News",
            active=article.article_id == active_id,
        )
        for article in articles
    ]
    return f"<div class='carousel'>{''.join(cards)}</div>"


def render_article_view(article: Article | None) -> str:
    if article is None:
        return (
            "<div class='article-view'>"
            "<div class='article-empty'>"
            "Pick a story from the carousel above to start reading."
            "</div></div>"
        )

    section = escape((article.section or "General").upper())
    title = escape(article.title)
    description = escape(article.description) if article.description else ""
    published = escape(article.published_at)
    authors = escape(", ".join(article.authors)) if article.authors else ""
    source = escape(article.source or "")
    url = escape(article.url)
    top_image = escape(article.top_image) if article.top_image else ""

    content_html = ""
    if article.content:
        paragraphs = [paragraph.strip() for paragraph in article.content.split("\n") if paragraph.strip()]
        content_html = "\n".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)

    image_html = (
        f"<img class='article-hero-img' src='{top_image}' alt=''>" if top_image else ""
    )
    description_html = (
        f"<p class='article-description'>{description}</p>" if description else ""
    )

    meta_parts = [
        f"<span class='article-section-tag'>{section}</span>",
        f"<span>{published}</span>",
    ]
    if authors:
        meta_parts.append(f"<span>By {authors}</span>")
    if source:
        meta_parts.append(f"<span>· {source}</span>")
    meta_html = "".join(meta_parts)

    source_label = escape(article.source or "source")
    return (
        f"<article class='article-view'>"
        f"{image_html}"
        f"<div class='article-meta'>{meta_html}</div>"
        f"<h2>{title}</h2>"
        f"{description_html}"
        f"<div class='article-content'>{content_html}</div>"
        f"<a class='article-source-link' href='{url}' target='_blank' rel='noopener'>"
        f"Read on {source_label} ↗</a>"
        f"</article>"
    )


def render_sources(citations: list[Citation]) -> str:
    if not citations:
        return EMPTY_SOURCES
    cards = []
    for index, citation in enumerate(citations, start=1):
        title = escape(citation.title.replace("\n", " ").strip())
        snippet = escape(
            shorten(citation.snippet.replace("\n", " ").strip(), width=200, placeholder="...")
        )
        url = escape(citation.url)
        date = escape(citation.published_at)
        source = escape(citation.source or "")
        cards.append(
            "<div class='source-card'>"
            f"<div class='source-index'>SOURCE {index}</div>"
            f"<div class='source-title'><a href='{url}' target='_blank' rel='noopener'>{title}</a></div>"
            f"<div class='source-meta'>{date}{' · ' + source if source else ''}</div>"
            f"<div class='source-snippet'>{snippet}</div>"
            "</div>"
        )
    return f"<div class='sources-grid'>{''.join(cards)}</div>"


def render_timeline(items: list[TimelineItem]) -> str:
    if not items:
        return EMPTY_TIMELINE

    cells = []
    for index, item in enumerate(items[:10]):
        position = "top" if index % 2 == 0 else "bottom"
        card = render_news_card(
            article_id=item.article_id,
            title=item.title,
            date=item.published_at,
            section="Timeline",
            snippet=item.summary,
        )
        if position == "top":
            inner = (
                f"<div class='timeline-cell top'>{card}</div>"
                f"<div class='timeline-marker'></div>"
                f"<div class='timeline-date'>{escape(item.published_at)}</div>"
                f"<div class='timeline-cell bottom'></div>"
            )
        else:
            inner = (
                f"<div class='timeline-cell top'></div>"
                f"<div class='timeline-marker'></div>"
                f"<div class='timeline-date'>{escape(item.published_at)}</div>"
                f"<div class='timeline-cell bottom'>{card}</div>"
            )
        cells.append(f"<div class='timeline-item'>{inner}</div>")

    return f"<div class='timeline-horizontal'><div class='timeline-track'>{''.join(cells)}</div></div>"


def use_example(questions: list[str], index: int) -> str:
    if 0 <= index < len(questions):
        return questions[index]
    return ""


def ask_question(user_query, history, current_article_id):
    history = history or []
    if not user_query.strip():
        return history, "", EMPTY_SOURCES

    response = request_api(
        "POST",
        "/query",
        {"question": user_query, "current_article_id": current_article_id, "top_k": RETRIEVAL_TOP_K},
    )
    if response is None:
        response = LOCAL_SERVICE.answer(user_query, current_article_id=current_article_id, top_k=RETRIEVAL_TOP_K)

    if not response.get("ok"):
        user_message = response.get("message", "The backend could not answer this question.")
        return history + [
            {"role": "user", "content": user_query},
            {"role": "assistant", "content": user_message},
        ], "", EMPTY_SOURCES

    answer = response.get("message", "")
    citations = [citation_from_dict(item) for item in response.get("citations", [])]
    updated_history = history + [
        {"role": "user", "content": user_query},
        {"role": "assistant", "content": answer},
    ]
    return updated_history, "", render_sources(citations)


def build_timeline(current_article_id: str, user_query: str) -> str:
    response = request_api(
        "POST",
        "/timeline",
        {"question": user_query, "current_article_id": current_article_id},
    )
    if response is None:
        response = LOCAL_SERVICE.timeline(user_query, current_article_id=current_article_id)
    if not response.get("ok"):
        return f"<div class='timeline-empty'>{escape(response.get('message', 'Timeline generation failed.'))}</div>"
    items = [timeline_item_from_dict(item) for item in response.get("items", [])]
    return render_timeline(items)


def build_demo() -> gr.Blocks:
    articles = load_ui_articles()
    selected_article_id = initial_article_id(articles)
    selected_article = get_article(selected_article_id)
    questions = example_questions(selected_article)

    with gr.Blocks(title="Ask the News", css=UI_CSS, head=HEAD_HTML, theme=gr.themes.Base()) as demo:
        gr.HTML(
            "<header class='ath-header'>"
            "<h1>Ask the News</h1>"
            "<p>Read a featured story, then ask about it or surface a timeline of related coverage.</p>"
            "</header>"
        )

        selected_article_textbox = gr.Textbox(
            value=selected_article_id,
            visible=False,
            elem_id="selected-article-id",
            interactive=True,
        )

        articles_state = gr.State(articles)

        carousel_html = gr.HTML(value=render_carousel(articles, active_id=selected_article_id))

        with gr.Row():
            with gr.Column(scale=6):
                article_view = gr.HTML(value=render_article_view(selected_article))

            with gr.Column(scale=4, elem_classes=["chat-col"]):
                chatbot_kwargs = {"label": "Conversation", "height": 360}
                if "type" in inspect.signature(gr.Chatbot).parameters:
                    chatbot_kwargs["type"] = "messages"
                chatbot = gr.Chatbot(**chatbot_kwargs)

                with gr.Row(elem_classes=["chips-row"]):
                    suggestion_one = gr.Button(questions[0], size="sm")
                    suggestion_two = gr.Button(questions[1], size="sm")
                    suggestion_three = gr.Button(questions[2], size="sm")
                    suggestion_four = gr.Button(questions[3], size="sm")

                user_input = gr.Textbox(
                    placeholder="Ask about this story or a broader topic...",
                    show_label=False,
                )

                with gr.Row():
                    send_button = gr.Button("Send", variant="primary")
                    timeline_button = gr.Button("Build timeline")

                suggestion_state = gr.State(questions)

        with gr.Group(elem_classes=["timeline-section"]):
            gr.HTML(
                "<div class='timeline-section-header'>"
                "<h3>Timeline</h3>"
                "<span class='timeline-section-hint'>Click a card to switch the current story.</span>"
                "</div>"
            )
            timeline_output = gr.HTML(value=EMPTY_TIMELINE)

        with gr.Accordion("Sources", open=False, elem_classes=["sources-section"]):
            sources_output = gr.HTML(value=EMPTY_SOURCES)

        def on_article_change(article_id: str, articles_list: list[Article]):
            article = get_article(article_id)
            new_questions = example_questions(article)
            return (
                render_carousel(articles_list, active_id=article_id),
                render_article_view(article),
                new_questions,
                EMPTY_CHAT,
                "",
                EMPTY_SOURCES,
                EMPTY_TIMELINE,
            )

        selected_article_textbox.change(
            fn=on_article_change,
            inputs=[selected_article_textbox, articles_state],
            outputs=[
                carousel_html,
                article_view,
                suggestion_state,
                chatbot,
                user_input,
                sources_output,
                timeline_output,
            ],
        ).then(
            fn=lambda q: suggestion_updates(q),
            inputs=[suggestion_state],
            outputs=[suggestion_one, suggestion_two, suggestion_three, suggestion_four],
        )

        suggestion_one.click(fn=lambda q: use_example(q, 0), inputs=[suggestion_state], outputs=[user_input])
        suggestion_two.click(fn=lambda q: use_example(q, 1), inputs=[suggestion_state], outputs=[user_input])
        suggestion_three.click(fn=lambda q: use_example(q, 2), inputs=[suggestion_state], outputs=[user_input])
        suggestion_four.click(fn=lambda q: use_example(q, 3), inputs=[suggestion_state], outputs=[user_input])

        send_button.click(
            fn=ask_question,
            inputs=[user_input, chatbot, selected_article_textbox],
            outputs=[chatbot, user_input, sources_output],
        )
        user_input.submit(
            fn=ask_question,
            inputs=[user_input, chatbot, selected_article_textbox],
            outputs=[chatbot, user_input, sources_output],
        )
        timeline_button.click(
            fn=build_timeline,
            inputs=[selected_article_textbox, user_input],
            outputs=[timeline_output],
        )

    return demo
