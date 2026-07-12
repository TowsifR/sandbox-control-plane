# sandbox-control-plane

A Temporal-backed control plane for the `kind: Sandbox` platform API. It turns "create a sandbox" into
a **durable lifecycle workflow** — provision → wait-ready → live for a TTL → clean up — that survives
crashes and restarts.

- **API** (FastAPI) — create / list / get / delete sandboxes; Swagger UI at `/docs`.
- **Worker** (Temporal) — runs the `SandboxLifecycle` workflow and its Kubernetes activities.
- It creates `platform.example.io` `Sandbox` **claims**; Crossplane reconciles the actual bundle
  (namespace / quota / netpol / pod). Temporal owns the *lifecycle*; Crossplane owns *reconciliation*.

## Layout

```
sandbox_control_plane/
├── core/         config · temporal client · generic kubernetes client   (reusable infra)
├── sandboxes/    router · models · service · gateway · workflows · activities   (the domain)
├── app.py        FastAPI app (includes the sandboxes router)
└── worker.py     Temporal worker (registers the workflow + activities)
```

## Prerequisites

- The KinD platform cluster running — the `Sandbox` CRD (Crossplane) and Temporal installed (see the
  `kubernetes-iac` repo).
- [`uv`](https://docs.astral.sh/uv/), and a kubeconfig pointing at that cluster.

## Run (locally, against the cluster)

```bash
# 1. Temporal frontend — leave running
kubectl port-forward -n temporal svc/temporal-frontend 7233:7233

# 2. Worker — new terminal
uv run python -m sandbox_control_plane.worker

# 3. API — new terminal
uv run uvicorn sandbox_control_plane.app:app --reload

# 4. Swagger UI
open http://localhost:8000/docs
```

## Try it

`POST /sandboxes` with `{"owner": "alice", "size": "small", "ttl": 120}` → returns a sandbox id
(`sb-…`, which is also the Temporal workflow id). Watch it in the Temporal Web UI and via
`kubectl get sandbox`; after ~120s the workflow deletes the claim and Crossplane garbage-collects the
bundle. `DELETE /sandboxes/{id}` expires it early (signals the workflow).

## Config (env vars, `SCP_` prefix)

| var | default | |
|---|---|---|
| `SCP_TEMPORAL_ADDRESS` | `localhost:7233` | Temporal frontend (port-forward for local) |
| `SCP_TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `SCP_TASK_QUEUE` | `sandbox-lifecycle` | must match between API and worker |
| `SCP_CLAIM_NAMESPACE` | `default` | namespace the `Sandbox` claims are created in |
