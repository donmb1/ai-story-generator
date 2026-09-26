from pathlib import Path

import pytest

from app import llm
from app.settings import settings

STUB = str(Path(__file__).parent / "bin" / "claude")


def override(**kw):
    # Settings ist frozen; für Tests gezielt umgehen
    old = {k: getattr(settings, k) for k in kw}
    for k, v in kw.items():
        object.__setattr__(settings, k, v)
    return old


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    old = override(claude_bin=STUB, provider="claude_cli", llm_max_retries=0)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-cli")
    yield
    override(**old)


def test_story_from_cli():
    r = llm.generate("Schreibe eine Geschichte", kids=True, words=600)
    assert r.title == "Der kleine Drache"
    assert r.story.startswith("Es war einmal") and "Maus" in r.story


def test_auth_error_is_readable(monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "auth")
    with pytest.raises(llm.StoryError, match="Anmeldung"):
        llm.generate("x", kids=False, words=600)


def test_missing_binary(monkeypatch):
    override(claude_bin="/nope/claude")
    with pytest.raises(llm.StoryError, match="nicht installiert"):
        llm.generate("x", kids=False, words=600)
