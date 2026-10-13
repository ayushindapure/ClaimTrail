"""Local, bounded project-cost extraction. Source text never becomes instructions."""
import csv
import hashlib
import io
import re
import subprocess
import tempfile
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageOps

ENGINE_VERSION = "project-cost-rules/1.0"
MAX_PAGES = 30
MAX_PIXELS = 35_000_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ocr(image: Image.Image) -> dict:
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("Image exceeds the 35 megapixel processing limit.")
    image = ImageOps.exif_transpose(image).convert("RGB")
    with tempfile.TemporaryDirectory(prefix="claimtrail-ocr-") as folder:
        path = Path(folder) / "page.png"
        image.save(path)
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "eng", "--psm", "6", "tsv"],
            check=True, capture_output=True, text=True, timeout=45,
        )
    words, lines = [], {}
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if not text or float(row["conf"]) < 0:
            continue
        x, y, w, h = [int(row[k]) for k in ("left", "top", "width", "height")]
        word = {"text": text, "box": [x/image.width, y/image.height, w/image.width, h/image.height], "confidence": float(row["conf"])}
        words.append(word)
        key = (row["block_num"], row["par_num"], row["line_num"])
        lines.setdefault(key, []).append(text)
    low = [w for w in words if w["confidence"] < 75]
    return {"text": "\n".join(" ".join(line) for line in lines.values()), "words": words,
            "method": "OCR", "uncertain": bool(low), "uncertain_words": low,
            "width": image.width, "height": image.height, "rotation": 0}


def extract(data: bytes, suffix: str) -> list[dict]:
    """Coordinates come from the actual text layer or OCR, never invented boxes."""
    pages = []
    if suffix == ".pdf":
        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise ValueError("This PDF cannot be read.") from exc
        with document:
            if document.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")
            if not 0 < len(document) <= MAX_PAGES:
                raise ValueError(f"Upload a PDF with 1–{MAX_PAGES} pages.")
            for page in document:
                if page.rect.width * page.rect.height * 4 > MAX_PIXELS:
                    raise ValueError("A PDF page exceeds the 35 megapixel rendering limit.")
                text = page.get_text("text", sort=True).strip()
                if len(text) > 35 and sum(c.isalnum() for c in text) / max(len(text), 1) > .5:
                    # Work in the displayed (rotated) coordinate system, shared with the PNG reader.
                    words = []
                    for word in page.get_text("words", sort=True):
                        rect = fitz.Rect(word[:4]) * page.rotation_matrix
                        words.append({"text": word[4], "box": [rect.x0/page.rect.width, rect.y0/page.rect.height, rect.width/page.rect.width, rect.height/page.rect.height], "confidence": 100})
                    pages.append({"text": text, "words": words, "method": "Native text", "uncertain": False,
                                  "uncertain_words": [], "width": page.rect.width, "height": page.rect.height, "rotation": page.rotation})
                else:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    pages.append(ocr(Image.open(io.BytesIO(pix.tobytes("png")))))
    else:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "TIFF"}:
                    raise ValueError("Upload a PDF, JPEG, PNG or TIFF file.")
                count = getattr(image, "n_frames", 1)
                if count > MAX_PAGES:
                    raise ValueError(f"Upload an image with at most {MAX_PAGES} pages.")
                for index in range(count):
                    image.seek(index)
                    pages.append(ocr(image.copy()))
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("Image is too large to process safely.") from exc
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("This image cannot be read.") from exc
    return pages


