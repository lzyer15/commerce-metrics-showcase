"""Selected production Store methods, unchanged. No platform transport included."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from core import MetricsError, days

# Source constants used by Store.save; their production values are retained.
SHEET_BASIS = "oriena_sheet_v2"
SMARTSTORE_BASIS = "smartstore_initial_product_payment_v1"

class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, brand TEXT NOT NULL, platform TEXT NOT NULL,
            account TEXT NOT NULL, since TEXT NOT NULL, until TEXT NOT NULL,
            status TEXT NOT NULL, code TEXT, collected_at TEXT NOT NULL,
            mode TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records (
            brand TEXT NOT NULL, platform TEXT NOT NULL, account TEXT NOT NULL,
            kind TEXT NOT NULL, source_id TEXT NOT NULL, payload TEXT NOT NULL,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            PRIMARY KEY(brand, platform, account, kind, source_id));
        CREATE TABLE IF NOT EXISTS coverage (
            brand TEXT NOT NULL, platform TEXT NOT NULL, account TEXT NOT NULL,
            day TEXT NOT NULL, complete_metrics TEXT NOT NULL, issues TEXT NOT NULL,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            PRIMARY KEY(brand, platform, account, day));
        CREATE TABLE IF NOT EXISTS reconciliations (
            brand TEXT NOT NULL, platform TEXT NOT NULL, account TEXT NOT NULL,
            day TEXT NOT NULL, metric TEXT NOT NULL, expected TEXT NOT NULL,
            fingerprint TEXT NOT NULL, evidence TEXT NOT NULL, verified_at TEXT NOT NULL,
            PRIMARY KEY(brand, platform, account, day, metric));
        CREATE TABLE IF NOT EXISTS collection_evidence (
            run_id INTEGER PRIMARY KEY REFERENCES runs(id), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_gaps (
            brand TEXT NOT NULL, platform TEXT NOT NULL, account TEXT NOT NULL,
            source_id TEXT NOT NULL, payload TEXT NOT NULL,
            detected_run_id INTEGER NOT NULL REFERENCES runs(id),
            resolved_run_id INTEGER REFERENCES runs(id),
            PRIMARY KEY(brand, platform, account, source_id));
        """)

    def close(self):
        self.db.close()

    def _run(self, brand, platform, account, since, until, status, code, mode):
        return self.db.execute("""INSERT INTO runs
            (brand,platform,account,since,until,status,code,collected_at,mode)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (brand, platform, account, since, until, status, code,
             datetime.now(timezone.utc).isoformat(), mode)).lastrowid

    def save(self, brand, batch):
        batch.validate()
        prefix = (brand, batch.platform, batch.account)
        # A demo database cannot contaminate live state, in either direction.
        modes = {r[0] for r in self.db.execute("SELECT DISTINCT mode FROM runs")}
        if modes and modes != {batch.mode}:
            raise MetricsError("demo_live_database_mismatch")
        with self.db:
            run_id = self._run(*prefix, batch.since, batch.until, "success", None, batch.mode)
            self.db.execute("INSERT INTO collection_evidence VALUES (?,?)",
                            (run_id, json.dumps(batch.evidence)))
            if batch.platform in ("meta", "naver_search"):
                # A complete response may legitimately remove previously returned ads.
                self.db.execute("""DELETE FROM records WHERE brand=? AND platform=?
                    AND account=? AND kind='ad'
                    AND json_extract(payload, '$.date') BETWEEN ? AND ?""",
                    prefix + (batch.since, batch.until))
            for record in batch.records:
                self.db.execute("""INSERT INTO records VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(brand,platform,account,kind,source_id)
                    DO UPDATE SET payload=excluded.payload,run_id=excluded.run_id""",
                    prefix + (record["kind"], record["id"], json.dumps(record), run_id))
                if (batch.platform == "smartstore" and batch.mode == "live"
                        and batch.evidence.get("identity", {}).get("account_id") == batch.account
                        and batch.evidence.get("gross_basis_accepted") is True
                        and record.get("source", {}).get("revenue_basis") == SMARTSTORE_BASIS):
                    payments = [e for e in record["events"] if e["kind"] == "payment"]
                    gap = self.db.execute("SELECT payload FROM source_gaps WHERE brand=? AND platform=? AND account=? AND source_id=? AND resolved_run_id IS NULL",
                                          prefix + (record["id"],)).fetchone()
                    if gap and len(payments) == 1 and json.loads(gap[0])["payment_days"] in ([], [payments[0]["date"]]):
                        self.db.execute("UPDATE source_gaps SET resolved_run_id=? WHERE brand=? AND platform=? AND account=? AND source_id=?",
                                        (run_id,) + prefix + (record["id"],))
            for day in days(batch.since, batch.until):
                self.db.execute("""INSERT INTO coverage VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(brand,platform,account,day) DO UPDATE SET
                    complete_metrics=excluded.complete_metrics, issues=excluded.issues,
                    run_id=excluded.run_id""", prefix +
                    (day, json.dumps(batch.complete_metrics), json.dumps(batch.issues), run_id))
        return run_id
