"""
Article persistence layer.

Saves each Wikipedia article as an individual JSON file under
backend/data/articles/<slugified-title>.json

Improvements over the previous article_store.py:
- Absolute path derived from __file__ (no CWD dependency)
- One file per article instead of one monolithic articles.json
- Title slugification keeps filenames filesystem-safe
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "articles"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _slug(title: str) -> str:
    """Convert an article title to a safe filename slug."""
    cleaned = re.sub(r"[^\w\s\-]", "_", title.strip().lower())
    return re.sub(r"\s+", "_", cleaned) + ".json"


def save_article(title: str, article: dict) -> None:
    """Persist article dict to disk."""
    path = DATA_DIR / _slug(title)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(article, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[article_store] Could not save article '{title}': {e}")


def get_article(title: str) -> dict | None:
    """
    Load article from disk.
    Returns the dict if found, or None if the article has not been cached yet.
    """
    path = DATA_DIR / _slug(title)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[article_store] Could not load article '{title}': {e}")
        return None