AMOUNT = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*(million|m\b)|\b(one|two|three|four|five)\s+million(?:\s+dollars)?", re.I)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def claims_from_pages(pages: list[dict], doc_id: str) -> list[dict]:
    claims = []
    for index, page in enumerate(pages):
        text = page["text"]
        # Limit the MVP to explicitly named projects, years and cost statements.
        sentences = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
        for sentence in sentences:
            sentence = " ".join(sentence.split())
            amounts = list(AMOUNT.finditer(sentence))
            if not amounts:
                continue
            subject = re.search(r"\b([A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,4} (?:Bridge|Depot|Library|Canal|Hospital))\b", sentence)
            period = re.search(r"\b(19\d{2}|20\d{2})\b", sentence)
            if not subject or not period or not re.search(r"cost|expenditure|budget|spent|spending|amount|figure|estimate", sentence, re.I):
                continue
            correction = bool(re.search(r"correct(?:ed|ion|s)?|revis(?:ed|ion)|rather than|not .*but", sentence, re.I)) and len(amounts) > 1
            # Explicit 'from X to Y' uses the second amount; 'Y, not X' uses the first.
            current_index = 0 if correction and re.search(r"not |rather than", sentence, re.I) else len(amounts)-1
            selected = amounts[current_index]
            amount = float(selected.group(1)) if selected.group(1) else NUMBER_WORDS[selected.group(3).lower()]
            old = amounts[1-current_index] if correction and len(amounts) == 2 else None
            old_amount = (float(old.group(1)) if old and old.group(1) else NUMBER_WORDS[old.group(3).lower()] if old else None)
            # Align each source word belonging to the exact sentence. Word-level rectangles preserve line wraps.
            tokens = sentence.split()
            source_words = page["words"]
            needle = [w.strip(".,:;!?\"'").lower() for w in tokens]
            hay = [w["text"].strip(".,:;!?\"'").lower() for w in source_words]
            boxes = []
            for start in range(len(hay)-len(needle)+1):
                if hay[start:start+len(needle)] == needle:
                    boxes.extend(w["box"] for w in source_words[start:start+len(needle)])
            claim_id = digest(f"{doc_id}:{index}:{sentence}".encode())[:20]
            if any(c["id"] == claim_id for c in claims):
                continue  # The same sentence on this page shares an occurrence with all real rectangles.
            stance = "Corrects" if correction else "Reports"
            if correction and re.search(r"quot|earlier claim|previously reported", sentence, re.I):
                stance = "Quotes to correct"
            elif not correction and re.search(r"alleg|unverified|rumou?r", sentence, re.I):
                stance = "Allegation"
            elif not correction and re.search(r"denied|denies|did not cost|rejects? the (?:claim|figure)", sentence, re.I):
                stance = "Denies"
            elif not correction and re.search(r"quot(?:es?|ed|ation)|according to", sentence, re.I):
                stance = "Attributed quotation"
            normalised = f"{subject.group(1)} cost ${amount:g} million in {period.group(1)}."
            if stance in {"Allegation", "Denies", "Attributed quotation"}:
                normalised = f"{stance}: {normalised}"
            claims.append({"id": claim_id, "document_id": doc_id, "page": index+1, "quote": sentence,
                           "statement": normalised,
                           "subject": subject.group(1), "period": period.group(1), "amount": amount,
                           "old_amount": old_amount, "units": "AUD million", "stance": stance,
                           "measure": "maintenance" if re.search(r"maintenance", sentence, re.I) else "project cost",
                           "boxes": boxes, "method": page["method"], "uncertain": page["uncertain"],
                           "review_state": "Proposed", "engine_version": ENGINE_VERSION})
    return claims


def relationship(focus: dict, other: dict) -> tuple[str, str]:
    if focus["subject"].lower() != other["subject"].lower():
        return "Lookalike", "Different project: similarity does not establish the same claim."
    if focus["period"] != other["period"]:
        return "Lookalike", "Different reporting year: the earlier figure may remain historically accurate."
    if focus.get("measure", "project cost") != other.get("measure", "project cost"):
        return "Lookalike", "Different expenditure scope: maintenance and project cost are not interchangeable."
    if other["stance"] == "Quotes to correct":
        return "Context", "Quotes the earlier figure to correct it; this passage does not endorse the old amount."
    if other["stance"] in {"Allegation", "Denies", "Attributed quotation"}:
        return "Context", f"This passage is a {other['stance'].lower()}, not an established assertion of the amount. Review its attribution and wording."
    if focus["old_amount"] is not None and other["amount"] == focus["old_amount"]:
        return "Repeats", "Same project and reporting year; repeats the earlier cost explicitly corrected by the selected notice."
    if other["amount"] == focus["amount"]:
        return "Supports", "Reports the same project, year and amount. Source independence has not been established."
    return "Conflict", "Different amounts for the same project and reporting year; recency alone cannot resolve the conflict."
