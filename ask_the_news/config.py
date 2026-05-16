from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_PATH = DATA_DIR / "sample_articles.json"
SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(DATA_DIR / "news.db")))
VECTOR_INDEX_PATH = Path(os.getenv("VECTOR_INDEX_PATH", str(DATA_DIR / "chunk_embeddings.npy")))
VECTOR_INDEX_IDS_PATH = Path(os.getenv("VECTOR_INDEX_IDS_PATH", str(DATA_DIR / "chunk_ids.json")))
API_BASE_URL = os.getenv("API_BASE_URL", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

HF_DATASET_REPO = os.getenv("HF_DATASET_REPO", "RealTimeData/bbc_news_alltime")
HF_DATASET_SUBSETS = [item.strip() for item in os.getenv("HF_DATASET_SUBSETS", "").split(",") if item.strip()]

MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "50"))
CHUNK_TARGET_WORDS = int(os.getenv("CHUNK_TARGET_WORDS", "150"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))
CHUNK_PREVIEW_LIMIT = int(os.getenv("CHUNK_PREVIEW_LIMIT", "3"))
EMBEDDING_PREVIEW_CHARS = int(os.getenv("EMBEDDING_PREVIEW_CHARS", "280"))
CHUNK_MIN_WORDS = int(os.getenv("CHUNK_MIN_WORDS", "60"))
CHUNK_SPLIT_THRESHOLD = int(os.getenv("CHUNK_SPLIT_THRESHOLD", "188"))
CHUNK_MAX_WORDS = int(os.getenv("CHUNK_MAX_WORDS", "220"))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "8"))
ARTICLE_AGGREGATION = os.getenv("ARTICLE_AGGREGATION", "off").strip().lower() == "on"
ARTICLE_AGGREGATION_POOL_MULT = int(os.getenv("ARTICLE_AGGREGATION_POOL_MULT", "3"))
ARTICLE_AGGREGATION_BONUS = float(os.getenv("ARTICLE_AGGREGATION_BONUS", "0.15"))

HYBRID_RETRIEVAL = os.getenv("HYBRID_RETRIEVAL", "off").strip().lower() == "on"
HYBRID_BM25_POOL = int(os.getenv("HYBRID_BM25_POOL", "30"))
HYBRID_VECTOR_POOL = int(os.getenv("HYBRID_VECTOR_POOL", "30"))
HYBRID_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))

RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "off").strip().lower() == "on"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_POOL = int(os.getenv("RERANKER_POOL", "30"))
TIMELINE_RECALL_K = int(os.getenv("TIMELINE_RECALL_K", "30"))
TIMELINE_MAX_ARTICLES = int(os.getenv("TIMELINE_MAX_ARTICLES", "12"))
TIMELINE_MAX_PER_BUCKET = int(os.getenv("TIMELINE_MAX_PER_BUCKET", "2"))
TIMELINE_BUCKET_GRANULARITY = os.getenv("TIMELINE_BUCKET_GRANULARITY", "week")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
QUERY_ROUTER_MODEL = os.getenv("QUERY_ROUTER_MODEL", "gpt-5-nano")
QA_MODEL = os.getenv("QA_MODEL", "gpt-5-mini")
TIMELINE_MODEL = os.getenv("TIMELINE_MODEL", "gpt-5-mini")
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "700"))
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "minimal")
