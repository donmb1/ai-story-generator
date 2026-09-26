"""Story-Erzeugung über Anthropic Claude, OpenAI oder einen Fake-Provider (für Tests)."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
from dataclasses import dataclass

from .settings import settings

log = logging.getLogger("story.llm")

SYSTEM_PROMPT = """Du bist ein warmherziger, einfallsreicher Geschichtenerzähler.
Du schreibst auf Deutsch Geschichten, die auf einem E-Reader gelesen oder vorgelesen werden.

Form:
- Erste Zeile: "TITEL: " gefolgt von einem kurzen, schönen Titel.
- Danach eine Leerzeile und die Geschichte in Absätzen, getrennt durch Leerzeilen.
- Reiner Fließtext: kein Markdown, keine Überschriften, keine Aufzählungen, keine Emojis.
- Wörtliche Rede mit deutschen Anführungszeichen („ … “).
- Kein Nachwort, keine Erklärung, keine Rückfragen.

Inhalt:
- Die Geschichte hat einen klaren Anfang, eine Mitte mit einem Problem und ein gutes Ende.
- Halte dich an die gewünschte Länge.
- Bei Geschichten für Kinder: altersgerecht, keine Gewalt, keine Angstmacherei,
  ein tröstliches, positives Ende."""

KIDS_SUFFIX = "\nDiese Geschichte ist für Kinder. Achte besonders auf eine kindgerechte, sichere Sprache."


class StoryError(Exception):
    """Fehler, dessen Text dem Nutzer auf dem Kindle angezeigt werden darf."""


@dataclass
class StoryResult:
    title: str
    story: str
    model: str


def _parse(text: str) -> tuple[str, str]:
    text = text.strip().replace("\r\n", "\n")
    m = re.match(r"^\s*(?:TITEL|Titel)\s*:\s*(.+?)\s*\n", text)
    if m:
        title = m.group(1).strip().strip('"„“*#')
        body = text[m.end():].strip()
    else:
        first, _, rest = text.partition("\n")
        title, body = first.strip().strip('"„“*#'), rest.strip()
    body = re.sub(r"[*_#]{1,3}", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    if len(body) < 50:
        raise StoryError("Die Geschichte kam leer zurück.")
    return title[:120] or "Ohne Titel", body


def _max_tokens(words: int) -> int:
    # Deutsch ~ 1,6–2 Tokens pro Wort, plus Luft für adaptives Denken
    return min(16000, max(4000, int(words * 3) + 3000))


def _anthropic(prompt: str, system: str, words: int) -> StoryResult:
    import anthropic

    client = anthropic.Anthropic(timeout=settings.llm_timeout_s, max_retries=settings.llm_max_retries)
    try:
        resp = client.beta.messages.create(
            model=settings.anthropic_model,
            max_tokens=_max_tokens(words),
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.anthropic_effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        log.error("anthropic: authentication failed (check ANTHROPIC_API_KEY)")
        raise StoryError("Server: API-Schlüssel ungültig.")
    except anthropic.RateLimitError:
        log.warning("anthropic: rate limited")
        raise StoryError("Die KI ist gerade überlastet. Bitte gleich nochmal.")
    except anthropic.BadRequestError as e:
        log.error("anthropic: bad request: %s", e.message)
        raise StoryError("Server: ungültige Anfrage an die KI.")
    except anthropic.APITimeoutError:
        log.warning("anthropic: timeout")
        raise StoryError("Die KI hat zu lange gebraucht.")
    except anthropic.APIStatusError as e:
        log.error("anthropic: status %s", e.status_code)
        raise StoryError("Die KI ist gerade nicht erreichbar.")
    except anthropic.APIConnectionError:
        log.error("anthropic: connection error")
        raise StoryError("Server hat keine Verbindung zur KI.")

    if resp.stop_reason == "refusal":
        cat = resp.stop_details.category if resp.stop_details else None
        log.warning("anthropic: refusal (category=%s)", cat)
        raise StoryError("Zu dieser Auswahl gab es leider keine Geschichte.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    if resp.stop_reason == "max_tokens":
        log.warning("anthropic: hit max_tokens, story may be cut")
    log.info(
        "anthropic: ok model=%s in=%s out=%s",
        resp.model, resp.usage.input_tokens, resp.usage.output_tokens,
    )
    title, body = _parse(text)
    return StoryResult(title=title, story=body, model=resp.model)


def _openai(prompt: str, system: str, words: int) -> StoryResult:
    import openai

    client = openai.OpenAI(timeout=settings.llm_timeout_s, max_retries=settings.llm_max_retries)
    try:
        resp = client.responses.create(
            model=settings.openai_model,
            instructions=system,
            input=prompt,
            max_output_tokens=_max_tokens(words),
        )
    except openai.AuthenticationError:
        log.error("openai: authentication failed (check OPENAI_API_KEY)")
        raise StoryError("Server: API-Schlüssel ungültig.")
    except openai.RateLimitError:
        log.warning("openai: rate limited")
        raise StoryError("Die KI ist gerade überlastet. Bitte gleich nochmal.")
    except openai.APITimeoutError:
        log.warning("openai: timeout")
        raise StoryError("Die KI hat zu lange gebraucht.")
    except openai.APIStatusError as e:
        log.error("openai: status %s", e.status_code)
        raise StoryError("Die KI ist gerade nicht erreichbar.")
    except openai.APIConnectionError:
        log.error("openai: connection error")
        raise StoryError("Server hat keine Verbindung zur KI.")
    title, body = _parse(resp.output_text or "")
    log.info("openai: ok model=%s", resp.model)
    return StoryResult(title=title, story=body, model=resp.model)


def _claude_cli(prompt: str, system: str, words: int) -> StoryResult:
    """Claude Code im Print-Modus, ohne Werkzeuge, ohne MCP, ohne gespeicherte Sitzung."""
    cmd = [
        settings.claude_bin, "-p", prompt,
        "--output-format", "json",
        "--model", settings.anthropic_model,
        "--effort", settings.anthropic_effort,
        "--system-prompt", system,
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    last_error = "Die KI ist gerade nicht erreichbar."
    for attempt in range(settings.llm_max_retries + 1):
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=settings.llm_timeout_s,
                stdin=subprocess.DEVNULL, cwd=os.environ.get("CLAUDE_CWD", "/tmp"),
                # Ein gesetzter API-Key hätte Vorrang vor dem OAuth-Token – bewusst entfernen
                env={k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
            )
        except FileNotFoundError:
            log.error("claude_cli: %s not found", settings.claude_bin)
            raise StoryError("Server: Claude CLI nicht installiert.")
        except subprocess.TimeoutExpired:
            log.warning("claude_cli: timeout after %ss", settings.llm_timeout_s)
            raise StoryError("Die KI hat zu lange gebraucht.")
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            out = {"is_error": True, "result": ""}
        result = out.get("result") if isinstance(out.get("result"), str) else ""
        if proc.returncode == 0 and not out.get("is_error") and result:
            log.info("claude_cli: ok model=%s duration_ms=%s", settings.anthropic_model, out.get("duration_ms"))
            title, body = _parse(result)
            return StoryResult(title=title, story=body, model=settings.anthropic_model)
        # Fehlertext nur gekürzt loggen, keine Prompts
        detail = (result or proc.stderr or "")[-300:].replace("\n", " ")
        log.warning("claude_cli: failed rc=%s attempt=%s: %s", proc.returncode, attempt + 1, detail)
        low = detail.lower()
        if any(k in low for k in ("login", "oauth", "unauthorized", "authentication", "invalid api key")):
            raise StoryError("Server: Claude-Anmeldung ungültig.")
        if "rate" in low or "limit" in low or "overloaded" in low:
            last_error = "Die KI ist gerade überlastet. Bitte gleich nochmal."
    raise StoryError(last_error)


_FAKE_SENTENCES = [
    "Es war einmal an einem Morgen, an dem die Sonne besonders neugierig über die Hügel schaute.",
    "„Heute passiert etwas Besonderes“, flüsterte der Wind und wirbelte ein paar Blätter hoch.",
    "Niemand hätte gedacht, dass ausgerechnet eine kleine Tür im Gartenzaun der Anfang von allem war.",
    "Mit klopfendem Herzen trat die Heldin hindurch und staunte über die bunten Wege dahinter.",
    "Ein alter Fuchs mit Brille saß auf einem Stein und las die Zeitung von übermorgen.",
    "Gemeinsam fanden sie heraus, dass Mut manchmal einfach heißt, die nächste Frage zu stellen.",
    "Am Abend leuchteten die Sterne, als hätten sie die ganze Zeit zugesehen.",
]


def _fake(prompt: str, system: str, words: int) -> StoryResult:
    rng = random.Random(prompt)
    paras, count = [], 0
    while count < words:
        para = " ".join(rng.choice(_FAKE_SENTENCES) for _ in range(rng.randint(3, 6)))
        paras.append(para)
        count += len(para.split())
    return StoryResult(title="Die Tür im Gartenzaun", story="\n\n".join(paras), model="fake")


def generate(prompt: str, kids: bool, words: int) -> StoryResult:
    system = SYSTEM_PROMPT + (KIDS_SUFFIX if kids else "")
    provider = settings.provider
    if provider == "claude_cli":
        return _claude_cli(prompt, system, words)
    if provider == "anthropic":
        return _anthropic(prompt, system, words)
    if provider == "openai":
        return _openai(prompt, system, words)
    if provider == "fake":
        return _fake(prompt, system, words)
    raise StoryError(f"Unbekannter Provider: {provider}")
