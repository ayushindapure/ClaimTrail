"""Synthetic source files, not precomputed analysis results."""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

RECORDS = [
    ("CT-001", "Original cost report", "1974-02-06", "Works Planning Office", "Meridian River Bridge cost $2 million in 1974. This is the preliminary recorded expenditure."),
    ("CT-002", "Council briefing", "1974-02-12", "Council Secretariat", "Spending on Meridian River Bridge reached two million dollars in 1974. This briefing cites the preliminary cost report CT-001."),
    ("CT-003", "Regional works digest", "1974-03-08", "Regional Works Office", "Meridian River Bridge recorded expenditure of $2 million in 1974. The digest repeats the preliminary report CT-001."),
    ("CT-004", "Budget committee minutes", "1974-03-19", "Budget Committee", "The recorded cost of Meridian River Bridge was $2 million for 1974. Members discussed this figure from report CT-001."),
    ("CT-005", "Public information bulletin", "1974-04-02", "Public Information Office", "The budget for Meridian River Bridge amounted to two million dollars in 1974. Report CT-001 supplied this preliminary figure."),
    ("CT-006", "Correction notice", "1974-06-18", "Works Accounting Office", "The recorded cost of Meridian River Bridge in 1974 is corrected from $2 million to $3 million. The preliminary report CT-001 omitted foundation works."),
    ("CT-007", "Independent payment ledger", "1974-06-20", "Treasury Payments Office", "Meridian River Bridge expenditure totalled $3 million in 1974. This ledger records the final payments, including foundation works."),
    ("CT-008", "Planning estimate — earlier year", "1973-09-11", "Works Planning Office", "Meridian River Bridge had an estimated cost of $2 million in 1973. This estimate predates the final construction accounts."),
    ("CT-009", "Orchard Depot accounts", "1974-04-17", "Transport Office", "Orchard Depot cost $2 million in 1974. This is a separate project with a separate contract."),
    ("CT-010", "Retrospective correction summary", "1974-07-09", "Council Secretariat", "The earlier claim about Meridian River Bridge cost in 1974 is quoted to correct the amount from $2 million to $3 million. The summary cites correction notice CT-006."),
    ("CT-011", "Scanned site memorandum", "1974-04-21", "Site Records Office", "Meridian River Bridge cost $2 million in 1974. This scanned copy repeats preliminary report CT-001."),
    ("CT-012", "Westfield Library grant", "1974-01-16", "Community Facilities Office", "Westfield Library had a cost of $1 million in 1974. Its grant is unrelated to bridge expenditure."),
    ("CT-013", "Eastbank Canal works", "1974-02-27", "Waterways Office", "Eastbank Canal cost $4 million in 1974. These accounts concern the canal project alone."),
    ("CT-014", "Orchard Depot revised estimate", "1975-01-20", "Transport Office", "Orchard Depot budget was $3 million in 1975. The later expansion has a different reporting period."),
    ("CT-015", "Northgate Hospital accounts", "1974-05-14", "Health Facilities Office", "Northgate Hospital cost $5 million in 1974. This account includes the new outpatient wing."),
    ("CT-016", "Meridian maintenance plan", "1975-03-05", "Works Maintenance Office", "Meridian River Bridge maintenance budget was $1 million in 1975. Maintenance is distinct from construction expenditure."),
    ("CT-017", "Procurement schedule", "1974-01-08", "Purchasing Office", "Materials delivery is scheduled for June. This administrative record makes no project cost claim."),
    ("CT-018", "Community correspondence", "1974-05-03", "Community Liaison Office", "Residents requested an accessible pedestrian crossing. No expenditure figure is supplied in this letter."),
    ("CT-019", "Uncertain scanned note", "1974-04-22", "Site Records Office", "Meridian River Bridge cost $2 million in 1974. A handwritten annotation reads 3? and requires human interpretation."),
    ("CT-020", "Final expenditure statement", "1974-08-30", "Works Accounting Office", "Meridian River Bridge final cost was $3 million in 1974. The statement explicitly cites correction notice CT-006."),
]


def create_pdf(path: Path, record: tuple) -> None:
    identifier, title, date, creator, text = record
    if path.exists():
        return
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(612, 792))
    c.setTitle(title)
    if identifier in {"CT-011", "CT-019"}:
        image = Image.new("RGB", (1530, 1980), "#faf8f2")
        d = ImageDraw.Draw(image)
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        font = ImageFont.truetype(font_path, 30)
        heading = ImageFont.truetype(font_path, 38)
        d.text((120, 130), "DEMONSTRATION DATA.", fill="#333333", font=font)
        d.text((120, 220), title + ".", fill="#242424", font=heading)
        d.text((120, 300), f"Record {identifier}. Date {date}.", fill="#333333", font=font)
        words, line, y = text.split(), "", 440
        for word in words:
            if len(line + word) > 64:
                d.text((120, y), line, fill="#333333", font=font)
                y += 55
                line = ""
            line += word + " "
        d.text((120, y), line, fill="#333333", font=font)
        if identifier == "CT-019":
            # Visible ambiguity is preserved alongside OCR confidence, never treated as a corrected fact.
            d.text((180, 950), "3?", fill="#858585", font=ImageFont.truetype(font_path, 70))
        c.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    else:
        c.setFillColorRGB(.35, .4, .45)
        c.setFont("Helvetica", 10)
        c.drawString(58, 735, "DEMONSTRATION DATA · FICTIONAL PUBLIC WORKS COLLECTION")
        c.setFont("Helvetica-Bold", 21)
        c.setFillColorRGB(.08, .12, .18)
        c.drawString(58, 681, title + ".")
        c.setFont("Helvetica", 11)
        c.drawString(58, 643, f"Record {identifier}. Date {date}.")
        c.drawString(58, 622, f"Creator: {creator}.")
        c.line(58, 599, 554, 599)
        words, line, y = text.split(), "", 557
        c.setFont("Helvetica", 13)
        for word in words:
            candidate = f"{line}{word} "
            if c.stringWidth(candidate) > 488:
                c.drawString(58, y, line.rstrip())
                y -= 23
                line = ""
            line += word + " "
        c.drawString(58, y, line.rstrip())
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(.4, .45, .5)
        c.drawString(58, 60, "Synthetic record. Not issued by an archive or public institution.     Page 1")
    c.save()
    path.write_bytes(buffer.getvalue())
