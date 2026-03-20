from __future__ import annotations

from html import escape
from textwrap import shorten

import gradio as gr
import httpx

from ask_the_news.config import API_BASE_URL, RETRIEVAL_TOP_K
from ask_the_news.models import Article, Citation, TimelineItem
from ask_the_news.service import NewsService


EMPTY_SOURCES = "### Sources\n\nNo sources yet."
EMPTY_TIMELINE = "<div class='timeline-empty'>Build a timeline to see related coverage.</div>"
EMPTY_CHAT: list[dict[str, str]] = []
LOCAL_SERVICE = NewsService()

UI_CSS = """
.app-shell {
  background:
    radial-gradient(circle at top left, rgba(201, 227, 255, 0.8), transparent 32%),
    linear-gradient(180deg, #f8fafc 0%, #eef4f7 100%);
}
.panel {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #d8e3ea;
  border-radius: 20px;
  box-shadow: 0 18px 40px rgba(38, 60, 77, 0.08);
}
.featured-card {
  padding: 22px;
}
.featured-card .eyebrow {
  color: #516475;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.featured-card h2 {
  color: #10202f;
  font-size: 30px;
  line-height: 1.15;
  margin: 10px 0 12px;
}
.featured-meta {
  color: #566778;
  font-size: 14px;
  margin-bottom: 16px;
}
.featured-summary {
  color: #22384a;
  font-size: 15px;
  line-height: 1.65;
}
.featured-link {
  display: inline-block;
  margin-top: 18px;
  color: #0a5c7a;
  font-weight: 600;
  text-decoration: none;
}
.headline-list {
  max-height: 420px;
  overflow-y: auto;
  padding: 6px;
}
.headline-list label {
  border-radius: 14px;
  margin-bottom: 8px;
}
.headline-list label:hover {
  background: rgba(229, 240, 245, 0.8);
}
.headline-hint {
  color: #607385;
  font-size: 13px;
  margin-bottom: 10px;
}
.question-grid {
  gap: 10px;
}
.timeline-strip {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding-bottom: 6px;
}
.timeline-card {
  min-width: 240px;
  max-width: 260px;
  background: linear-gradient(180deg, #fbfdff 0%, #edf5f8 100%);
  border: 1px solid #d7e5eb;
  border-radius: 16px;
  padding: 16px;
}
.timeline-date {
  color: #0a5c7a;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.timeline-card h4 {
  color: #10202f;
  font-size: 16px;
  line-height: 1.35;
  margin: 8px 0 10px;
}
.timeline-card p {
  color: #3a4f60;
  font-size: 14px;
  line-height: 1.55;
  margin: 0 0 12px;
}
.timeline-card a {
  color: #0a5c7a;
  font-weight: 600;
  text-decoration: none;
}
.timeline-empty {
  color: #607385;
  padding: 10px 2px;
}
"""


def article_label(article: Article) -> str:
    return f"{shorten(article.title, width=74, placeholder='...')} | {article.published_at}"


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


def render_featured_card(article: Article | None) -> str:
    if article is None:
        return (
            "<div class='featured-card'>"
            "<div class='eyebrow'>No story loaded</div>"
            "<h2>Import articles and sync SQLite to start.</h2>"
            "<p class='featured-summary'>Run the ingestion pipeline, then rebuild the local vector index.</p>"
            "</div>"
        )

    section = escape(article.section or "General")
    title = escape(article.title)
    summary = escape(shorten(article.summary_text, width=520, placeholder="..."))
    url = escape(article.url)
    published = escape(article.published_at)
    return (
        "<div class='featured-card'>"
        f"<div class='eyebrow'>{section}</div>"
        f"<h2>{title}</h2>"
        f"<div class='featured-meta'>{published}</div>"
        f"<div class='featured-summary'>{summary}</div>"
        f"<a class='featured-link' href='{url}' target='_blank'>Open source article</a>"
        "</div>"
    )


def example_questions(article: Article | None) -> list[str]:
    return LOCAL_SERVICE.example_questions(article)


def suggestion_updates(questions: list[str]) -> list[dict]:
    return [gr.update(value=question) for question in questions]


def render_sources(citations: list[Citation]) -> str:
    if not citations:
        return EMPTY_SOURCES
    lines = ["### Sources", ""]
    for citation in citations:
        title = citation.title.replace("\n", " ").strip()
        snippet = shorten(citation.snippet.replace("\n", " ").strip(), width=180, placeholder="...")
        lines.append(f"- [{title}]({citation.url}) | {citation.published_at}")
        if snippet:
            lines.append(f"  {snippet}")
    return "\n".join(lines)


