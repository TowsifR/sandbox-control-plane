# syntax=docker/dockerfile:1
# sandbox-opencode — the coding-agent image the platform runs inside a Sandbox pod.
# The pod idles; the control plane execs `opencode` (agent) or `bash` (shell) into it.
# The model + provider key are runtime env (e.g. GEMINI_API_KEY) — never baked in.

FROM node:22-slim

# git: agents edit real repos. ca-certificates: TLS to the model provider.
# python3: the builder persona runs the code it writes (node already ships in the base).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates python3 python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g opencode-ai@1.17.20

# node:22-slim already ships `node` at uid 1000 — reuse it; a second uid-1000 user won't create.
# chown up front: WORKDIR would otherwise create the workspace root-owned.
RUN mkdir -p /home/node/workspace && chown node:node /home/node/workspace
USER node
WORKDIR /home/node/workspace

# Idle so the control plane can exec in — Pattern A (shell/agent) and Pattern B (`opencode run`).
CMD ["sleep", "infinity"]
