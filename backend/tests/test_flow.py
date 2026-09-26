import os
import tempfile

os.environ["STORY_PROVIDER"] = "fake"
os.environ["DEVICE_TOKEN"] = "test-token"
os.environ["DATA_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from app import screens  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-token"}


def center(state_token: str, action: str) -> tuple[int, int]:
    for w in screens.layout(screens.decode(state_token)):
        if w.action == action:
            return w.x + w.w // 2, w.y + w.h // 2
    raise AssertionError(f"action {action} not on screen")


def tap(state: str, action: str) -> str:
    x, y = center(state, action)
    r = client.get("/k/tap", params={"s": state, "x": x, "y": y}, headers=AUTH)
    assert r.status_code == 200
    return r.text.strip()


def test_auth_required():
    assert client.get("/k/start").status_code == 401
    assert client.get("/k/start", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/k/start", params={"t": "test-token"}).status_code == 200
    assert client.get("/health").status_code == 200


def test_full_wizard_to_story():
    cmd, state = client.get("/k/start", headers=AUTH).text.split()
    assert cmd == "ui"
    assert client.get("/k/screen.png", params={"s": state}, headers=AUTH).content[:4] == b"\x89PNG"

    cmd, state = tap(state, "wiz").split()
    # Kindergeschichte -> Altersschritt muss erscheinen
    cmd, state = tap(state, "opt:kinder").split()
    assert screens.wizard.next_step(screens.decode(state)["sel"]).id == "alter"
    cmd, state = tap(state, "opt:6-8").split()
    cmd, state = tap(state, "opt:kurz").split()
    # Themenliste hat mehrere Seiten
    cmd, state = tap(state, "pg:1").split()
    assert screens.decode(state)["p"] == 1
    while screens.decode(state)["v"] == "step":
        cmd, state = tap(state, "rnd").split()
    assert screens.decode(state)["v"] == "summary"

    cmd, loading = tap(state, "gen").split()
    assert cmd == "gen"
    assert client.get("/k/screen.png", params={"s": loading}, headers=AUTH).status_code == 200

    r = client.get("/k/generate", params={"s": loading}, headers=AUTH)
    cmd, story_id, pages, page = r.text.split()
    assert cmd == "read" and int(pages) >= 1 and page == "1"
    for n in range(1, int(pages) + 1):
        png = client.get(f"/k/story/{story_id}/{n}.png", headers=AUTH)
        assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert client.get(f"/k/story/{story_id}/{int(pages) + 1}.png", headers=AUTH).status_code == 404

    cmd, menu = client.get("/k/menu", params={"id": story_id, "pg": 2}, headers=AUTH).text.split()
    assert tap(menu, "resume") == f"read {story_id} {pages} 2"


def test_back_from_first_step_goes_home():
    state = screens.encode({"v": "step", "sel": []})
    cmd, new = tap(state, "back").split()
    assert screens.decode(new)["v"] == "home"


def test_tampered_state_falls_back_home():
    bad = screens.encode({"v": "summary", "sel": [["genre", "hacker"]]})
    assert screens.decode(bad) == {"v": "home"}
    assert screens.decode("%%%") == {"v": "home"}


def test_miss_returns_none():
    state = screens.encode({"v": "home"})
    r = client.get("/k/tap", params={"s": state, "x": 5, "y": 5}, headers=AUTH)
    assert r.text.strip() == "none"


def test_json_api():
    r = client.post("/story", json={"selections": {"genre": "krimi", "laenge": "kurz"}}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] and body["story"] and body["model"] == "fake"
    assert client.post("/story", json={"selections": {"genre": "gibtsnicht"}}, headers=AUTH).status_code == 422
    assert client.post("/story", json={"prompt": "x" * 400}, headers=AUTH).status_code == 422
    r = client.post("/story", json={"prompt": "Ein Detektiv auf dem Mond", "length": "short"}, headers=AUTH)
    assert r.status_code == 200


def test_config():
    r = client.get("/config", headers=AUTH)
    ids = [s["id"] for s in r.json()["steps"]]
    assert ids[0] == "genre" and "thema" in ids
