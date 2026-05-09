import sys

from ask_the_news import db
from ask_the_news.app_logic import build_demo


def startup_diagnostic() -> None:
    print("--- ask-the-news startup ---", flush=True)
    print(f"DATABASE_URL configured: {db.is_configured()}", flush=True)
    if db.is_configured():
        try:
            with db.connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM articles")
                article_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]
            print(f"DB reachable: {article_count} articles, {chunk_count} chunks", flush=True)
        except Exception as exc:
            print(f"DB connect FAILED: {exc!r}", flush=True)
    else:
        print("Falling back to local SQLite (data/news.db must exist)", flush=True)
    print("--- end diagnostic ---", flush=True)
    sys.stdout.flush()


startup_diagnostic()
demo = build_demo()


if __name__ == "__main__":
    demo.launch()
