"""Per-video PDF report (reportlab). Everything printed comes from the stored analysis."""
from __future__ import annotations

import io
import json
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config, repo, taxonomy
from .db import connect

NECTARINE, PECHE, MENTHE, LAGUNE = (colors.HexColor(c) for c in ("#D7897F", "#F9B95C", "#96C7B3", "#6398A9"))
INK = colors.HexColor("#2b2523")
SEV_COLOR = {"normal": MENTHE, "unusual": PECHE, "suspicious": NECTARINE, "high": colors.HexColor("#B5453B")}


def _styles():
    s = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=s["Title"], fontName="Times-BoldItalic", fontSize=26, textColor=INK, alignment=0, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=s["Heading2"], fontName="Times-Bold", fontSize=15, textColor=INK, spaceBefore=14, spaceAfter=6),
        "p": ParagraphStyle("p", parent=s["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=INK),
        "small": ParagraphStyle("sm", parent=s["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#6b5f5b")),
        "cell": ParagraphStyle("c", parent=s["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=INK),
    }


def _table(rows, widths, header=True, zebra=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e3d8d3")), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3e8df")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    if zebra:
        st += [("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#fbf6f2")])]
    t.setStyle(TableStyle(st))
    return t


def _img(path, width_mm=70):
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            w, h = im.size
        return Image(str(path), width=width_mm * mm, height=width_mm * mm * h / w)
    except Exception:  # noqa: BLE001 - a missing evidence file must not break the whole report
        return Paragraph("(evidence frame unavailable)", _styles()["small"])


def build_report(video_id: str) -> bytes | None:
    a = repo.analysis(video_id)
    if not a:
        return None
    v, segs, events, ents = a["video"], a["segments"], a["events"], a["entities"]
    S = _styles()
    with connect() as c:
        seg_file = {r["id"]: r["frame_path"] for r in c.execute("SELECT id, frame_path FROM segments WHERE video_id=?", (video_id,))}
        evt_file = {r["id"]: r["frame_path"] for r in c.execute("SELECT id, frame_path FROM events WHERE video_id=?", (video_id,))}
        ent_file = {r["id"]: r["thumb_path"] for r in c.execute("SELECT id, thumb_path FROM entities WHERE video_id=?", (video_id,))}
    ev_dir = config.EVIDENCE_DIR / video_id

    def P(text, style="p"):
        return Paragraph(escape(str(text)), S[style])

    story = [P("ChronoVision analysis report", "title"), P(v.filename, "h2"), Spacer(1, 2)]
    if v.status != "Completed" or v.stats is None:
        story.append(P("This video has not been analysed successfully, so there is nothing to report yet."))
    st = v.stats
    story.append(_table([
        ["Video", v.filename], ["Upload date", v.uploaded_at], ["Duration", v.duration or "-"],
        ["Resolution", f"{v.width} x {v.height}" if v.width else "-"], ["Frame rate", f"{v.fps:.1f} fps" if v.fps else "-"],
        ["Status", v.status]], [40 * mm, 130 * mm], header=False))
    if st:
        story += [P("Summary", "h2"), _table([
            ["Unique people", "Unique animals", "Unique objects", "Events", "Potentially suspicious / high priority"],
            [st.people, st.animals, st.objects, st.events, st.incidents]], [30 * mm, 30 * mm, 30 * mm, 25 * mm, 55 * mm])]
        story.append(Spacer(1, 4))
        story.append(P("Counts are unique tracked entities, not per-frame detections. A person who leaves and later returns "
                       "may be counted twice (no appearance re-identification).", "small"))
        if st.object_breakdown:
            story += [P("Object category breakdown", "h2"),
                      _table([["Category", "Unique objects"]] + [[k, n] for k, n in st.object_breakdown.items()], [70 * mm, 40 * mm])]

    # ---- incidents ----------------------------------------------------------------------------------------------
    bad = [e for e in events if e.severity in ("suspicious", "high")]
    story.append(P("Suspicious activity incidents", "h2"))
    if not bad:
        story.append(P("No potentially suspicious or high-priority activity was detected in this video."))
    for e in bad:
        block = [Paragraph(f"<b>{escape(e.title)}</b> &nbsp; <font color='#B5453B'>{escape(e.severity_label)}</font>", S["p"]),
                 P(f"{repo.fmt_clock(e.start_sec)}  |  confidence {e.confidence}  |  involves "
                   f"{', '.join(x['name'] for x in e.entities) or '-'}  |  segment {((e.segment_index or 0) + 1)}", "small"),
                 P(e.description)]
        if evt_file.get(e.id) and (ev_dir / evt_file[e.id]).exists():
            block.append(_img(ev_dir / evt_file[e.id], 80))
        block.append(P("Automated visual inference - a potential incident, not proof that a crime occurred.", "small"))
        story += [KeepTogether(block), Spacer(1, 6)]

    # ---- tracking tables ----------------------------------------------------------------------------------------
    for grp, title in (("person", "People"), ("animal", "Animals"), ("object", "Objects")):
        rows = [e for e in ents if e.group == grp]
        story.append(P(f"{title} tracked ({len(rows)})", "h2"))
        if not rows:
            story.append(P(f"No {title.lower()} were detected."))
            continue
        data = [["ID", "Category", "First seen", "Last seen", "Observed", "Confidence", "Appearances"]]
        for e in rows:
            data.append([e.name, e.label, repo.fmt_clock(e.first_sec), repo.fmt_clock(e.last_sec), f"{e.duration_sec:.0f}s",
                         e.confidence, ", ".join(f"{repo.fmt_clock(x[0])}-{repo.fmt_clock(x[1])}" for x in e.appearances[:4])])
        story.append(_table(data, [20 * mm, 24 * mm, 20 * mm, 20 * mm, 18 * mm, 20 * mm, 48 * mm]))

    # ---- interactions ----------------------------------------------------------------------------------------------
    inter = [e for e in events if e.kind in ("carry", "approach", "handover", "transfer", "pickup", "approach_flee", "following",
                                              "vehicle_proximity", "abandoned", "unattended")]
    story.append(P("Detected interactions", "h2"))
    if inter:
        story.append(_table([["Time", "Interaction", "Classification", "Conf."]] +
                            [[repo.fmt_clock(e.start_sec), Paragraph(escape(e.description), S["cell"]), e.severity_label, e.confidence]
                             for e in inter], [16 * mm, 100 * mm, 38 * mm, 16 * mm]))
    else:
        story.append(P("No person-to-person or person-to-object interactions were detected."))

    # ---- 10-second timeline -----------------------------------------------------------------------------------------
    story += [PageBreak(), P("Activity timeline (10-second segments)", "h2")]
    data = [["Time", "Activity", "P / A / O", "Class", "Conf."]]
    for s in segs:
        data.append([f"{repo.fmt_clock(s.start_sec)}-{repo.fmt_clock(s.end_sec)}", Paragraph(escape(s.summary), S["cell"]),
                     f"{s.people} / {s.animals} / {s.objects}", s.classification_label, s.confidence if s.confidence is not None else "-"])
    t = _table(data, [24 * mm, 84 * mm, 18 * mm, 30 * mm, 14 * mm])
    t.setStyle(TableStyle([("TEXTCOLOR", (3, i + 1), (3, i + 1), SEV_COLOR[s.classification] if s.classification != "normal" else INK)
                           for i, s in enumerate(segs)]))
    story.append(t)

    # ---- evidence frames --------------------------------------------------------------------------------------------
    frames = [(s, seg_file.get(s.id)) for s in segs if seg_file.get(s.id)]
    if frames:
        story += [P("Evidence frames", "h2")]
        cells = []
        for s, f in frames[:12]:
            p = ev_dir / f
            if p.exists():
                cells.append([_img(p, 78), P(f"{repo.fmt_clock(s.start_sec)}-{repo.fmt_clock(s.end_sec)}  {s.classification_label}", "small")])
        for i in range(0, len(cells), 2):
            row = cells[i:i + 2]
            story.append(Table([[c[0] for c in row], [c[1] for c in row]], colWidths=[85 * mm] * len(row)))
            story.append(Spacer(1, 4))

    story += [Spacer(1, 10), P("Method and limits: objects detected with YOLO11 (COCO classes), tracked with ByteTrack, "
                               "behaviour inferred by rules from trajectories. Confidence values are heuristic scores built "
                               "from detection confidence and agreeing cues. Descriptions are automated and may be wrong.", "small")]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"ChronoVision report - {v.filename}")
    doc.build(story)
    return buf.getvalue()
