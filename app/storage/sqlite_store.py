import json
import sqlite3
from pathlib import Path
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
