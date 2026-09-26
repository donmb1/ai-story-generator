"""Story-Konfigurator: Schritte, Auswahl-Validierung, Prompt-Bau.

Die Auswahl ist eine geordnete Liste von (step_id, option_id). Nur IDs aus
wizard.json werden akzeptiert – vom Kindle kommt nie freier Text.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

WIZARD_FILE = Path(__file__).with_name("wizard.json")
RANDOM_ID = "_zufall"


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    prompt: str
    kids: bool = False
    words: int | None = None


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    short: str
    options: tuple[Option, ...]
    when: dict[str, list[str]] | None = None

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


class Wizard:
    def __init__(self, path: Path = WIZARD_FILE):
        raw = json.loads(path.read_text(encoding="utf-8"))
        names = [n for n in raw.get("names", []) if isinstance(n, str) and n.strip()]
        steps = []
        for s in raw["steps"]:
            opts = [
                Option(
                    id=o["id"],
                    label=o["label"],
                    prompt=o.get("prompt", ""),
                    kids=bool(o.get("kids", False)),
                    words=o.get("words"),
                )
                for o in s["options"]
            ]
            if s.get("names_as_options"):
                opts = [
                    Option(id=f"name:{i}", label=n, prompt=f"ein Kind namens {n}")
                    for i, n in enumerate(names)
                ] + opts
            steps.append(Step(id=s["id"], title=s["title"], short=s.get("short", s["title"]), options=tuple(opts), when=s.get("when")))
        self.steps: tuple[Step, ...] = tuple(steps)
        self._by_id = {s.id: s for s in self.steps}

    def step(self, step_id: str) -> Step | None:
        return self._by_id.get(step_id)

    @staticmethod
    def _applies(step: Step, sel: dict[str, str]) -> bool:
        if not step.when:
            return True
        return all(sel.get(k) in allowed for k, allowed in step.when.items())

    def next_step(self, sel: list[list[str]]) -> Step | None:
        chosen = dict(sel)
        for step in self.steps:
            if step.id not in chosen and self._applies(step, chosen):
                return step
        return None

    def validate(self, sel: list[list[str]]) -> list[list[str]]:
        """Wirft ValueError bei unbekannten Schritten/Optionen oder falscher Reihenfolge."""
        clean: list[list[str]] = []
        for item in sel:
            if not (isinstance(item, (list, tuple)) and len(item) == 2):
                raise ValueError("bad selection item")
            step_id, opt_id = str(item[0]), str(item[1])
            expected = self.next_step(clean)
            if expected is None or expected.id != step_id:
                raise ValueError(f"unexpected step {step_id!r}")
            if expected.option(opt_id) is None:
                raise ValueError(f"unknown option {opt_id!r} for {step_id!r}")
            clean.append([step_id, opt_id])
        return clean

    def complete(self, sel: list[list[str]]) -> bool:
        return self.next_step(sel) is None

    def randomize(self, sel: list[list[str]] | None = None, rng: random.Random | None = None) -> list[list[str]]:
        """Füllt alle offenen Schritte zufällig auf."""
        rng = rng or random.Random()
        out = [list(x) for x in (sel or [])]
        while (step := self.next_step(out)) is not None:
            out.append([step.id, rng.choice(step.options).id])
        return out

    def from_dict(self, d: dict[str, str]) -> list[list[str]]:
        """JSON-API: {"genre": "kinder", ...} -> geordnete, validierte Liste. Fehlendes wird zufällig ergänzt."""
        out: list[list[str]] = []
        while (step := self.next_step(out)) is not None:
            opt = d.get(step.id)
            if opt is None or opt == RANDOM_ID:
                opt = random.choice(step.options).id
            out.append([step.id, opt])
        unknown = set(d) - {s for s, _ in out}
        if unknown:
            raise ValueError(f"unknown or inapplicable steps: {sorted(unknown)}")
        return self.validate(out)

    def labels(self, sel: list[list[str]]) -> list[tuple[str, str]]:
        out = []
        for step_id, opt_id in sel:
            step = self.step(step_id)
            opt = step.option(opt_id) if step else None
            if step and opt:
                out.append((step.short, opt.label))
        return out

    def is_kids(self, sel: list[list[str]]) -> bool:
        genre = dict(sel).get("genre")
        step = self.step("genre")
        opt = step.option(genre) if step and genre else None
        return bool(opt and opt.kids)

    def target_words(self, sel: list[list[str]]) -> int:
        step = self.step("laenge")
        opt = step.option(dict(sel).get("laenge", "")) if step else None
        return (opt.words if opt and opt.words else 1200)

    def build_prompt(self, sel: list[list[str]]) -> str:
        chosen = dict(sel)

        def p(step_id: str) -> str:
            step = self.step(step_id)
            opt = step.option(chosen.get(step_id, "")) if step else None
            return opt.prompt if opt else ""

        parts = [f"Schreibe {p('genre') or 'eine Geschichte'}"]
        if p("alter"):
            parts.append(p("alter"))
        if p("thema"):
            parts.append(f"Thema: {p('thema')}")
        if p("held"):
            parts.append(f"Hauptfigur: {p('held')}")
        if p("stimmung"):
            parts.append(f"Stimmung: {p('stimmung')}")
        if p("botschaft"):
            parts.append(f"Unaufdringliche Botschaft: {p('botschaft')}")
        parts.append(f"Länge: {p('laenge') or 'etwa 1200 Wörter'}")
        return ".\n".join(parts) + "."


def free_prompt(prompt: str, length: str) -> str:
    """Für die JSON-API mit freiem Prompt (nicht vom Kindle genutzt)."""
    words = {"short": 600, "medium": 1200, "long": 2200}.get(length, 1200)
    return f"Schreibe eine Geschichte zu folgender Idee: {prompt}\nLänge: etwa {words} Wörter."
