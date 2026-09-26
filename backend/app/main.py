"""AI Story Reader – Backend.

JSON-API:      GET /health, GET /config, POST /story
Kindle-API:    GET /k/start, /k/screen.png, /k/tap, /k/generate, /k/menu, /k/story/{id}/{n}.png
               (Antworten der Befehls-Endpunkte sind eine Zeile text/plain, leicht in Shell zu parsen)
"""

from __future__ import annotations

import logging
import random
import time
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from . import llm, screens, store
from .security import check_token, generating, generating_lock, requests_limit, stories_limit
from .settings import settings
from .wizard import free_prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("story")

app = FastAPI(title="AI Story Reader", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def access_log(request: Request, call_next):
    # Bewusst ohne Query-String: dort können Token (?t=) und Zustand stehen
    start = time.monotonic()
    response = await call_next(request)
    log.info("%s %s -> %s %.0fms", request.method, request.url.path, response.status_code,
             (time.monotonic() - start) * 1000)
    return response


def device(request: Request) -> str:
    dev = check_token(request)
    if not requests_limit.allow(dev):
        raise HTTPException(429, "too many requests")
    return dev


def text(body: str) -> PlainTextResponse:
    return PlainTextResponse(body + "\n", headers={"Cache-Control": "no-store"})


def png(data: bytes) -> Response:
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})


def generate_story(dev: str, prompt: str, kids: bool, words: int, sel: list[list[str]]) -> dict:
    if not stories_limit.allow(dev):
        raise llm.StoryError("Genug Geschichten für diese Stunde. Später wieder!")
    with generating_lock:
        if dev in generating:
            raise llm.StoryError("Es wird schon eine Geschichte geschrieben.")
        generating.add(dev)
    try:
        # kleine Zufalls-Note, damit „Nochmal“ mit gleicher Auswahl eine neue Variante liefert
        prompt += f"\nVariante {random.randint(1, 9999)}: überrasche mit einer eigenen Idee."
        log.info("generate: device=%s provider=%s kids=%s words=%s", dev, settings.provider, kids, words)
        result = llm.generate(prompt, kids=kids, words=words)
        return store.save(result.title, result.story, result.model, sel, kids)
    finally:
        with generating_lock:
            generating.discard(dev)


# ---------------------------------------------------------------- JSON-API

@app.get("/health")
def health():
    return {"ok": True, "provider": settings.provider}


@app.get("/config")
def config(dev: str = Depends(device)):
    return {
        "steps": [
            {"id": s.id, "title": s.title, "when": s.when,
             "options": [{"id": o.id, "label": o.label} for o in s.options]}
            for s in screens.wizard.steps
        ]
    }


class StoryRequest(BaseModel):
    selections: dict[str, str] | None = None
    prompt: str | None = Field(default=None, max_length=300)
    length: Literal["short", "medium", "long"] = "medium"

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = "".join(ch for ch in v if ch.isprintable()).strip()
        if len(v) < 3:
            raise ValueError("prompt too short")
        return v


@app.post("/story")
def story(req: StoryRequest, dev: str = Depends(device)):
    wz = screens.wizard
    if req.selections is not None:
        try:
            sel = wz.from_dict(req.selections)
        except ValueError as e:
            raise HTTPException(422, str(e))
        prompt, kids, words = wz.build_prompt(sel), wz.is_kids(sel), wz.target_words(sel)
    elif req.prompt:
        sel = []
        words = {"short": 600, "medium": 1200, "long": 2200}[req.length]
        prompt, kids = free_prompt(req.prompt, req.length), False
    else:
        raise HTTPException(422, "selections or prompt required")
    try:
        doc = generate_story(dev, prompt, kids, words, sel)
    except llm.StoryError as e:
        raise HTTPException(502, str(e))
    return {"id": doc["id"], "title": doc["title"], "story": doc["story"], "model": doc["model"], "pages": doc["pages"]}


# ---------------------------------------------------------------- Kindle-API

@app.get("/k/start")
def k_start(dev: str = Depends(device)):
    return text(f"ui {screens.encode(screens.home())}")


@app.get("/k/screen.png")
def k_screen(s: str = Query("", max_length=2000), dev: str = Depends(device)):
    return png(screens.png(screens.decode(s)))


@app.get("/k/offline.png")
def k_offline(dev: str = Depends(device)):
    return png(screens.png({"v": "offline"}))


@app.get("/k/tap")
def k_tap(s: str = Query("", max_length=2000), x: int = Query(..., ge=0, le=5000),
          y: int = Query(..., ge=0, le=5000), dev: str = Depends(device)):
    return text(screens.tap(screens.decode(s), x, y))


@app.get("/k/generate")
def k_generate(s: str = Query("", max_length=2000), dev: str = Depends(device)):
    state = screens.decode(s)
    sel = state.get("sel", [])
    wz = screens.wizard
    if not sel or not wz.complete(sel):
        return text(f"ui {screens.encode(screens.home())}")
    try:
        doc = generate_story(dev, wz.build_prompt(sel), wz.is_kids(sel), wz.target_words(sel), sel)
    except llm.StoryError as e:
        return text(f"ui {screens.encode({'v': 'error', 'sel': sel, 'm': str(e)})}")
    except Exception:
        log.exception("generate failed")
        return text(f"ui {screens.encode({'v': 'error', 'sel': sel, 'm': 'Unerwarteter Serverfehler.'})}")
    return text(f"read {doc['id']} {doc['pages']} 1")


@app.get("/k/menu")
def k_menu(id: str = Query("", max_length=32), pg: int = Query(1, ge=1, le=9999), dev: str = Depends(device)):
    return text(f"ui {screens.encode({'v': 'menu', 'id': id, 'pg': pg})}")


@app.get("/k/story/{story_id}/{n}.png")
def k_page(story_id: str, n: int, dev: str = Depends(device)):
    data = store.page_png(story_id, n)
    if data is None:
        raise HTTPException(404, "no such page")
    return png(data)
