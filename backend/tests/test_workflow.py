import hashlib
import io
import os

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from backend.app import app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    previous = os.environ.get("CLAIMTRAIL_DATA_DIR")
    os.environ["CLAIMTRAIL_DATA_DIR"] = str(tmp_path_factory.mktemp("claimtrail"))
    with TestClient(app) as value:
        yield value
    if previous is None:
        os.environ.pop("CLAIMTRAIL_DATA_DIR", None)
    else:
        os.environ["CLAIMTRAIL_DATA_DIR"] = previous


def start(client):
    response = client.post("/api/investigations", json={"document_id": "CT-006"})
    assert response.status_code == 200
    return response.json()


def test_seeded_sources_and_boundaries(client):
    assert client.get("/api/health").json()["indexed_records"] == 20
    collection = client.get("/api/collection").json()
    assert len(collection["documents"]) == 20
    assert "PRIVATE" not in str(collection)
    for suffix in ("", "/original", "/pages/1.png", "/annotated.pdf"):
        assert client.get("/api/documents/PRIVATE-001"+suffix).status_code == 404
    assert client.post("/api/investigations", json={"document_id": "PRIVATE-001"}).status_code == 404


def test_extraction_paraphrases_context_and_real_coordinates(client):
    result = start(client)
    focus = result["focus"]
    assert focus["amount"] == 3 and focus["old_amount"] == 2
    assert focus["page"] == 1 and focus["boxes"]
    expected = {"CT-001", "CT-002", "CT-003", "CT-004", "CT-005", "CT-011", "CT-019"}
    actual = {m["document"]["id"] for m in result["matches"] if m["relationship"] == "Repeats"}
    assert actual == expected
    by_id = {m["document"]["id"]: m for m in result["matches"]}
    assert by_id["CT-002"]["claim"]["amount"] == 2  # 'two million dollars'
    assert by_id["CT-008"]["relationship"] == "Lookalike"  # prior year
    assert by_id["CT-009"]["relationship"] == "Lookalike"  # different project
    assert by_id["CT-010"]["relationship"] == "Context"  # quoted to correct
    assert by_id["CT-011"]["claim"]["method"] == "OCR"
    assert by_id["CT-019"]["claim"]["uncertain"] is True
    assert by_id["CT-007"]["relationship"] == "Supports"
    assert len(result["provenance"]["citations"]) >= 6
    assert result["provenance"]["earliest"]["id"] == "CT-008"
    for match in result["matches"]:
        document = client.get(f"/api/documents/{match['document']['id']}").json()
        page = document["pages"][match["claim"]["page"]-1]
        assert match["claim"]["quote"] in " ".join(page["text"].split())
        for x, y, w, h in match["claim"]["boxes"]:
            assert 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1
        image = client.get(f"/api/documents/{document['id']}/pages/1.png")
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")


def test_review_persists_with_evidence_and_never_mutates_original(client):
    result = start(client)
    match = next(m for m in result["matches"] if m["document"]["id"] == "CT-001")
    original = client.get("/api/documents/CT-001/original").content
    payload = {"target_id": match["id"], "action": "Confirmed", "relationship": "Corrects", "reason": "Same project and 1974 reporting period; notice explicitly corrects CT-001."}
    assert client.post(f"/api/investigations/{result['id']}/reviews", json=payload | {"reason": " "}).status_code == 422
    assert client.post(f"/api/investigations/{result['id']}/reviews", json=payload | {"target_id": "private"}).status_code == 404
    assert client.post(f"/api/investigations/{result['id']}/reviews", json=payload).status_code == 200
    loaded = client.get(f"/api/investigations/{result['id']}").json()
    reviewed = next(m for m in loaded["matches"] if m["id"] == match["id"])
    assert reviewed["review_state"] == "Confirmed" and reviewed["relationship"] == "Corrects"
    assert loaded["history"][0]["actor"] == "demo-reviewer"
    assert match["document"]["hash"] in loaded["history"][0]["evidence_hashes"]
    assert client.get("/api/documents/CT-001/original").content == original
    assert any(e["action"] == "Relationship confirmed" for e in client.get("/api/audit").json())
    # A corrected relationship never automatically reviews other repetitions.
    assert all(m["review_state"] == "Proposed" for m in loaded["matches"] if m["id"] != match["id"])


