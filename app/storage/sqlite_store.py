import json
import sqlite3
from pathlib import Path
from typing import Any, Dict
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

    def handle_slack_action(self, payload_str: str, k8s_actions) -> str:
        payload = _json.loads(payload_str)
        actions = payload.get("actions", [])
        if not actions:
            return "No action in Slack payload."

        action = actions[0]
        action_id = action.get("action_id")
        incident_id = action.get("value")

        if not incident_id:
            return "Missing incident_id."

        incident = self._get_incident(incident_id)
        ns = incident["namespace"]
        svc = incident["service"]

        if action_id == "reject_action":
            self._audit(incident_id, "reject", "rejected", "User rejected action")
            return f"❌ Action rejected for incident `{incident_id}`."

        if action_id == "approve_rollout_restart":
            deployment = svc  # MVP mapping: deployment == service
            self._audit(incident_id, "rollout_restart", "approved", f"Approved restart for {deployment} in {ns}")
            try:
                msg = k8s_actions.rollout_restart_deployment(namespace=ns, deployment=deployment)
                self._audit(incident_id, "rollout_restart", "executed", msg)
                return f"{msg}\nIncident `{incident_id}`: {incident['title']}"
            except Exception as e:
                self._audit(incident_id, "rollout_restart", "failed", str(e))
                return f"⚠️ Restart failed for incident `{incident_id}`: {e}"

        return f"Unknown Slack action: {action_id}"
