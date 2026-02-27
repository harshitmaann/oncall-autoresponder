import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
import json as _json
from app.core.schemas import Incident

DB_PATH = Path("incidents.db")

class IncidentStore:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            title TEXT,
            severity TEXT,
            service TEXT,
            namespace TEXT,
            alertname TEXT,
            started_at TEXT,
            source TEXT,
            env TEXT,
            raw_json TEXT,
            evidence_json TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS action_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT,
            action_type TEXT,
            status TEXT,
            detail TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        self.conn.commit()
        self._migrate_incidents_columns()

    def _migrate_incidents_columns(self) -> None:
        # Add slack_channel_id + slack_message_ts if missing
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(incidents)")
        cols = {row[1] for row in cur.fetchall()}

        if "slack_channel_id" not in cols:
            cur.execute("ALTER TABLE incidents ADD COLUMN slack_channel_id TEXT")
        if "slack_message_ts" not in cols:
            cur.execute("ALTER TABLE incidents ADD COLUMN slack_message_ts TEXT")

        self.conn.commit()

    def upsert_incident(self, incident: Incident) -> None:
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO incidents
        (incident_id, title, severity, service, namespace, alertname, started_at, source, env, raw_json, evidence_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET
            title=excluded.title,
            severity=excluded.severity,
            service=excluded.service,
            namespace=excluded.namespace,
            alertname=excluded.alertname,
            started_at=excluded.started_at,
            source=excluded.source,
            env=excluded.env,
            raw_json=excluded.raw_json,
            evidence_json=excluded.evidence_json
        """, (
            incident.incident_id,
            incident.title,
            incident.severity,
            incident.service,
            incident.namespace,
            incident.alertname,
            incident.started_at,
            incident.source,
            incident.env,
            json.dumps(incident.raw),
            json.dumps(incident.evidence),
        ))
        self.conn.commit()

    def set_slack_meta(self, incident_id: str, slack_channel_id: str, slack_message_ts: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE incidents SET slack_channel_id=?, slack_message_ts=? WHERE incident_id=?",
            (slack_channel_id, slack_message_ts, incident_id),
        )
        self.conn.commit()

    def get_slack_meta(self, incident_id: str) -> Optional[Dict[str, str]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT slack_channel_id, slack_message_ts FROM incidents WHERE incident_id=?",
            (incident_id,),
        )
        row = cur.fetchone()
        if not row or not row[0] or not row[1]:
            return None
        return {"channel": row[0], "ts": row[1]}

    def _get_incident(self, incident_id: str) -> Dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT incident_id,title,severity,service,namespace,alertname,evidence_json FROM incidents WHERE incident_id=?",
            (incident_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Incident not found: {incident_id}")
        return {
            "incident_id": row[0],
            "title": row[1],
            "severity": row[2],
            "service": row[3],
            "namespace": row[4],
            "alertname": row[5],
            "evidence": _json.loads(row[6] or "{}"),
        }

    def _audit(self, incident_id: str, action_type: str, status: str, detail: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO action_audit (incident_id, action_type, status, detail) VALUES (?,?,?,?)",
            (incident_id, action_type, status, detail),
        )
        self.conn.commit()

    def _already_executed(self, incident_id: str, action_type: str) -> bool:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT 1 FROM action_audit WHERE incident_id=? AND action_type=? AND status='executed' LIMIT 1",
            (incident_id, action_type),
        )
        return cur.fetchone() is not None

    def handle_slack_action(self, payload_str: str, k8s_actions) -> Dict[str, Any]:
        """
        Returns a dict so the caller can:
        - post a follow-up message (text)
        - update the original message (remove buttons)
        """
        payload = _json.loads(payload_str)
        actions = payload.get("actions", [])
        if not actions:
            return {"text": "No action in Slack payload."}

        action = actions[0]
        action_id = action.get("action_id")
        incident_id = action.get("value")

        if not incident_id:
            return {"text": "Missing incident_id."}

        approver_id = (payload.get("user") or {}).get("id") or ""
        approver_name = (payload.get("user") or {}).get("username") or ""
        approver = approver_name or approver_id or "unknown"

        incident = self._get_incident(incident_id)
        ns = incident["namespace"]
        svc = incident["service"]

        if action_id == "reject_action":
            self._audit(incident_id, "reject", "rejected", f"rejected_by={approver}")
            return {
                "text": f"❌ Action rejected for incident `{incident_id}`.",
                "update": {"incident_id": incident_id, "status": f"Rejected by {approver}"},
            }

        if action_id == "approve_rollout_restart":
            deployment = svc  # MVP mapping: deployment == service

            if self._already_executed(incident_id, "rollout_restart"):
                return {
                    "text": f"✅ Rollout restart already executed for incident `{incident_id}`.",
                    "update": {"incident_id": incident_id, "status": "Already executed"},
                }

            self._audit(
                incident_id,
                "rollout_restart",
                "approved",
                f"approved_by={approver} deployment={deployment} namespace={ns}",
            )
            try:
                msg = k8s_actions.rollout_restart_deployment(namespace=ns, deployment=deployment)
                self._audit(incident_id, "rollout_restart", "executed", msg)

                verify = k8s_actions.verify_deployment(namespace=ns, deployment=deployment, wait_seconds=30)
                verdict = "✅ Verification PASS" if verify["ok"] else "❌ Verification FAIL"
                details = (
                    f"- rollout: desired={verify['desired']} updated={verify['updated']} "
                    f"ready={verify['ready']} available={verify['available']}\n"
                    f"- pods: {verify['pod_count']} max_restarts={verify['max_restarts']}\n"
                    f"- restartedAt: {verify['restarted_at']}"
                )
                self._audit(incident_id, "verify", "pass" if verify["ok"] else "fail", details)

                return {
                    "text": f"{msg}\n{verdict}\n{details}\nIncident `{incident_id}`: {incident['title']}",
                    "update": {"incident_id": incident_id, "status": f"Approved by {approver}"},
                }
            except Exception as e:
                self._audit(incident_id, "rollout_restart", "failed", str(e))
                return {"text": f"⚠️ Restart failed for incident `{incident_id}`: {e}"}

        return {"text": f"Unknown Slack action: {action_id}"}
