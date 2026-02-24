# On-call Autoresponder (Kubernetes + Slack)

An on-call autoresponder that ingests **Alertmanager** alerts, posts a structured incident brief in **Slack**, and (with explicit approval) executes a safe **Kubernetes** mitigation like **rollout restart** — then verifies rollout health and records an audit trail.

**Goal:** reduce on-call toil and MTTR by turning alerts into **actionable, verified, and auditable** responses.

---

## What it does

### 1) Ingest alerts
- Receives alerts from **Alertmanager** via webhook: `POST /webhooks/alertmanager`
- Normalizes the payload into an internal `Incident` record

### 2) Triage + evidence (K8s)
- Collects basic Kubernetes evidence (pods/events) for the impacted service/namespace (when kube access is available)
- Persists incidents and actions to a local SQLite DB (`incidents.db`)

### 3) Slack incident brief + approvals
- Posts an incident summary into Slack with interactive buttons:
  - **Approve: Rollout Restart**
  - **Reject**
- Verifies interactive requests using Slack request signatures

### 4) Safe execution (approval-gated)
- On approval, triggers a real Kubernetes rollout restart by patching:
  `spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"]`
- Scopes actions with environment guardrails:
  - `ALLOWED_NAMESPACES`
  - `ALLOWED_ACTIONS`

### 5) Verification loop
- After execution, verifies rollout and readiness:
  - desired/updated/ready/available replicas
  - pod count + max container restarts
  - `restartedAt` timestamp
- Posts **Verification PASS/FAIL** back into Slack

### 6) Audit trail
- Records approvals/execution/verification to SQLite (`action_audit` table)

---

## Architecture (high level)

**Alertmanager → FastAPI webhook → Incident store (SQLite) → Slack message w/ buttons → Slack interactive endpoint → K8S executor → verify → Slack follow-up**

Key endpoints:
- `POST /webhooks/alertmanager` — ingest Alertmanager alerts
- `POST /integrations/slack/actions` — handle Slack button clicks (Approve/Reject)

---

## Tech stack
- Python + FastAPI
- Slack Block Kit (interactive buttons) + request signature verification
- Kubernetes Python client
- SQLite (incidents + action audit)
- pytest (sanity tests)

---

## Repository structure

```
app/
  api/                  # Alert webhooks (Alertmanager)
  core/                 # Incident logic + schemas
  collectors/           # Evidence collectors (K8s)
  executor/             # Guardrailed K8s actions + verification
  integrations/         # Slack notifier + interactive handler
  runbooks/             # (WIP) incident classification/router
  storage/              # SQLite incident + audit store
assets/                 # (Optional) screenshots for README
tests/
.github/workflows/      # CI
```

---

## Setup (local)

### 1) Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### 2) Configure environment

```bash
cp .env.example .env
```

Fill in the required Slack values in `.env`:
- `SLACK_BOT_TOKEN` (xoxb-…)
- `SLACK_SIGNING_SECRET`
- `SLACK_CHANNEL_ID` (C…)

Safety guardrails:
- `ALLOWED_NAMESPACES=default,staging`
- `ALLOWED_ACTIONS=rollout_restart`

> ⚠️ Never commit `.env` (it contains secrets).

---

## Run the service

```bash
uvicorn app.main:app --reload --port 8000
```

---

## Expose localhost to Slack (ngrok)

Slack can’t call `localhost`. Run:

```bash
ngrok http 8000
```

Set your Slack App **Interactivity & Shortcuts → Request URL** to:

```
https://<YOUR-NGROK-URL>/integrations/slack/actions
```

---

## Create a demo Kubernetes target

This project’s demo path assumes a deployment name matches the `service` label (e.g., `api`).

```bash
kubectl create deployment api --image=nginx
kubectl rollout status deployment/api
```

---

## Trigger a test alert

```bash
curl -X POST http://localhost:8000/webhooks/alertmanager \
  -H "Content-Type: application/json" \
  -d '{
    "status":"firing",
    "alerts":[{"status":"firing","labels":{"alertname":"High5xxErrorRate","service":"api","namespace":"default","severity":"critical"}}],
    "commonLabels":{}
  }'
```

Expected flow:
1) Slack incident message posts with **Approve / Reject**
2) Click **Approve** → bot triggers rollout restart
3) Bot posts **Verification PASS/FAIL** with rollout + pod health details

---

## Safety model

- **Approval required** for execution (no autopilot by default)
- Actions constrained by:
  - `ALLOWED_ACTIONS`
  - `ALLOWED_NAMESPACES`
- Full audit trail for approvals/execution/verification

---

## Roadmap (next YC-level upgrades)

- Deployment auto-discovery by labels (stop assuming deployment == service)
- Least-privilege RBAC + in-cluster deployment manifests
- Runbook engine (YAML-based) with ranked hypotheses + step-by-step actions
- Change correlation (deploy/config diffs) to pinpoint “what changed?”
- Replay protection + one-time action tokens + disable buttons after use
- Optional integrations: Prometheus queries, log signatures (Loki), incident summaries

---

## License

MIT (update as needed)