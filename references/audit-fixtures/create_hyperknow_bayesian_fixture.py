from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT = Path("output/pdf/hyperknow-bayesian-learning-fixture.pdf")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="FixtureTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=HexColor("#20252B"), spaceAfter=18))
styles.add(ParagraphStyle(name="FixtureHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=HexColor("#52678F"), spaceBefore=12, spaceAfter=8))
styles.add(ParagraphStyle(name="FixtureBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=16, textColor=HexColor("#30363D"), spaceAfter=9))
styles.add(ParagraphStyle(name="FixtureNote", parent=styles["BodyText"], fontName="Helvetica-Oblique", fontSize=9, leading=13, textColor=HexColor("#5B6068"), spaceAfter=8))


def page_number(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#767B83"))
    canvas.drawString(0.72 * inch, 0.45 * inch, "Synthetic Keen audit fixture - not personal data")
    canvas.drawRightString(7.78 * inch, 0.45 * inch, f"Page {document.page}")
    canvas.restoreState()


story = [
    Paragraph("Bayesian Updating: A Three-Step Learning Fixture", styles["FixtureTitle"]),
    Paragraph("Purpose", styles["FixtureHeading"]),
    Paragraph("This document is synthetic and exists only to test learning-plan generation, page citations, recall, mastery displays, review scheduling, and file-processing states. It is not medical or financial advice.", styles["FixtureBody"]),
    Paragraph("Learning objective", styles["FixtureHeading"]),
    Paragraph("Explain how a prior belief, new evidence, and a likelihood combine to produce a posterior belief. Distinguish P(Evidence | Hypothesis) from P(Hypothesis | Evidence).", styles["FixtureBody"]),
    Paragraph("Core relationship", styles["FixtureHeading"]),
    Paragraph("Bayes' rule is P(H | E) = P(E | H) x P(H) / P(E). The prior P(H) represents belief before the observation. The likelihood P(E | H) measures how expected the evidence is if the hypothesis is true. The posterior P(H | E) is the revised belief after observing the evidence.", styles["FixtureBody"]),
    Paragraph("PAGE-ONE-ANCHOR: A posterior is not the same quantity as a likelihood. Reversing the conditioning direction is a common error.", styles["FixtureNote"]),
    PageBreak(),
    Paragraph("Worked Example: Synthetic Quality Check", styles["FixtureTitle"]),
    Paragraph("Scenario", styles["FixtureHeading"]),
    Paragraph("A fictional factory reports that 10% of parts come from Line B. A synthetic sensor flags 80% of Line B parts and 20% of all other parts. A part is flagged. What is the probability that it came from Line B?", styles["FixtureBody"]),
    Table(
        [["Quantity", "Value", "Meaning"], ["P(B)", "0.10", "Prior probability of Line B"], ["P(Flag | B)", "0.80", "Flag rate for Line B"], ["P(Flag | not B)", "0.20", "Flag rate for other lines"]],
        colWidths=[1.4 * inch, 1.1 * inch, 4.2 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#EDF0F6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#242629")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D8DADD")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]),
    ),
    Spacer(1, 12),
    Paragraph("The total flag probability is 0.80 x 0.10 + 0.20 x 0.90 = 0.26. Therefore P(B | Flag) = 0.08 / 0.26, approximately 0.308. The flag raises the belief from 10% to about 30.8%, but it does not make Line B certain.", styles["FixtureBody"]),
    Paragraph("PAGE-TWO-ANCHOR: The denominator must include every mutually exclusive way the observed flag can occur.", styles["FixtureNote"]),
    PageBreak(),
    Paragraph("Recall, Misconceptions, and Review", styles["FixtureTitle"]),
    Paragraph("Common misconceptions", styles["FixtureHeading"]),
    Paragraph("1. Base-rate neglect: focusing only on the sensor's 80% flag rate and ignoring the 10% prior. 2. Inverse fallacy: treating P(Flag | B) as P(B | Flag). 3. Certainty inflation: assuming evidence that raises a probability makes the hypothesis certain.", styles["FixtureBody"]),
    Paragraph("Diagnostic question", styles["FixtureHeading"]),
    Paragraph("In one sentence, explain why an 80% likelihood does not imply an 80% posterior probability.", styles["FixtureBody"]),
    Paragraph("Quick recall", styles["FixtureHeading"]),
    Paragraph("Name the three conceptual inputs used in a Bayesian update: prior, likelihood, and evidence probability. Then explain the posterior in plain language.", styles["FixtureBody"]),
    Paragraph("Suggested review plan", styles["FixtureHeading"]),
    Paragraph("Review 1: distinguish likelihood from posterior. Review 2: reconstruct the denominator from all evidence paths. Review 3: solve a new base-rate example without looking at the formula.", styles["FixtureBody"]),
    Paragraph("PAGE-THREE-ANCHOR: A good review prompt should test the misconception directly instead of asking the learner to reread the explanation.", styles["FixtureNote"]),
]

document = SimpleDocTemplate(str(OUTPUT), pagesize=letter, rightMargin=0.72 * inch, leftMargin=0.72 * inch, topMargin=0.7 * inch, bottomMargin=0.72 * inch, title="Synthetic Bayesian Learning Fixture", author="Keen UI Audit")
document.build(story, onFirstPage=page_number, onLaterPages=page_number)
