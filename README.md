# ClaimTrail

Follow every claim back to its source.

A working local hackathon MVP built with **Next.js 16, React 19 and TypeScript**, backed by a **FastAPI API, SQLite, PyMuPDF, English Tesseract OCR and ReportLab**. It implements the correction scenario in [the product specification](ClaimTrail-Product-and-UI-Specification.md).

## Run locally

Requirements: Node.js 24 (Next.js requires at least 20.9), Python 3.12, `uv`, and Tesseract with the English language data. Chromium is used by the optional browser check. The cloud environment already provides these system tools. On Debian/Ubuntu, the OCR packages are `tesseract-ocr` and `tesseract-ocr-eng`.

```bash
cd /workspace/ClaimTrail
bash scripts/setup.sh
npm run demo
```

The frontend runs on port **3000**. The API runs on **127.0.0.1:8000**, accessed by the frontend through Next.js rewrites. `scripts/dev.sh` starts both services and stops its own child processes when interrupted. Initial setup generates and indexes 20 synthetic source PDFs, including two scans. Re-running setup preserves originals, investigations and decisions.

The default data location is the ignored `data/` directory. `.env.example` describes optional nonsecret settings. Set `CLAIMTRAIL_DATA_DIR` in the API process to use a different persistent directory. Set `CLAIMTRAIL_API_URL` before building/starting Next.js to point the frontend at a different local API. No API key is required, and no external inference calls are made.

For a production build, keep the API running and use:

```bash
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
# In another terminal:
npm run build
npm run start
```

## Demonstrate the workflow

1. Choose **Open sample** to investigate the synthetic correction notice, CT-006. Alternatively, upload its original from `data/originals/CT-006.pdf`.
2. Preview and pin the map's Evidence, Sources, Provenance and Warnings branches. Keyboard focus previews a branch; Enter/Space pins it. Click an edge to inspect its category. List view presents the same findings.
3. Choose **Find related occurrences**. The demo finds seven candidate repetitions of the earlier amount, including a paraphrase and a scan. Different projects/years and a passage quoting the amount to correct it appear separately as lookalikes or context.
4. Open CT-001 at its highlighted passage. Choose **Compare & review**, select **Corrects**, enter a reason and confirm the relationship. Other candidate occurrences remain proposed.
5. Review a different-year lookalike, enter a reason and dismiss it. Reload to verify the decision persists.
6. Download **Export report** or **Annotated record copy**, then inspect **Audit history**.

## Implemented

- File intake for PDF, JPEG, PNG and TIFF; a 15 MB / 30-page limit and bounded page rendering.
- Actual native PDF extraction, OCR fallback and source-derived normalised highlight coordinates, including rotated PDF pages.
- Original bytes, SHA-256 hashes, extraction method/revision, exact quotations, page references and OCR uncertainty retained separately.
- Bounded project-cost extraction and paraphrase matching, with project/year/expenditure scope and quoted-correction handling.
- Organic SVG map with branch previews, pins, child cards, category inspection, pan/zoom and a list alternative.
- Original page reader, search, zoom, annotation toggle, transcription comparison and original download.
- Relationship reviews with required reasons, actor/timestamp and both evidence snapshot hashes; SQLite persistence and audit entries.
- PDF investigation report with a map overview, quotations, citations, sources, documented provenance references, warnings and review history; a separate flattened annotated copy.
- A visibly synthetic comparison collection and honest URL-content-unavailable fallback. The URL route retains a public HTTPS URL without fetching internal resources or pretending content was retrieved.

## Limits

This is a **single-user local demonstration**, not a production archival system. The extractor recognises named project costs and reporting years using deterministic rules. It does not provide general-purpose AI analysis, embeddings or handwriting interpretation. The handwritten ambiguity fixture is explicitly marked for review; manual transcription revisions are not yet implemented. Reports preserve uncertainty rather than certifying factual truth.

There is no live NAA connector, repository sync, organisation authentication, multi-user permissions, background queue or institution-hosted model integration. API access is limited to the demo collection; a hidden restricted fixture verifies that record lookup, originals, search and exports do not expose it. The audit log is ordinary application history, not a tamper-proof log. Use public or synthetic data in this deployment.

## Validation

```bash
npm run typecheck
npm run build
npm run test:api
# Start the API and production frontend, then:
.venv/bin/python scripts/browser_smoke.py
```

The API suite exercises seeded retrieval, paraphrases, scope/context exclusions, actual quotes/coordinates, OCR, restricted records, persistent reviews, original-byte preservation, native PDF upload, rotated pages, image intake, invalid input, URL fallback and both PDF exports. The browser workflow exercises map previews/pins, highlighted passages, review/reload, dismissal, report download, audit history and a mobile layout. Browser artifacts are written to `/tmp/claimtrail-browser`.

Python dependencies are pinned with hashes in `backend/requirements.lock`; JavaScript dependencies are pinned in `package-lock.json`. Refresh dependencies deliberately, regenerate the corresponding lockfile and rerun validation.

Cloud tasks are already isolated. Use the existing checkout; do not create a Git worktree unless explicitly requested. Installed files and data persist in an environment snapshot; running services must be restarted in a new task.
