import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .engine import claims_from_pages, digest, extract
from .fixtures import RECORDS, create_pdf


def root() -> Path:
    path = Path(os.environ.get("CLAIMTRAIL_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
    path.mkdir(parents=True, exist_ok=True)
    (path / "originals").mkdir(exist_ok=True)
    return path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    connection = sqlite3.connect(root() / "claimtrail.sqlite3", timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def audit(connection, action: str, target: str, detail: dict | None = None):
    connection.execute("INSERT INTO audit(actor,action,target,detail,created_at) VALUES(?,?,?,?,?)",
                       ("demo-reviewer", action, target, json.dumps(detail or {}), now()))


def initialise():
    with db() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, collection_id TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY, document_id TEXT, created_at TEXT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, investigation_id TEXT REFERENCES investigations(id), target_id TEXT,
          action TEXT, relationship TEXT, reason TEXT, actor TEXT, evidence_hashes TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT, action TEXT, target TEXT, detail TEXT, created_at TEXT);
        """)
        existing = {row[0] for row in connection.execute("SELECT id FROM documents")}
        for record in RECORDS:
            identifier, title, date, creator, _ = record
            if identifier in existing:
                continue
            path = root() / "originals" / f"{identifier}.pdf"
            create_pdf(path, record)
            data = path.read_bytes()
            pages = extract(data, ".pdf")
            if identifier == "CT-019":
                # This warning is fixture metadata identifying a visible handwritten ambiguity.
                pages[0]["uncertain"] = True
                pages[0]["uncertainty_note"] = "Handwritten ‘3?’ is ambiguous. Review the original scan; it is not a confirmed correction."
            document = {"id": identifier, "title": title, "date": date, "creator": creator,
                        "institution": "Fictional Public Works Archive", "record_id": identifier,
                        "collection_id": "demo", "filename": path.name, "hash": digest(data), "pages": pages,
                        "synthetic": True, "availability": "Full content", "source_url": None, "extraction_revision": 1}
            save_document(connection, document)
        # An inaccessible collection exercises the boundary without leaking it through list/search/export.
        if "PRIVATE-001" not in existing:
            connection.execute("INSERT INTO documents VALUES(?,?,?)", ("PRIVATE-001", "restricted", json.dumps({"id": "PRIVATE-001", "title": "Restricted record"})))


def save_document(connection, document: dict):
    connection.execute("INSERT INTO documents VALUES(?,?,?)", (document["id"], document["collection_id"], json.dumps(document)))
    claims = claims_from_pages(document["pages"], document["id"])
    for claim in claims:
        connection.execute("INSERT INTO claims VALUES(?,?,?)", (claim["id"], document["id"], json.dumps(claim)))
    audit(connection, "Record indexed", document["id"], {"hash": document["hash"], "claim_count": len(claims), "revision": 1})


def document_for(connection, identifier: str) -> dict | None:
    row = connection.execute("SELECT payload FROM documents WHERE id=? AND collection_id='demo'", (identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def all_claims(connection) -> list[dict]:
    return [json.loads(row[0]) for row in connection.execute("SELECT c.payload FROM claims c JOIN documents d ON d.id=c.document_id WHERE d.collection_id='demo'")]


def doc_claims(connection, identifier: str) -> list[dict]:
    return [c for c in all_claims(connection) if c["document_id"] == identifier]
