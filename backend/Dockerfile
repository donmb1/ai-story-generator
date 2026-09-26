# AI Story Reader – Backend mit Claude Code CLI (Anmeldung per OAuth-Token, kein API-Key).
# Claude läuft hier ohne Werkzeuge: nur Text rein, Text raus.
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Bewusst gepinnt; zum Aktualisieren anheben und neu bauen
ARG CLAUDE_CODE_VERSION=2.1.280
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} && npm cache clean --force

WORKDIR /app
COPY requirements.txt ./
RUN python3 -m venv /venv \
 && /venv/bin/pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY fonts ./fonts

# uid 1000 = node im Image; umbenennen statt zweiten Nutzer anlegen
RUN usermod -l story -d /home/story -m node && groupmod -n story node \
 && mkdir -p /data /home/story/.claude && chown -R story:story /data /home/story

USER 1000:1000
ENV STORY_PROVIDER=claude_cli DATA_DIR=/data HOME=/home/story CLAUDE_CWD=/tmp
EXPOSE 8787
HEALTHCHECK --interval=60s --timeout=5s CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8787/health')"
CMD ["/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--no-access-log"]
