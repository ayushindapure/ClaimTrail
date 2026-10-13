import io
import json
import re
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import pymupdf as fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .engine import ENGINE_VERSION, claims_from_pages, digest, extract, relationship
from .store import all_claims, audit, db, doc_claims, document_for, initialise, now, root, save_document


@asynccontextmanager
async def lifespan(app):
    initialise()
    yield


app = FastAPI(title="ClaimTrail API", version="0.1.0", lifespan=lifespan)
MAX_BYTES = 15 * 1024 * 1024


class Start(BaseModel):
    document_id: str = "CT-006"


class URLInput(BaseModel):
    url: str = Field(max_length=2048)


class Review(BaseModel):
    target_id: str
    action: str
    relationship: str
    reason: str = Field(min_length=3, max_length=1500)


def require_doc(connection, identifier):
    document = document_for(connection, identifier)
    if not document:
        raise HTTPException(404, "Record unavailable under your current access.")
    return document


def require_investigation(connection, identifier):
    row = connection.execute("SELECT * FROM investigations WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise HTTPException(404, "Investigation not found.")
    if row["document_id"]:
        require_doc(connection, row["document_id"])
    return row


def public_doc(document):
    return {key: value for key, value in document.items() if key != "pages"} | {
        "page_count": len(document["pages"]), "methods": sorted({p["method"] for p in document["pages"]}),
        "uncertain": any(p["uncertain"] for p in document["pages"]),
    }


def results(connection, investigation_id, focus_id=None):
    investigation = require_investigation(connection, investigation_id)
    payload = json.loads(investigation["payload"])
    if not investigation["document_id"]:
        return payload | {"id": investigation_id, "claims": [], "matches": [], "history": []}
    document = require_doc(connection, investigation["document_id"])
    claims = doc_claims(connection, document["id"])
    focus = next((c for c in claims if c["id"] == focus_id), claims[0] if claims else None)
    matches = []
    reviews = connection.execute("SELECT * FROM reviews WHERE investigation_id=? ORDER BY id", (investigation_id,)).fetchall()
    decisions = {row["target_id"]: dict(row) for row in reviews}
    for claim in all_claims(connection) if focus else []:
        if claim["document_id"] == document["id"]:
            continue
        # Bounded retrieval: same subject, or the same cost with a lookalike context.
        if claim["subject"] != focus["subject"] and claim["amount"] not in {focus["amount"], focus["old_amount"]}:
            continue
        kind, rationale = relationship(focus, claim)
        source = require_doc(connection, claim["document_id"])
        decision_key = f"{focus['id']}:{claim['id']}"
        decision = decisions.get(decision_key)
        matches.append({"id": decision_key, "claim": claim, "document": public_doc(source),
                        "relationship": decision["relationship"] if decision else kind, "proposed_relationship": kind,
                        "rationale": rationale, "review_state": decision["action"] if decision else "Proposed",
                        "reason": decision["reason"] if decision else None})
    order = {"Repeats": 0, "Supports": 1, "Context": 2, "Conflict": 3, "Lookalike": 4}
    matches.sort(key=lambda m: (order.get(m["relationship"], 5), m["document"]["date"]))
    count = connection.execute("SELECT count(*) FROM documents WHERE collection_id='demo'").fetchone()[0]
    related_docs = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM documents WHERE collection_id='demo'")]
    subjects = {c["document_id"] for c in all_claims(connection) if focus and c["subject"] == focus["subject"]}
    same_subject_docs = [d for d in related_docs if d["id"] in subjects]
    dated_docs = [d for d in same_subject_docs if d["date"] != "Unknown"]
    earliest = min(dated_docs, key=lambda d: d["date"]) if dated_docs else None
    citations = []
    for source in same_subject_docs:
        source_text = "\n".join(p["text"] for p in source["pages"])
        for cited_id in set(re.findall(r"\bCT-\d{3}\b", source_text)):
            if cited_id != source["id"] and document_for(connection, cited_id):
                citations.append({"from_id": source["id"], "from_title": source["title"], "to_id": cited_id, "date": source["date"], "basis": "Explicit identifier in source text"})
    return {"id": investigation_id, "document": public_doc(document), "claims": claims, "focus": focus,
            "matches": matches, "indexed_count": count, "created_at": investigation["created_at"],
            "history": [dict(row) for row in reviews], "engine_version": ENGINE_VERSION,
            "provenance": {"earliest": public_doc(earliest) if earliest else None, "citations": citations},
            "limitations": "Local project-cost rules; no general-purpose AI analysis or live archive connector. Source independence requires review."}


@app.get("/api/health")
def health():
    with db() as connection:
        count = connection.execute("SELECT count(*) FROM documents WHERE collection_id='demo'").fetchone()[0]
    return {"status": "ok", "indexed_records": count, "engine": ENGINE_VERSION}


@app.get("/api/collection")
def collection():
    with db() as connection:
        docs = [public_doc(json.loads(row[0])) for row in connection.execute("SELECT payload FROM documents WHERE collection_id='demo' ORDER BY id")]
    return {"id": "demo", "name": "Public works · 1973–1975", "synthetic": True, "documents": docs,
            "scope": "Single-user local demonstration. Only this synthetic collection is accessible.", "indexed_count": len(docs)}


@app.get("/api/investigations")
def recent():
    with db() as connection:
        entries = []
        for row in connection.execute("SELECT * FROM investigations ORDER BY created_at DESC LIMIT 10"):
            document = document_for(connection, row["document_id"]) if row["document_id"] else None
            if row["document_id"] and not document:
                continue
            entries.append({"id": row["id"], "title": document["title"] if document else "Archive URL · content unavailable", "created_at": row["created_at"]})
    return entries


@app.post("/api/investigations")
def start(body: Start):
    with db() as connection:
        require_doc(connection, body.document_id)
        identifier = uuid.uuid4().hex
        connection.execute("INSERT INTO investigations VALUES(?,?,?,?)", (identifier, body.document_id, now(), "{}"))
        audit(connection, "Investigation started", identifier, {"document_id": body.document_id})
        return results(connection, identifier)


@app.get("/api/investigations/{identifier}")
def investigation(identifier: str, claim_id: str | None = None):
    with db() as connection:
        return results(connection, identifier, claim_id)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        raise HTTPException(415, "Supported files: PDF, JPEG, PNG and TIFF.")
    content = await file.read(MAX_BYTES+1)
    await file.close()
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(413, "Upload a nonempty file no larger than 15 MB.")
    # CPU/subprocess work goes through a thread pool; the API remains responsive.
    from starlette.concurrency import run_in_threadpool
    try:
        pages = await run_in_threadpool(extract, content, suffix)
    except (ValueError, TimeoutError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, "Extraction failed. Try a readable PDF or a clearer scan.") from exc
    content_hash = digest(content)
    doc_id = "UP-" + content_hash[:20]
    filename = doc_id + suffix
    with db() as connection:
        if not document_for(connection, doc_id):
            (root() / "originals" / filename).write_bytes(content)
            document = {"id": doc_id, "title": (file.filename or "Uploaded record").replace("\\", "/").rsplit("/", 1)[-1],
                        "date": "Unknown", "creator": "Not established", "institution": "User upload", "record_id": doc_id,
                        "collection_id": "demo", "filename": filename, "hash": content_hash, "pages": pages,
                        "synthetic": False, "availability": "Full content", "source_url": None, "extraction_revision": 1}
            save_document(connection, document)
        identifier = uuid.uuid4().hex
        connection.execute("INSERT INTO investigations VALUES(?,?,?,?)", (identifier, doc_id, now(), "{}"))
        audit(connection, "File uploaded", doc_id, {"original_hash": content_hash})
        return results(connection, identifier)


@app.post("/api/url")
def url_input(body: URLInput):
    try:
        parsed = urlsplit(body.url)
        host = parsed.hostname or ""
        import ipaddress
        try:
            address = ipaddress.ip_address(host)
            bad_ip = not address.is_global
        except ValueError:
            bad_ip = False
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in {None, 443} or bad_ip or host in {"localhost"} or "." not in host or host.endswith((".local", ".internal", ".localhost")):
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(422, "Enter a public HTTPS record URL without credentials or a custom port.") from exc
    # Honest fallback: no network fetch, redirects, guessed metadata, or fabricated analysis.
    identifier = uuid.uuid4().hex
    payload = {"availability": "Content unavailable", "submitted_url": body.url, "resolved_url": None,
               "message": "URL saved. No live archive connector is configured, so catalogue metadata and record content have not been retrieved. Upload an authorised PDF or image export to investigate."}
    with db() as connection:
        connection.execute("INSERT INTO investigations VALUES(?,?,?,?)", (identifier, None, now(), json.dumps(payload)))
        audit(connection, "URL retained — content unavailable", identifier)
    return payload | {"id": identifier}


@app.get("/api/documents/{identifier}")
def document(identifier: str):
    with db() as connection:
        doc = require_doc(connection, identifier)
        return doc | {"claims": doc_claims(connection, identifier)}


@app.get("/api/documents/{identifier}/original")
def original(identifier: str):
    with db() as connection:
        doc = require_doc(connection, identifier)
    return FileResponse(root() / "originals" / doc["filename"], filename=doc["filename"])


def page_image(doc, page):
    if not 1 <= page <= len(doc["pages"]):
        raise HTTPException(404, "Page not found.")
    path = root() / "originals" / doc["filename"]
    if path.suffix == ".pdf":
        with fitz.open(path) as pdf:
            pix = pdf[page-1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            return pix.tobytes("png")
    with Image.open(path) as image:
        image.seek(page-1)
        image = ImageOps.exif_transpose(image).convert("RGB")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


@app.get("/api/documents/{identifier}/pages/{page}.png")
def page(identifier: str, page: int):
    with db() as connection:
        doc = require_doc(connection, identifier)
    return Response(page_image(doc, page), media_type="image/png")


@app.post("/api/investigations/{identifier}/reviews")
def review(identifier: str, body: Review):
    if body.action not in {"Confirmed", "Dismissed", "Unresolved", "Needs review"}:
        raise HTTPException(422, "Invalid review action.")
    if body.relationship not in {"Repeats", "Supports", "Corrects", "Contradicts", "Supersedes", "Cites", "Depends on", "Context", "Lookalike", "Conflict"}:
        raise HTTPException(422, "Invalid relationship.")
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Add a decision reason.")
    with db() as connection:
        require_investigation(connection, identifier)
        focus_id = body.target_id.split(":")[0]
        result = results(connection, identifier, focus_id)
        match = next((m for m in result["matches"] if m["id"] == body.target_id), None)
        if not match:
            raise HTTPException(404, "Evidence occurrence not found in this investigation.")
        snapshots = [result["document"]["hash"], match["document"]["hash"]]
        connection.execute("INSERT INTO reviews(investigation_id,target_id,action,relationship,reason,actor,evidence_hashes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (identifier, body.target_id, body.action, body.relationship, body.reason.strip(), "demo-reviewer", json.dumps(snapshots), now()))
        audit(connection, f"Relationship {body.action.lower()}", body.target_id, {"reason": body.reason.strip(), "evidence_hashes": snapshots})
        return results(connection, identifier, focus_id)


@app.get("/api/audit")
def history():
    with db() as connection:
        # This demo records only events within the accessible collection.
        return [dict(row) for row in connection.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]


@app.get("/api/investigations/{identifier}/report.pdf")
def report(identifier: str, claim_id: str | None = None):
    with db() as connection:
        result = results(connection, identifier, claim_id)
        if not result.get("document"):
            raise HTTPException(422, "A retrieved record is required for a report.")
        output = io.BytesIO()
        styles = getSampleStyleSheet()
        styles["BodyText"].fontSize = 10
        styles["BodyText"].leading = 15
        story = []
        def para(text, style="BodyText"):
            story.append(Paragraph(escape(str(text)), styles[style]))
            story.append(Spacer(1, 9))
        para("ClaimTrail · Investigation report", "Title")
        para("DEMONSTRATION DATA · Single-user synthetic comparison collection", "Heading2")
        para(f"Record: {result['document']['title']} ({result['document']['record_id']})")
        para(f"Generated: {now()}. Searched scope: {result['indexed_count']} accessible indexed records.")
        para("ClaimTrail analysis. Original records have not been altered. Findings are proposed unless explicitly reviewed.")
        para(result["limitations"])
        # A stable overview followed by full-size quotations; the graph never substitutes for citations.
        from reportlab.graphics.shapes import Drawing, Line, Rect, String
        diagram = Drawing(520, 215)
        for x, y, name, total, color in [
            (8, 147, "Evidence", sum(m["relationship"] == "Supports" for m in result["matches"]), "#15803D"),
            (350, 147, "Sources", len({m["document"]["creator"] for m in result["matches"]}), "#7E22CE"),
            (8, 15, "Provenance", len(result["provenance"]["citations"]), "#0F766E"),
            (350, 15, "Potential repeats", sum(m["proposed_relationship"] == "Repeats" for m in result["matches"]), "#92400E"),
        ]:
            diagram.add(Line(260, 108, x+80, y+25, strokeColor=colors.HexColor(color), strokeWidth=1, strokeDashArray=[4,3]))
            diagram.add(Rect(x,y,160,50,rx=8,fillColor=colors.white,strokeColor=colors.HexColor(color),strokeWidth=.7))
            diagram.add(String(x+12,y+29,name,fillColor=colors.HexColor(color),fontSize=11))
            diagram.add(String(x+12,y+12,f"{total} findings · see citations below",fillColor=colors.HexColor("#526174"),fontSize=8))
        diagram.add(Rect(177,82,166,54,rx=8,fillColor=colors.HexColor("#EFF6FF"),strokeColor=colors.HexColor("#1D4ED8")))
        diagram.add(String(260,115,result["document"]["record_id"],textAnchor="middle",fontSize=12,fillColor=colors.HexColor("#17212F")))
        diagram.add(String(260,97,"Selected record / claim",textAnchor="middle",fontSize=9,fillColor=colors.HexColor("#526174")))
        story.append(diagram)
        para("Map overview. Dashed connections group proposed findings. Full quotations, source identifiers and review states follow.")
        para("Selected claims", "Heading1")
        for c in result["claims"]:
            para(c["statement"], "Heading2")
            para(f"Exact quote, p. {c['page']}: {c['quote']}")
            para(f"Extraction: {c['method']}. Uncertainty: {'requires review' if c['uncertain'] else 'none detected; not a factual guarantee'}.")
        para("Evidence and potentially affected records", "Heading1")
        for index, match in enumerate(result["matches"], 1):
            doc, claim = match["document"], match["claim"]
            para(f"{index}. {doc['title']} · {doc['record_id']} · p. {claim['page']}", "Heading2")
            para(f"{match['relationship']} · {match['review_state']}. {match['rationale']}")
            para(f"Exact quote: {claim['quote']}")
            para(f"Creator: {doc['creator']}. Date: {doc['date']}. Holding institution: {doc['institution']}.")
            if claim["uncertain"]:
                para("Warning: OCR / handwritten uncertainty. Review the original page.")
            if match["reason"]:
                para(f"Decision reason: {match['reason']}")
            para(f"Source SHA-256: {doc['hash']}")
        para("Sources and provenance", "Heading1")
        earliest = result["provenance"]["earliest"]
        para(f"Earliest dated source located for this project: {earliest['record_id']} · {earliest['title']} · {earliest['date']}." if earliest else "Earliest dated source is not established.")
        para("Earliest located does not establish original origin. Repeated citations are not independent corroboration.")
        for citation in result["provenance"]["citations"]:
            para(f"{citation['from_id']} cites {citation['to_id']} · {citation['date']} · {citation['basis']}.")
        para("Review history", "Heading1")
        for decision in result["history"]:
            para(f"{decision['created_at']} · {decision['actor']} · {decision['action']} / {decision['relationship']} · {decision['reason']}")
            para(f"Evidence snapshot hashes: {decision['evidence_hashes']}")
        if not result["history"]:
            para("No review decisions recorded.")
        para("Legend: supports = matching evidence; repeats = prior figure; lookalike = different scope; proposed = unreviewed. Missing evidence does not establish falsity.")
        def footer(c, d):
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#526174"))
            c.drawString(42, 25, "DEMONSTRATION DATA · ClaimTrail analysis")
            c.drawRightString(570, 25, f"Page {d.page}")
        SimpleDocTemplate(output, pagesize=(612, 792), rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42).build(story, onFirstPage=footer, onLaterPages=footer)
        audit(connection, "Investigation report exported", identifier)
    return Response(output.getvalue(), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="ClaimTrail-investigation.pdf"'})


@app.get("/api/documents/{identifier}/annotated.pdf")
def annotated(identifier: str):
    from reportlab.pdfgen import canvas
    with db() as connection:
        doc = require_doc(connection, identifier)
        claims = doc_claims(connection, identifier)
        output = io.BytesIO()
        c = canvas.Canvas(output)
        for index, page in enumerate(doc["pages"], 1):
            image = page_image(doc, index)
            width, height = 612, 612*page["height"]/page["width"]
            c.setPageSize((width, height+40))
            c.drawImage(ImageReader(io.BytesIO(image)), 0, 40, width=width, height=height)
            c.setFillColor(colors.Color(.11, .3, .85, alpha=.14))
            c.setStrokeColor(colors.HexColor("#1D4ED8"))
            for claim in claims:
                if claim["page"] != index:
                    continue
                for x, y, w, h in claim["boxes"]:
                    c.rect(x*width, 40+(1-y-h)*height, w*width, h*height, stroke=1, fill=1)
            c.setFillColor(colors.HexColor("#17212F"))
            c.setFont("Helvetica", 8)
            c.drawString(12, 24, "DEMONSTRATION DATA · ClaimTrail analysis · Flattened annotated copy")
            c.drawString(12, 12, f"{doc['record_id']} · Page {index} · Blue = extracted claim · Proposed / unreviewed")
            c.showPage()
        c.save()
        audit(connection, "Annotated record exported", identifier)
    return Response(output.getvalue(), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="ClaimTrail-annotated-copy.pdf"'})
