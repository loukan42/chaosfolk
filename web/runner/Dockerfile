# Disposable audit container: Chaosfolk, Chromium and OpenCode. Build from the repository root:
#   docker build -f web/runner/Dockerfile -t chaosfolk-runner .
FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm

# Pin this in production once a run has been checked with that version.
ARG OPENCODE_VERSION=latest

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && npm install -g "opencode-ai@${OPENCODE_VERSION}" \
 && npm cache clean --force

# The wheel bundles the skill (SKILL.md and its guides) used by `chaosfolk setup`.
COPY . /src/chaosfolk
RUN pip install /src/chaosfolk \
 && python -m playwright install --with-deps chromium \
 && rm -rf /src/chaosfolk /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 audit
COPY web/runner/prompt.md /opt/chaosfolk/prompt.md
COPY web/runner/run-audit.sh /usr/local/bin/run-audit
COPY web/runner/opencode.json /home/audit/.config/opencode/opencode.json
RUN chmod 0755 /usr/local/bin/run-audit \
 && chown -R audit:audit /home/audit

USER audit
RUN chaosfolk setup --agent opencode --skip-browser

WORKDIR /work
ENTRYPOINT ["run-audit"]
