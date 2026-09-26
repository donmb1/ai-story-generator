"""Bildschirm-Zustände und Tap-Logik für den Kindle ("Thin Client").

Der Kindle kennt keine Bildschirme. Er zeigt ein PNG, schickt Tap-Koordinaten
plus den undurchsichtigen Zustand zurück und bekommt einen Befehl:

    ui <state>                 neuen Bildschirm laden
    gen <state>                Lade-Bildschirm zeigen, dann /k/generate aufrufen
    read <id> <pages> <page>   Story (lokal) lesen
    exit                       App beenden
    none                       nichts getroffen
"""

from __future__ import annotations

import base64
import json
import random
from typing import Any

from . import render, store
from .render import MARGIN, W, H, Widget
from .wizard import Wizard

PER_PAGE = 11  # + "Zufällig" = 12 Kacheln
LIB_PER_PAGE = 6

wizard = Wizard()


# ---------------------------------------------------------------- Zustand

def encode(state: dict[str, Any]) -> str:
    raw = json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(token: str | None) -> dict[str, Any]:
    if not token or len(token) > 2000:
        return {"v": "home"}
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        state = json.loads(raw)
        if not isinstance(state, dict) or not isinstance(state.get("v"), str):
            raise ValueError
        sel = state.get("sel", [])
        state["sel"] = wizard.validate(sel) if sel else []
        state["p"] = max(0, int(state.get("p", 0)))
        return state
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"v": "home"}


def home() -> dict[str, Any]:
    return {"v": "home"}


# ---------------------------------------------------------------- Layouts

def _breadcrumb(sel: list[list[str]]) -> str:
    return " › ".join(label for _, label in wizard.labels(sel))


