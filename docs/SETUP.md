# Setup guide

This guide takes you from a stock Kindle to reading AI-generated stories. Each step says what you
should see afterwards. If something looks different, check [Troubleshooting](#troubleshooting).

Plan about an hour: roughly 20 minutes for the server, 20 for the jailbreak and 10 for the Kindle.

## 0. Prerequisites

**Hardware**
- A Kindle with a touchscreen that can be jailbroken. Tested: Kindle Paperwhite 3 (7th gen),
  firmware 5.13.7. Look up your model and firmware at
  [kindlemodding.org → Find my Jailbreak](https://kindlemodding.org).
- An always-on server in your home network with **Docker** and **Docker Compose**.
  A Raspberry Pi 4/5 (64-bit Raspberry Pi OS or Ubuntu Server) is ideal. Any Linux box, or a Mac for testing, works too.
- A USB cable and a computer running macOS or Linux.

**Accounts** (one of these)
- A **Claude subscription** (Pro or Max). The backend uses the Claude Code CLI and logs in with a
  long-lived token from `claude setup-token`. **No API key needed.** This is the default.
- *or* an Anthropic API key (`STORY_PROVIDER=anthropic`)
- *or* an OpenAI API key (`STORY_PROVIDER=openai`)

**On your computer:** `git`, `openssl`, `curl`, and on Linux `rsync` if you want to use `deploy.sh`.

Find your server's LAN IP (e.g. `hostname -I` on the Pi) and give it a **fixed IP / DHCP reservation**
in your router. The Kindle stores this address.

## 1. Server: backend with the Claude CLI

On the server:

```sh
git clone https://github.com/donmb1/ai-story-generator.git ~/ai-story
cd ~/ai-story/deploy/pi
cp env.example .env
chmod 600 .env
openssl rand -hex 16          # → your DEVICE_TOKEN
nano .env                     # set DEVICE_TOKEN and LAN_IP (the server's LAN IP)
```

Build the image and log in to Claude. This opens a login URL: open it in a browser, sign in, and
paste the code back into the terminal. At the end it prints a token starting with `sk-ant-oat…`.

```sh
docker compose build
docker compose run --rm --no-deps story claude setup-token
```

Put the token into `.env` without it showing up in your shell history:

```sh
read -rsp "Token: " T && echo && sed -i "s|^CLAUDE_CODE_OAUTH_TOKEN=.*|CLAUDE_CODE_OAUTH_TOKEN=$T|" .env
docker compose up -d
```

**Check:**

```sh
curl http://<LAN_IP>:8787/health
# {"ok":true,"provider":"claude_cli"}

T=<DEVICE_TOKEN>
curl -s -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"selections":{"genre":"kinder","alter":"6-8","laenge":"kurz","thema":"dinos"}}' \
  http://<LAN_IP>:8787/story | head -c 400
# {"id":"…","title":"…","story":"Es war einmal …","model":"claude-opus-5","pages":8}
```

The first story takes about 20–40 seconds. If you see `Claude-Anmeldung ungültig`, the token is missing or wrong.

> Using an API key instead: set `STORY_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=…` in `.env`
> (or `openai` / `OPENAI_API_KEY`) and skip `setup-token`.
>
> The container listens **only on `LAN_IP`**, not on all interfaces. Docker's port publishing
> bypasses host firewalls such as ufw, so this binding is what keeps it private.

## 2. Jailbreak the Kindle

Follow **[kindlemodding.org](https://kindlemodding.org)** for your exact model and firmware.
This repo intentionally contains no jailbreak steps: they depend on the firmware and change over time.

The tested path was **WinterBreak** on a PW3 with firmware 5.13.7:
- Afterwards `documents/JAILBROKEN.txt` exists on the Kindle.
- Automatic updates are blocked by the jailbreak.
- "Scriptlets" work: every `.sh` file in `documents/` shows up in the library as a book and runs when you tap it.
- KUAL/MRPI are **not** needed with these modern jailbreaks (kindlemodding.org calls KUAL obsolete).

Before the jailbreak is complete, keep the Kindle in airplane mode so it can't update itself.

## 3. Install the app on the Kindle

On your computer, in your clone of this repo:

```sh
cp backend/.env.example backend/.env
nano backend/.env
#   DEVICE_TOKEN=<same value as on the server>
#   KINDLE_BACKEND_URLS="http://<LAN_IP>:8787"
```

Connect the Kindle via USB. It mounts as `/Volumes/Kindle` on macOS; on Linux usually
`/media/$USER/Kindle`, so set `KINDLE=/media/$USER/Kindle`. Then:

```sh
./kindle/install.sh
# Installiert.
# BACKEND_URLS="http://<LAN_IP>:8787"
# …/documents/ai_story.sh … hello_world.sh …
```

Eject the Kindle. The library now shows six new "books":

| Scriptlet | What you should see |
|---|---|
| **Hello World** | "Hello World" and the date at the top left, in a blocky font |
| **Hello - Systeminfo** | writes `hello.log` to the Kindle root |
| **AI Story - Netztest** | tests HTTPS and your backend, writes `aistory/nettest.log` |
| **AI Story - Touch-Test** | tap top-left, top-right, bottom-left and the coordinates appear |
| **AI Story** | the app |
| **AI Story - Beenden (Notfall)** | stops the app if it ever gets stuck |

## 4. Test the display and touch

1. Tap **Hello World**. If text appears, the display path (`eips`) works.
2. Turn on Wi-Fi, then tap **AI Story - Netztest** and wait for "Netztest fertig". Connect via USB
   and check `aistory/nettest.log`: the `backend …/health` line should show `{"ok":true,…}`.
3. Tap **AI Story - Touch-Test** and tap the three corners in order. Expected values are roughly
   `0 0`, `1071 0` and `0 1447`. If the axes are wrong, set `TOUCH_FLAGS` in `/mnt/us/aistory/app/config.sh`:
   `-s` swaps x/y, `-x` mirrors left/right, `-y` mirrors top/bottom. You can combine them.
   `install.sh` keeps your value on later installs.

## 5. Read your first story

Tap **AI Story**. You should see **"Was möchtest du lesen?"** with four buttons:

- **Geschichte zusammenstellen:** story type → (age) → length → theme → hero → mood → message → **Geschichte erzeugen**
- **Überrasch mich:** a random story in one tap
- **Letzte Geschichten:** stories generated before
- **Beenden:** back to the Kindle library

While reading: tap the **right** side for the next page, the **left** side to go back, and the **top** strip for the menu.
After the last page the menu opens automatically. The app quits by itself after 30 minutes without a tap.

## 6. Optional: use it outside your home network

The Kindle tries each address in `KINDLE_BACKEND_URLS` in order and uses the first that answers.
To make it work anywhere, add a public HTTPS address. With **Tailscale Funnel** on the server:

```sh
# once: enable Funnel for your tailnet (the command prints a link if needed)
sudo tailscale funnel --bg --https=10000 http://<LAN_IP>:8787
tailscale funnel status          # https://<machine>.<tailnet>.ts.net:10000 (Funnel on)
```

Then on your computer:

```sh
# backend/.env
KINDLE_BACKEND_URLS="http://<LAN_IP>:8787 https://<machine>.<tailnet>.ts.net:10000"
./kindle/install.sh
```

The public DNS name can take 10+ minutes to appear. The Kindle's curl (7.76 / OpenSSL 1.0.2 on
FW 5.13.7) handles Let's Encrypt certificates fine; **AI Story - Netztest** checks it on your device.
A phone hotspot then works, since the Kindle only needs internet access.

⚠️ This makes the backend reachable from the internet. It is protected by the device token (sent as
a header over HTTPS) and rate limits (`STORIES_PER_HOUR`), and Claude has no tools there. Treat the
token like a password; to turn Funnel off, run `sudo tailscale funnel --https=10000 off`.

## Customising

| What | Where |
|---|---|
| Themes, steps, kids' names | `backend/app/wizard.json` (`"names": [...]` shows up as hero buttons) |
| Story style and safety rules | `SYSTEM_PROMPT` in `backend/app/llm.py` |
| Model, speed | `ANTHROPIC_MODEL`, `ANTHROPIC_EFFORT` (`low` is faster) in the server `.env` |
| Fonts, sizes, margins | `backend/app/render.py` |
| Kindle behaviour (idle timeout, refresh, Wi-Fi) | `kindle/device/app/config.sh`, then rerun `install.sh` |
| Other screen size | `SCREEN_W` / `SCREEN_H` in the server `.env` **and** in `kindle/device/app/config.sh` |

After changing backend code on the server, run `git pull && docker compose up -d --build`.
If you develop on your computer, `PI=user@server ./deploy/pi/deploy.sh` syncs and rebuilds.

## Development

```sh
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # tests (use the fake provider, no AI calls)
cp .env.example .env && ./run.sh       # local backend on :8787, STORY_PROVIDER=fake for test stories

cd ../kindle
sim/run-sim.sh happy                   # runs the Kindle client in BusyBox (Docker) against it
./build-ktap.sh                        # rebuilds the ARMv7 touch helper (Docker, QEMU)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Scriptlets don't show up | Wait a moment or reopen the library. Check that the files are in `documents/` and end in `.sh`. |
| "Keine Verbindung zum Server" | Is the Kindle on Wi-Fi? Does `curl http://<LAN_IP>:8787/health` work from another device? Is the IP in `KINDLE_BACKEND_URLS` right? Run **Netztest**. |
| Taps land in the wrong place | Run **Touch-Test** and set `TOUCH_FLAGS`. |
| Kindle UI draws over the app | Set `STOP_FRAMEWORK=1` in `config.sh` (experimental: stops the Kindle UI while the app runs). |
| "Claude-Anmeldung ungültig" | Token missing or expired: run `claude setup-token` again (step 1). |
| Story takes very long | Lower `ANTHROPIC_EFFORT` to `low`, or pick a shorter length. |
| App seems stuck | Tap **AI Story - Beenden (Notfall)**, or hold the power button for about 40 s to restart. |
| Logs | Kindle: `/tmp/aistory/aistory.log` (RAM, gone after a reboot). Server: `docker logs ai-story`. |
