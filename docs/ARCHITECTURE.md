# Architecture

```
┌──────────── Kindle (stock OS + jailbreak) ────────────┐
│ scriptlet "AI Story" → bin/start.sh → bin/aistory.sh  │   BusyBox ash
│   show screens:  eips -g <png>                        │   (stock firmware)
│   read taps:     bin/ktap serve  (EVIOCGRAB)          │   static ARMv7 binary
│   HTTP:          curl (or BusyBox wget)               │
│   offline:       /mnt/us/aistory/stories/<id>/<n>.png │
└───────────────────────────┬───────────────────────────┘
                            │ HTTP in the LAN / HTTPS via Funnel, device token
┌───────────────────────────▼───────────────────────────┐
│ Backend (FastAPI in Docker)                           │
│   screens.py   screen states + hit-testing            │
│   render.py    PNG 1072×1448, 16 grey levels          │
│   wizard.json  configurator steps and themes          │
│   store.py     stories as JSON                        │
│   llm.py       claude_cli | anthropic | openai | fake │
└───────────────────────────┬───────────────────────────┘
                            ▼
      claude -p (Claude Code CLI, subscription token, no tools)
```

## Thin client

The Kindle renders nothing itself. The backend returns every screen as a finished PNG, with fonts,
umlauts, wrapping and layout all solved server-side, and it also interprets taps. The Kindle only
needs three things: show an image, read a tap, make an HTTP request.

Why:
- There are no fonts, text layout or UTF-8 issues on a ten-year-old userspace.
- New themes, steps or layouts only change the server; the Kindle stays untouched.
- No free text comes from the device, so there is no prompt injection. The backend validates
  against a whitelist of IDs from `wizard.json`.

Trade-off: each screen change in the configurator costs one request (about 0.2–1 s in the LAN).
Reading is unaffected, because pages are prefetched in the background and cached on the device.

## Kindle protocol

Command responses are **one line of text/plain**, so they can be parsed with `read` in ash.

| Endpoint | Response |
|---|---|
| `GET /k/start` | `ui <state>` |
| `GET /k/screen.png?s=<state>` | PNG |
| `GET /k/tap?s=<state>&x=&y=` | `ui <state>` · `gen <state>` · `read <id> <pages> <page>` · `exit` · `none` |
| `GET /k/generate?s=<state>` | `read …` or `ui <error-state>`; blocks while the story is written |
| `GET /k/menu?id=&pg=` | `ui <menu-state>` |
| `GET /k/story/<id>/<n>.png` | one page as PNG |
| `GET /k/offline.png` | offline screen, cached on the Kindle at start |

`<state>` is base64url JSON (view, selections, page). The server re-validates it on every request
against `wizard.json`; a broken or tampered state falls back to the home screen.

Reader: tapping the **top** 12 % opens the menu, the **left** 35 % goes back, anywhere else goes forward.

JSON API for testing and other clients: `GET /health`, `GET /config`, and `POST /story` with
`{"selections": {...}}` or `{"prompt": "...", "length": "short|medium|long"}`.

## AI providers

The default is `STORY_PROVIDER=claude_cli`. Each story is one call:

```
claude -p <prompt> --output-format json --model claude-opus-5 --effort medium \
       --system-prompt <story rules> --tools "" --strict-mcp-config --no-session-persistence
```

- It authenticates with `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, billed to your Claude subscription.
  A `ANTHROPIC_API_KEY` in the environment is removed before the call on purpose, because it would take precedence.
- There are no tools, no MCP servers and no saved session: every story is a stateless, text-in/text-out call.
- `anthropic` (official SDK, API key, server-side refusal fallbacks), `openai` (Responses API) and
  `fake` (deterministic test text) are alternatives.

## Security

- **Credentials** (OAuth token or API keys) live only in the server's `.env` (chmod 600), never on the Kindle.
- **Device token:** 32 hex characters. It is sent as `Authorization: Bearer` (or `?t=` for BusyBox wget)
  and compared with `hmac.compare_digest`. `install.sh` writes it into the Kindle's `config.sh`.
- **Input:** the Kindle sends only IDs and coordinates. The free-text prompt of the JSON API is limited
  to 300 printable characters.
- **Rate limits** per device: 240 requests/min and `STORIES_PER_HOUR` (default 12). Only one story is
  generated at a time per device.
- **Timeouts:** the CLI call is capped at 150 s with one retry (none on auth errors). The Kindle waits up to 240 s.
- **Logs** contain only method, path, status, duration and an 8-character hash of the device. There are
  no query strings (token, state), no prompts and no story text.
- **Network:**
  - The container publishes its port **only on `LAN_IP`**. Docker's port publishing bypasses ufw,
    so this binding is the real protection. Don't forward the port on your router.
  - Container hardening: `cap_drop: ALL`, `no-new-privileges`, 768 MB memory limit, 256 PIDs, rotated logs.
  - **Remote access (optional):** a public HTTPS endpoint such as Tailscale Funnel pointing only at
    this container. The Kindle tries `BACKEND_URLS` in order (LAN first). Once exposed, the device
    token and the rate limits are the only barrier. Worst case, someone with the token burns your
    story quota; they cannot reach anything else.
- **Kids' stories:** the system prompt requires age-appropriate, non-violent content with a
  comforting ending.

## Display

| Option | Verdict |
|---|---|
| **`eips -g <png>`** (used) | Ships with the stock firmware, shows greyscale PNGs, `-f` forces a full refresh. |
| FBInk | More control over waveforms and faster. Many jailbreaks ship it (`/mnt/us/libkh/bin/fbink`), which makes it a possible upgrade. |
| Raw framebuffer | No benefit over FBInk. |
| WebKit / Mesquite (WAF) | Old engine and hard to debug. |
| KOReader plugin | Viable, but looks like KOReader instead of a dedicated app. |

Ghosting: every `FULL_REFRESH_EVERY` (6) images, and always on the loading and offline screens, the display does a full refresh.
PNGs are quantised to 16 grey levels (what E-Ink can show anyway) and are 15–60 KB each.

## Old hardware notes (PW3, FW 5.13.7)

- **Kernel 3.0.35, ARMv7, 512 MB RAM.** `ktap` is 26 KB, statically linked against musl (so the
  glibc version and soft/hard-float don't matter) and sleeps in `select()`.
- **TLS:** curl 7.76.1 / OpenSSL 1.0.2q handles Let's Encrypt certificates, as verified by the network-test scriptlet.
- **Flash wear:** logs and state live in `/tmp` (RAM). `/mnt/us` is written once per story (pages + two tiny files).
- **Scriptlets** run from `/mnt/us`, which is FAT. `aistory.sh` therefore copies `ktap` to `/tmp` before running it.
- The stock UI keeps running underneath. `ktap` grabs the touchscreen exclusively (EVIOCGRAB), so taps
  don't reach it, and the screensaver is suppressed via `lipc-set-prop com.lab126.powerd preventScreenSaver 1`
  while the app runs.