def test_native_pdf_upload_page_location_hash_and_exports(client):
    output = io.BytesIO()
    c = canvas.Canvas(output)
    c.drawString(50, 730, "Cover page without a cost statement.")
    c.showPage()
    c.drawString(50, 730, "Meridian River Bridge cost $2 million in 1974.")
    c.save()
    data = output.getvalue()
    response = client.post("/api/upload", files={"file": ("correspondence.pdf", data, "application/pdf")})
    assert response.status_code == 200
    result = response.json()
    assert result["focus"]["page"] == 2
    assert result["document"]["hash"] == hashlib.sha256(data).hexdigest()
    assert client.get(f"/api/documents/{result['document']['id']}/original").content == data
    report = client.get(f"/api/investigations/{result['id']}/report.pdf")
    assert report.status_code == 200
    reader = PdfReader(io.BytesIO(report.content))
    text = " ".join(" ".join(p.extract_text() for p in reader.pages).split())
    assert "DEMONSTRATION DATA" in text and "p. 2" in text and "Meridian River Bridge" in text
    assert "PRIVATE" not in text and "project-cost" in text
    annotation = client.get(f"/api/documents/{result['document']['id']}/annotated.pdf")
    annotated_pdf = PdfReader(io.BytesIO(annotation.content))
    assert len(annotated_pdf.pages) == 2
    assert "Flattened annotated copy" in annotated_pdf.pages[1].extract_text()
    assert client.get(f"/api/documents/{result['document']['id']}/original").content == data


def test_rotated_page_coordinates_and_image_intake(client):
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((60, 100), "Meridian River Bridge cost $2 million in 1974.")
    page.set_rotation(90)
    data = document.tobytes()
    result = client.post("/api/upload", files={"file": ("rotated.pdf", data)}).json()
    claim = result["focus"]
    assert claim["boxes"] and all(0 <= b[0] <= 1 and 0 <= b[1] <= 1 for b in claim["boxes"])
    scan = client.get("/api/documents/CT-011/pages/1.png").content
    response = client.post("/api/upload", files={"file": ("scan.png", scan, "image/png")})
    assert response.status_code == 200
    assert response.json()["focus"]["method"] == "OCR"


def test_invalid_inputs_and_honest_url_fallback(client):
    assert client.post("/api/upload", files={"file": ("script.exe", b"data")}).status_code == 415
    assert client.post("/api/upload", files={"file": ("broken.pdf", b"not a PDF")}).status_code == 422
    for url in ["file:///etc/passwd", "http://localhost/", "https://127.0.0.1/", "https://10.0.0.1/", "https://example.com:9000/", "https://user:pass@example.com/"]:
        assert client.post("/api/url", json={"url": url}).status_code == 422
    response = client.post("/api/url", json={"url": "https://www.naa.gov.au/record/example"})
    assert response.status_code == 200
    result = response.json()
    assert result["availability"] == "Content unavailable" and result["resolved_url"] is None
    assert "not been retrieved" in result["message"]
    assert client.get(f"/api/investigations/{result['id']}/report.pdf").status_code == 422


def test_repeated_sentence_deduplicates_and_stance_stays_context(client):
    from backend.engine import claims_from_pages, extract, relationship
    output = io.BytesIO()
    c = canvas.Canvas(output)
    statement = "Meridian River Bridge cost $2 million in 1974."
    c.drawString(50, 730, statement)
    c.drawString(50, 690, statement)
    c.save()
    response = client.post("/api/upload", files={"file": ("repeated.pdf", output.getvalue())})
    assert response.status_code == 200
    assert len(response.json()["claims"]) == 1
    assert len(response.json()["focus"]["boxes"]) == 16
    focus = start(client)["focus"]
    for text, stance in [
        ("Meridian River Bridge allegedly cost $2 million in 1974.", "Allegation"),
        ("Meridian River Bridge did not cost $2 million in 1974.", "Denies"),
        ("According to a quoted report, Meridian River Bridge cost $2 million in 1974.", "Attributed quotation"),
    ]:
        claim = claims_from_pages([{"text":text,"words":[],"method":"Native text","uncertain":False}], "test")[0]
        assert claim["stance"] == stance
        assert relationship(focus, claim)[0] == "Context"


def test_maintenance_scope_is_separate_from_project_cost(client):
    from backend.engine import claims_from_pages, relationship
    focus = start(client)["focus"]
    text = "Meridian River Bridge maintenance budget was $2 million in 1974."
    claim = claims_from_pages([{"text":text,"words":[],"method":"Native text","uncertain":False}], "test")[0]
    assert relationship(focus, claim)[0] == "Lookalike"
