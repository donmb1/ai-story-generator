"""Ablage der erzeugten Geschichten als JSON-Dateien (eine pro Story)."""

from __future__ import annotations

import json
import secrets
import time
from functools import lru_cache
from typing import Any

from . import render
from .settings import settings

STORIES = settings.data_dir / "stories"


def _path(story_id: str):
    if not story_id.isalnum() or len(story_id) > 32:
        return None
    return STORIES / f"{story_id}.json"


def save(title: str, story: str, model: str, sel: list[list[str]], kids: bool) -> dict[str, Any]:
    STORIES.mkdir(parents=True, exist_ok=True)
    story_id = secrets.token_hex(5)
    pages = len(render.paginate(title, story, kids))
    doc = {
        "id": story_id, "title": title, "story": story, "model": model,
        "sel": sel, "kids": kids, "pages": pages, "created": int(time.time()),
    }
    _path(story_id).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    _prune()
    recent.cache_clear()
    return doc


def _prune() -> None:
    files = sorted(STORIES.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[settings.keep_stories:]:
        f.unlink(missing_ok=True)


def load(story_id: str) -> dict[str, Any] | None:
    path = _path(story_id)
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def meta(story_id: str) -> dict[str, Any] | None:
    doc = load(story_id)
    if doc is None:
        return None
    return {k: doc[k] for k in ("id", "title", "pages", "sel", "created", "model")}


@lru_cache(maxsize=1)
def recent() -> list[dict[str, Any]]:
    if not STORIES.exists():
        return []
    files = sorted(STORIES.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": doc["id"], "title": doc["title"], "created": doc["created"]})
        except (OSError, ValueError, KeyError):
            continue
    return out


@lru_cache(maxsize=16)
def _pages(story_id: str) -> tuple[str, bool, list]:
    doc = load(story_id)
    if doc is None:
        raise KeyError(story_id)
    return doc["title"], doc["kids"], render.paginate(doc["title"], doc["story"], doc["kids"])


def page_png(story_id: str, n: int) -> bytes | None:
    try:
        title, kids, pages = _pages(story_id)
    except KeyError:
        return None
    if not 1 <= n <= len(pages):
        return None
    return render.render_story_page(title, pages[n - 1], n, len(pages), kids)
