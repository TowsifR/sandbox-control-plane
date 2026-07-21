# Sandbox Control Plane — architecture & design

The control plane that makes Temporal actually *drive* the `kind: Sandbox` platform API. It turns
"create a sandbox" into a **durable lifecycle workflow** — provision → wait-ready → live for a TTL →
clean up — and then lets you **open a terminal or chat with the agent** in the running pod, from a browser.

It sits between two systems that already exist in the [`kubernetes-iac`](https://github.com/TowsifR/kubernetes-iac)
platform:

```
browser UI ─┬─ HTTP ───▶ API ──▶ Temporal workflow ──▶ platform.example.io/Sandbox claim
            │                                                   │
            │                         Kyverno admits/denies ◀───┤
            │                                                   ▼
            │                         Crossplane Composition reconciles the bundle
            │                         (namespace · quota · limits · netpol · agent-sandbox pod)
            │                                                   │
            ├─ WebSocket ─▶ API ── pods/exec ─────────────▶ shell in the pod
            └─ HTTP + SSE ─▶ API ── pods/portforward ─────▶ opencode serve (chat)
```

> **Temporal owns the *lifecycle*. Crossplane owns *reconciliation*.** This app never touches the
> bundle directly — it only writes `Sandbox` **claims**, and lets the platform's Composition do the work.
> That boundary is the whole design. The terminal is the one exception: once a pod exists, the API
> execs into it directly — an interactive path, not a declarative one.

## The two moving parts

| Process | File | What it does |
|---|---|---|
| **API** (FastAPI) | `app.py` + `sandboxes/router.py` | create / list / get / delete sandboxes; the terminal WebSocket; Swagger UI at `/docs` |
| **Worker** (Temporal) | `worker.py` | runs the `SandboxLifecycle` workflow and its Kubernetes activities |
| **Frontend** (React + Vite) | `frontend/` | sandbox table, persona tiles + create dialog, an xterm.js terminal, and a chat surface |

API and worker are the **same image**, run with a different command; both connect to Temporal, and the
worker also polls the task queue. The frontend is a separate SPA that talks to the API over `/api`
(a Vite proxy in dev, an ingress in the cluster).

## The lifecycle workflow (`sandboxes/workflows.py`)

`SandboxLifecycle` is a durable state machine. The value Temporal adds is that **every step is
crash-safe** — if the worker dies mid-flight, the workflow resumes from where it left off, and the
cleanup is *guaranteed* to run.

```
create_sandbox_claim
  └─ poll check_sandbox_ready  (bounded: 60 × 3s, else fail — a stuck provision can't hang forever)
       └─ wait_condition(delete-requested OR ttl elapsed)   ← the sandbox "lives" here
            └─ finally: delete_sandbox_claim                 ← runs on EVERY exit path
```

Two things make this correct:

- **The `finally` guarantees cleanup** — whether the sandbox exits via TTL, an early delete, or a
  ready-timeout, the claim is always deleted. That is the reason to use Temporal rather than a cron job
  or a `time.Sleep`: durable, crash-proof teardown.
- **Two exit paths, one mechanism.** `workflow.wait_condition(lambda: self._delete_requested,
  timeout=ttl)` blocks until *either* a `request_delete` **signal** arrives (early delete) *or* the TTL
  **timeout** fires — whichever comes first.

The workflow also exposes a `phase` **query** (`provisioning | running | deleting | deleted`) so the API
can report live status without its own bookkeeping.

## Structure — infra vs domain

```
sandbox_control_plane/
├── core/         config · temporal client · generic kubernetes client   (reusable infra)
├── sandboxes/    router · models · service · gateway · workflows · activities · terminal   (the domain)
├── app.py        FastAPI app
└── worker.py     Temporal worker
frontend/         React + Vite SPA (table · create dialog · xterm.js terminal)
```

- **`gateway.py` is the only `Sandbox`-CRD-aware code** — it speaks `platform.example.io/v1alpha1`
  and nothing else knows the CRD shape. Kept deliberately Temporal-agnostic (no `temporalio` import).
- **Activities wrap the gateway.** The kubernetes client is synchronous, so each call is offloaded with
  `asyncio.to_thread` to avoid blocking the activity event loop.
- **One id threads through everything.** `sb-<hex>` is the claim name **and** the Temporal workflow id
  **and** the API's sandbox id — so `kubectl get sandbox`, the Temporal UI, and the API all line up.
- **`pydantic_data_converter`** lets Pydantic models pass as workflow/activity args directly.

## Error handling — fail fast on rejection, retry on transients

Temporal retries a failing activity forever by default. That's right for *transient* failures and wrong
for *permanent* ones. `create_sandbox_claim` classifies the apiserver's response:

- **A terminal 4xx** (Kyverno policy denial, RBAC forbidden, schema) means the claim can never be
  created — so it raises a **non-retryable** `ApplicationError` and the workflow fails cleanly with the
  reason surfaced (e.g. *"image ubuntu:22.04 is not permitted…"*).
- **429 / 408** (throttling, timeout) and **5xx** stay retryable — the apiserver emits those transiently.

This mirrors how mature retry libraries classify: retry `429`/`408`/`5xx`, treat other `4xx` as fatal.
(`409` never reaches the classifier — the gateway swallows it as idempotent.)

## The terminal (`sandboxes/terminal.py`)

`GET /sandboxes/{id}/terminal` is a WebSocket that gives the browser an interactive shell. The core is
a single **bridge** (`_bridge`) that pumps bytes between the socket and a duplex stream until either
end closes — the shape is deliberately backend-agnostic, so the *same* bridge serves two backends:

| Mode | Backend | For |
|---|---|---|
| **fake** (`SCP_MODE=fake`) | a local pty (`pty.fork`) | UI/dev without a cluster |
| **real** | Kubernetes `pods/exec` into the sandbox pod | the actual product |

The API resolves the pod from the claim's `status.namespace` (never guessed) and a
`platform.example.io/sandbox` label the Composition stamps, then execs `/bin/sh -c` with a one-liner
that lands in **bash** where present and **sh** otherwise — and sets `TERM`, which exec doesn't inject.
On an agent image it first prints how to start the agent (`opencode run <task>`), since opencode's
full-screen TUI doesn't paint over the exec pty.

Details that took real care:

- **Wire protocol:** text frames are keystrokes, binary frames are control JSON (`{cols, rows}`).
  xterm.js only ever sends text, so binary is unambiguous — that's how **resize** reaches the pod's
  pty without a second channel.
- **A dedicated `ApiClient` for exec.** `kubernetes.stream.stream()` monkey-patches the client's
  `request` method to a WebSocket transport while it connects; sharing that client with the REST calls
  would misroute a concurrent `GET /sandboxes`. `core_v1_exec()` hands exec its own client (shared
  `Configuration`, so auth stays single-sourced).
- **The official client mangles its own errors.** On a handshake failure (RBAC denial, bad container)
  it raises `ApiException(body=None)`, and its own error path then calls `.decode()` on that `None` —
  so what actually surfaces is an `AttributeError`. Errors are caught broadly and the apiserver's real
  message is dug out of `__context__`, then drawn **in the terminal** (browsers don't show WS close
  reasons).
- **Teardown order is load-bearing:** stop the reader thread and `join` it *before* closing the exec
  socket — closing an fd another thread is polling is a race.

The frontend adds **copy-on-select and `Ctrl/Cmd+V` paste** (`Ctrl+C` stays as interrupt); clipboard
needs a secure context, so it works on `localhost` and no-ops over plain-HTTP ingress.

## Running the agent

The sandbox image can be `sandbox-opencode` — [OpenCode](https://opencode.ai) on `node:22-slim` (plus
`git` and `python`, so the agent can run what it writes), non-root. It's the image every persona runs on
(see **Personas**), and it runs `opencode serve` as its main process (the chat backend — see **Chat**);
the control plane still execs a shell into it for the terminal. Non-opencode images just idle on `sleep
infinity`. The platform delivers its API key without it ever touching git:

```
key → LocalStack Secrets Manager ──(ESO ClusterExternalSecret, per sandbox ns)──▶ Secret ──▶ OPENCODE_API_KEY
```

A `ClusterExternalSecret` syncs the key into every sandbox namespace, and the Composition mounts it as
`OPENCODE_API_KEY` (required, not optional — the pod waits for it rather than start with a key it could
never pick up). The value lives only in the secret store — the same pattern a real cluster uses with
Secrets Manager + IRSA. LocalStack doesn't persist, so `kubernetes-iac/seed-secrets.sh` re-seeds it
from a gitignored `.env` after a restart.

## Personas — the governed flavor catalog

A **persona** turns "a sandbox" into a *task-scoped, governed* one. Instead of a raw image, the user
picks a persona (what the sandbox is *for*); the platform derives the image and, crucially, **what the
agent is allowed to do** — enforced in the pod where the user can't override it. Two ship:

| Persona | edit | bash | for |
|---|---|---|---|
| `builder` | ✅ | ✅ | writes **and runs** code |
| `architect` | ✅ | ❌ | designs & writes docs; **can't execute** — a `design.md` + a Mermaid diagram |

The governance is **two layers**:

- **Admission** — `persona` is an `enum` on the `Sandbox` XRD, so the apiserver rejects an unknown one
  before anything runs. (A closed set belongs in the schema; the open-ended `image` string is what
  Kyverno guards — right tool per shape.)
- **Runtime** — the Composition renders the persona's OpenCode config as a ConfigMap mounted **read-only
  at `/etc/opencode/`**, which OpenCode treats as *managed* config: highest precedence, **non-overridable**
  by the user inside the pod. So `architect`'s `bash: deny` isn't advice — the agent has no `bash` tool,
  and there's no `opencode.json` the user can write to grant one.

The config is `permission` (the guardrail) + a system prompt (`persona.md`, referenced via OpenCode's
`instructions`) + the model — authored as config-as-data in the Composition's KCL `_personas` catalog.
`persona` and `image` are **mutually exclusive**: a claim carries one or the other and the Composition
uses whichever is present. In the UI, personas are the **golden paths** — featured as tiles on the
landing page with their `edit`/`bash` guardrails shown, while the raw-image flow lives behind the
`Image` toggle in the create dialog.

*Deliberately deferred:* per-persona **skills / MCP** and their **credentials** (the Identity plane) —
the layer that makes a persona distinct beyond its permissions. A `researcher` persona waits for that
(every sandbox already has open egress, so web access alone isn't a differentiator).

## Chat (`sandboxes/chat.py`)

The terminal gives you a shell; **chat** lets you *converse* with the agent and watch its reply stream in.
It's offered for any **opencode** sandbox (a persona, or the opencode image picked directly); other images
are terminal-only. The sandbox table is the console — click a sandbox's **Chat**. The agent is
`opencode serve`, OpenCode's headless HTTP+SSE server, which each opencode pod runs as its main process on
`localhost:4096`; the control plane proxies to it:

- **Transport is `portforward`, not the apiserver pod-`proxy`.** Pod-proxy reaches the pod *over the pod
  network*, so the sandbox's `default-deny-ingress` NetworkPolicy blocks it. Port-forward enters the pod's
  network namespace and connects to `localhost` — bypassing the NetworkPolicy exactly like `exec`, so the
  agent's port is never exposed. Needs `pods/portforward` on the sandbox RBAC.
- **HTTP over the tunnel by hand.** Port-forward hands back a raw socket, so the proxy speaks HTTP with the
  stdlib `http.client` over it (no `httpx`). `chat/sessions`, `…/prompt`, `…/messages` forward opencode's
  JSON verbatim; `…/events` pipes its **SSE** stream straight through to the browser.
- **The tunnel is flaky** — a fresh port-forward intermittently drops, hangs, or truncates a body. Every
  call retries on a fresh tunnel with a short timeout (all calls are quick — a prompt returns at once, its
  reply arriving over SSE), and `create_session` retries as a unit so a garbled body just tries again.
- **Model pin.** `serve` runs sessions on its own default — a *paid* model the free Zen key rejects — and
  ignores the config's `model`, so the proxy pins each session to the free `deepseek-v4-flash-free`. The
  persona's managed config still governs *tools*, so chat is guardrailed like the terminal (architect
  chat can't run bash).

The frontend (`ChatPage`) tracks user messages locally (opencode doesn't echo the prompt) and treats each
SSE event as a refresh signal — refetching the messages (cheap, ~40 ms). The reply isn't token-streamed
(opencode emits it as one event), so a "thinking" indicator covers the model's latency.

## Deployment (`deploy/`, Kustomize)

The app runs in `sandbox-system`; the `Sandbox` claims live in the claim namespace (`default`).

| Concern | Choice | Why |
|---|---|---|
| **RBAC (claims)** | SA in `sandbox-system`, namespaced `Role` in `default`, `RoleBinding` across | Least-privilege — the app can CRUD `Sandbox` claims in one namespace, **not** cluster-admin |
| **RBAC (exec)** | static `ClusterRole` (platform side), bound per-sandbox by the Composition | Exec is scoped to sandbox namespaces and GC'd with them; a `ClusterRoleBinding` would grant a shell in *every* pod |
| **RBAC (chat)** | `pods/portforward` on the same per-sandbox `ClusterRole` | Chat tunnels to the pod's `opencode serve` via port-forward — same scoping as exec, no network exposure |
| **Config** | `configMapGenerator` (hash-suffixed) | Any config change mints a new name → updates Deployment refs → **auto rolling-restart** (a static ConfigMap + `envFrom` goes silently stale) |
| **Image tag** | single-sourced in the `images:` block | bump/retag in one place; the Deployments carry no tag |
| **Image pull** | `imagePullPolicy: IfNotPresent` | image is side-loaded via `kind load` (no registry); `Always` would try to pull and fail |
| **Ingress** | Traefik `IngressRoute` → `sandbox.localtest.me` | API + Swagger UI, consistent with the platform's other routes |

The image is a **uv two-stage Dockerfile** (build the venv in a builder, copy into a clean
`python:3.12-slim`, non-root). `PYTHONUNBUFFERED=1` is set so `kubectl logs` isn't blank — Python
block-buffers stdout when it isn't a tty (a container's log pipe).

## Health & graceful degradation

Temporal is a **hard dependency** — without it the API can't do its job. The current probes both hit
`/openapi.json`, and the lifespan connects to Temporal at startup, so the pod won't go Ready until
Temporal is reachable. That's acceptable because Flux/deploy ordering brings Temporal up first.

The **proper** shape (deferred — see *Next*) separates the two health questions:

- **Liveness** → cheap process check, **never** tied to Temporal. Otherwise a Temporal blip would fail
  liveness on every pod → k8s restarts them all → a dependency hiccup becomes a self-inflicted outage.
- **Readiness** → *should* reflect Temporal (a `/healthz` that pings the client) → a pod that can't
  reach Temporal is pulled from the Service (degraded), but stays alive to recover.
- **Per request** → return `503`, not `500`, when Temporal is unreachable.

## Decisions & gotchas baked in

- **`201`-then-fail on a rejected image.** `POST` returns `201` immediately (the workflow starts before
  the first activity runs), so a claim rejected by Kyverno yields a `201` followed by the workflow
  failing — a later `GET` 404s. Acceptable for now; a synchronous pre-validation would tighten it.
- **Mutable `:dev` tag** is fine for `kind load`, but a GitOps anti-pattern (no change detection). Phase 3
  moves to immutable tags/digests.
- **Claim namespace is defined twice** — the `Role`'s namespace and `SCP_CLAIM_NAMESPACE` must agree.
- **Terminal-too-early race.** `phase` comes from the workflow, which reports `running` when the *claim*
  goes Ready — a beat before the *pod* is Running (an image pull can widen the gap). Clicking the
  terminal in that window returns a clean "pod not found", not a hang. A pod-aware readiness check would
  close it.
- **Every sandbox gets the Zen key** — the `ClusterExternalSecret` matches every sandbox namespace, so
  even a raw busybox sandbox gets a key it ignores. Now that `persona` exists, gating the sync on it
  (only persona sandboxes) is the tidy refinement — deferred.

## Verification (end-to-end, in-cluster)

```bash
kubectl get pods -n sandbox-system                    # api + worker Running/Ready
curl -s -o /dev/null -w '%{http_code}\n' http://sandbox.localtest.me/openapi.json   # 200

# Happy path — claim provisions, then TTL cleans it up:
curl -sX POST http://sandbox.localtest.me/sandboxes \
  -H 'content-type: application/json' -d '{"owner":"alice","size":"small","ttl":90}'
kubectl get sandbox.platform.example.io -n default    # READY=True, then gone after ~90s

# The non-retryable fix — a disallowed image ends FAILED, not stuck retrying:
curl -sX POST http://sandbox.localtest.me/sandboxes \
  -H 'content-type: application/json' -d '{"owner":"eve","image":"ubuntu:22.04","ttl":60}'
kubectl exec -n temporal deploy/temporal-admintools -- \
  temporal workflow describe -w <id> -n default       # Status FAILED (one attempt)

# The terminal — exec into the pod and (on the opencode image) run the agent:
#   open the UI, click the sandbox, or drive the WebSocket directly.
kubectl exec -n sandbox-<id> sandbox -c main -- \
  opencode run --model opencode/deepseek-v4-flash-free "say hi"   # authenticates via OPENCODE_API_KEY

# A persona — its guardrails are enforced by managed config the agent can't override:
curl -sX POST http://sandbox.localtest.me/sandboxes \
  -H 'content-type: application/json' -d '{"owner":"ada","persona":"architect","ttl":300}'
kubectl exec -n sandbox-<id> sandbox -c main -- opencode run "run the shell command ls"
#   → architect refuses: no bash tool (bash: deny), and no local config can grant it

# Chat — a session + prompt proxied to the pod's opencode serve over port-forward (reply streams via SSE):
sid=$(curl -sX POST http://sandbox.localtest.me/sandboxes/<id>/chat/sessions | jq -r .data.id)
curl -sX POST http://sandbox.localtest.me/sandboxes/<id>/chat/sessions/$sid/prompt \
  -H 'content-type: application/json' -d '{"text":"say PONG"}'   # 200; watch .../events for the reply
```

To run the whole thing locally against the cluster: `kubectl port-forward -n temporal
svc/temporal-frontend 7233:7233`, then `uv run python -m sandbox_control_plane.worker`, `uv run uvicorn
sandbox_control_plane.app:app`, and `npm run dev` in `frontend/` (its `/api` proxy targets the API).

## Next

- **GitOps delivery** — push the image to `ghcr.io`, manage this repo's `deploy/` with **Argo CD** (the
  app-delivery plane, alongside the platform's Flux). Immutable image tags/digests.
- **Startup resilience** — lazy Temporal connect + `/healthz` readiness + split liveness + `503`s.
- **Pod-aware readiness** — close the terminal-too-early race by having `running` reflect the pod, not
  just the claim.
- **Per-persona skills & secrets** — MCP servers and their credentials (the Identity plane) per persona;
  and gate the Zen-key sync on `persona` so raw sandboxes don't get it.

## References

- [`kubernetes-iac`](https://github.com/TowsifR/kubernetes-iac) — the platform (Crossplane, Temporal,
  Kyverno, CloudNativePG) this control plane drives.
- `docs/sandbox-control-plane-implementation.md` (in `kubernetes-iac`) — the platform side: the
  `Sandbox` XRD + Crossplane Composition that reconciles the bundle.
- [Temporal Python SDK](https://docs.temporal.io/dev-guide/python) · [Kustomize](https://kustomize.io/)