def layout(state: dict[str, Any]) -> list[Widget]:
    v = state["v"]
    sel = state.get("sel", [])
    p = state.get("p", 0)

    if v == "home":
        return [
            Widget("title", MARGIN, 200, W - 2 * MARGIN, 200, "Was möchtest du lesen?", size=76),
            Widget("small", MARGIN, 420, W - 2 * MARGIN, 40, "AI Story Reader", size=34),
            *render.stack(
                [
                    ("Geschichte zusammenstellen", "wiz", True),
                    ("Überrasch mich", "surprise", False),
                    ("Letzte Geschichten", "lib", False),
                    ("Beenden", "exit", False),
                ],
                top=560,
            ),
        ]

    if v == "step":
        step = wizard.next_step(sel)
        if step is None:
            return layout({"v": "summary", "sel": sel})
        opts = list(step.options)
        pages = max(1, -(-len(opts) // PER_PAGE))
        p = min(p, pages - 1)
        chunk = opts[p * PER_PAGE:(p + 1) * PER_PAGE]
        items = [(o.label, f"opt:{o.id}") for o in chunk] + [("Zufällig", "rnd")]
        return [
            *render.header(_breadcrumb(sel), step.title),
            *render.grid(items),
            *render.footer(
                ("‹ Zurück", "back"), p, pages,
                f"pg:{p - 1}" if p > 0 else None,
                f"pg:{p + 1}" if p < pages - 1 else None,
            ),
        ]

    if v == "summary":
        text = "\n".join(f"{t}: {label}" for t, label in wizard.labels(sel))
        return [
            *render.header("", "Deine Geschichte"),
            Widget("text", MARGIN, 300, W - 2 * MARGIN, 600, text, size=44),
            *render.stack(
                [("Geschichte erzeugen", "gen", True), ("Neu anfangen", "wiz", False)],
                top=H - 560,
            ),
            *render.footer(("‹ Zurück", "back"), 0, 1, None, None),
        ]

    if v == "loading":
        return [
            Widget("title", MARGIN, 420, W - 2 * MARGIN, 200, "Die Geschichte wird geschrieben …", size=70),
            Widget("text", MARGIN, 700, W - 2 * MARGIN, 400,
                   "Das dauert meistens 20 bis 60 Sekunden.\nBitte nicht tippen.", size=38),
            Widget("small", MARGIN, H - 160, W - 2 * MARGIN, 40, _breadcrumb(sel), size=30),
        ]

    if v == "lib":
        items = store.recent()
        pages = max(1, -(-len(items) // LIB_PER_PAGE))
        p = min(p, pages - 1)
        chunk = items[p * LIB_PER_PAGE:(p + 1) * LIB_PER_PAGE]
        out = [*render.header("", "Letzte Geschichten")]
        if not chunk:
            out.append(Widget("text", MARGIN, 320, W - 2 * MARGIN, 200, "Noch keine Geschichten.", size=40))
        out += render.grid([(s["title"], f"read:{s['id']}") for s in chunk], cols=1, row_h=130)
        out += render.footer(("‹ Start", "home"), p, pages,
                             f"pg:{p - 1}" if p > 0 else None,
                             f"pg:{p + 1}" if p < pages - 1 else None)
        return out

    if v == "menu":
        meta = store.meta(state.get("id", ""))
        title = meta["title"] if meta else "Menü"
        items = [("Weiterlesen", "resume", True)] if meta else []
        if meta and meta.get("sel"):
            items.append(("Nochmal, neue Variante", "again", False))
        items += [("Neue Geschichte", "wiz", False), ("Startseite", "home", False), ("Beenden", "exit", False)]
        return [*render.header("", title), *render.stack(items, top=330, h=140, gap=30)]

    if v == "error":
        items = [("Nochmal versuchen", "gen", True)] if wizard.complete(sel) and sel else []
        items.append(("Startseite", "home", False))
        return [
            *render.header("", "Das hat nicht geklappt"),
            Widget("text", MARGIN, 320, W - 2 * MARGIN, 400, str(state.get("m", ""))[:300], size=42),
            *render.stack(items, top=H - 520),
        ]

    if v == "offline":
        # Wird beim Start auf dem Kindle abgelegt; Zonen wertet das Kindle-Skript aus (Drittel)
        third = H // 3
        labels = ["Nochmal verbinden", "Letzte Geschichte lesen", "Beenden"]
        out = [Widget("small", MARGIN, 40, W - 2 * MARGIN, 40, "Keine Verbindung zum Server", size=34)]
        for i, label in enumerate(labels):
            out.append(Widget("button", MARGIN, i * third + 110, W - 2 * MARGIN, third - 180, label,
                              None, primary=(i == 0), size=54))
        return out

    return layout(home())


def png(state: dict[str, Any]) -> bytes:
    return render.draw_widgets(layout(state))


# ---------------------------------------------------------------- Taps

def tap(state: dict[str, Any], x: int, y: int) -> str:
    hit = next((w for w in layout(state) if w.hit(x, y)), None)
    if hit is None:
        return "none"
    return act(state, hit.action or "")


def _ui(state: dict[str, Any]) -> str:
    return f"ui {encode(state)}"


def _gen(sel: list[list[str]]) -> str:
    return f"gen {encode({'v': 'loading', 'sel': sel})}"


def act(state: dict[str, Any], action: str) -> str:
    sel = [list(x) for x in state.get("sel", [])]
    v = state["v"]

    if action == "exit":
        return "exit"
    if action == "home":
        return _ui(home())
    if action == "wiz":
        return _ui({"v": "step", "sel": []})
    if action == "lib":
        return _ui({"v": "lib"})
    if action == "surprise":
        return _gen(wizard.randomize())
    if action.startswith("pg:"):
        return _ui({**state, "p": int(action[3:])})
    if action == "gen":
        return _gen(sel)

    if action == "back":
        if v == "summary" or (v == "step" and sel):
            return _ui({"v": "step", "sel": sel[:-1]})
        return _ui(home())

    if action in ("rnd",) or action.startswith("opt:"):
        step = wizard.next_step(sel)
        if step is None:
            return _ui({"v": "summary", "sel": sel})
        opt_id = random.choice(step.options).id if action == "rnd" else action[4:]
        if step.option(opt_id) is None:
            return "none"
        sel.append([step.id, opt_id])
        return _ui({"v": "summary" if wizard.complete(sel) else "step", "sel": sel})

    if action.startswith("read:"):
        meta = store.meta(action[5:])
        if not meta:
            return _ui({"v": "lib"})
        return f"read {meta['id']} {meta['pages']} {meta.get('last_page', 1)}"

    if action == "resume":
        meta = store.meta(state.get("id", ""))
        if not meta:
            return _ui(home())
        return f"read {meta['id']} {meta['pages']} {max(1, int(state.get('pg', 1)))}"
    if action == "again":
        meta = store.meta(state.get("id", ""))
        if meta and meta.get("sel"):
            return _gen(wizard.validate(meta["sel"]))
        return _ui(home())

    return "none"