def render_timeline(items: list[TimelineItem]) -> str:
    if not items:
        return EMPTY_TIMELINE

    cards = []
    for item in items[:10]:
        title = escape(item.title)
        summary = escape(shorten(item.summary, width=220, placeholder="..."))
        date = escape(item.published_at)
        url = escape(item.url)
        cards.append(
            "<article class='timeline-card'>"
            f"<div class='timeline-date'>{date}</div>"
            f"<h4>{title}</h4>"
            f"<p>{summary}</p>"
            f"<a href='{url}' target='_blank'>Read article</a>"
            "</article>"
        )
    return f"<div class='timeline-strip'>{''.join(cards)}</div>"


def load_article_view(article_id: str) -> tuple[str, list[str], list[dict[str, str]], str, str, str]:
    article = get_article(article_id)
    questions = example_questions(article)
    return (
        render_featured_card(article),
        questions,
        EMPTY_CHAT,
        "",
        EMPTY_SOURCES,
        EMPTY_TIMELINE,
    )


def use_example(questions: list[str], index: int) -> str:
    if 0 <= index < len(questions):
        return questions[index]
    return ""


def ask_question(
    user_query: str,
    history: list[dict[str, str]] | None,
    current_article_id: str,
) -> tuple[list[dict[str, str]], str, str]:
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
    choices = [(article_label(article), article.article_id) for article in articles]

    with gr.Blocks(title="Ask the News", css=UI_CSS) as demo:
        gr.Markdown("# Ask the News", elem_classes=["app-shell"])
        with gr.Row(equal_height=False, elem_classes=["app-shell"]):
            with gr.Column(scale=5, elem_classes=["panel"]):
                featured_card = gr.HTML(render_featured_card(selected_article))
                article_selector = gr.Radio(
                    choices=choices,
                    value=selected_article_id,
                    label="Stories",
                    elem_classes=["headline-list"],
                )
            with gr.Column(scale=7, elem_classes=["panel"]):
                chatbot = gr.Chatbot(label="Ask the News")
                user_input = gr.Textbox(
                    label="Question",
                    placeholder="Ask about the current story or a broader topic.",
                )
                with gr.Row(equal_height=True, elem_classes=["question-grid"]):
                    suggestion_one = gr.Button(questions[0], size="sm")
                    suggestion_two = gr.Button(questions[1], size="sm")
                    suggestion_three = gr.Button(questions[2], size="sm")
                    suggestion_four = gr.Button(questions[3], size="sm")
                    send_button = gr.Button("Send", variant="primary")
                with gr.Row():
                    timeline_button = gr.Button("Timeline")
                suggestion_state = gr.State(questions)
                timeline_output = gr.HTML(EMPTY_TIMELINE)
                sources_output = gr.Markdown(EMPTY_SOURCES)
                

        article_selector.change(
            fn=load_article_view,
            inputs=[article_selector],
            outputs=[
                featured_card,
                suggestion_state,
                chatbot,
                user_input,
                sources_output,
                timeline_output,
            ],
        ).then(
            fn=lambda questions: suggestion_updates(questions),
            inputs=[suggestion_state],
            outputs=[suggestion_one, suggestion_two, suggestion_three, suggestion_four],
        )

        suggestion_one.click(fn=lambda questions: use_example(questions, 0), inputs=[suggestion_state], outputs=[user_input])
        suggestion_two.click(fn=lambda questions: use_example(questions, 1), inputs=[suggestion_state], outputs=[user_input])
        suggestion_three.click(fn=lambda questions: use_example(questions, 2), inputs=[suggestion_state], outputs=[user_input])
        suggestion_four.click(fn=lambda questions: use_example(questions, 3), inputs=[suggestion_state], outputs=[user_input])

        send_button.click(
            fn=ask_question,
            inputs=[user_input, chatbot, article_selector],
            outputs=[chatbot, user_input, sources_output],
        )
        user_input.submit(
            fn=ask_question,
            inputs=[user_input, chatbot, article_selector],
            outputs=[chatbot, user_input, sources_output],
        )
        timeline_button.click(
            fn=build_timeline,
            inputs=[article_selector, user_input],
            outputs=[timeline_output],
        )

    return demo
