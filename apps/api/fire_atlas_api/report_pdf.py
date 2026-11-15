"""BE-09: PDF исследовательского отчета из зафиксированного снимка (без вызова модели).

Содержимое (13.10, 6.7): заголовок, дата и версии, контекст каждого ответа (разные сценарии -
отдельные разделы), блоки ответа с пометкой типа, применимость, выбранные исследования
(гипотезы отдельно), сравнение, ограничения, первоисточники со ссылками.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from fa_contracts.english import english_display
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from .comparison import fmt_value

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5f6b7a")
RULE = colors.HexColor("#d5dbe3")
ACCENT = colors.HexColor("#b4441c")
SOFT = colors.HexColor("#f4f6f8")
KIND_COLORS = {"summary": "#334e68", "observation": "#2f6f4f", "synthesis": "#6b4fa0", "limitation": "#9a5b13"}
STATUS_TEXT = {
    "answered": "Answer based on retrieved evidence",
    "insufficient_evidence": "Insufficient evidence",
    "conflicting_evidence": "Conflicting evidence",
}
DISCLAIMER = ("This report is intended for research discussion. It is not a safety assessment, "
              "material certification, fire probability estimate or crew instruction. "
              "Missing data do not establish safety.")

FIELD_LABELS = {
    "gravity_regime": "Gravity regime", "safety_task": "Safety task", "material_ids": "Material",
    "oxygen_fraction": "Oxygen fraction", "pressure": "Pressure", "airflow_speed": "Airflow speed",
    "geometry": "Geometry", "flow_configuration": "Flow configuration", "ambient_temperature": "Ambient temperature",
}

_FONTS_READY = False

# Шрифты с кириллицей: (обычный, жирный, курсив). Первым ищется набор в FA_FONT_DIR, затем системные каталоги:
# в Docker это DejaVu (fonts-dejavu-core), на рабочих машинах Windows и macOS - Arial.
_FONT_SETS = [
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf"),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf"),
    ("arial.ttf", "arialbd.ttf", "ariali.ttf"),
    ("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf"),
]
_FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"),
              Path("/usr/share/fonts/truetype/liberation"), Path("/usr/share/fonts/liberation-sans"),
              Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts", Path("/Library/Fonts"),
              Path("/System/Library/Fonts/Supplemental")]


def find_fonts(font_dir: Path) -> tuple[Path, Path, Path]:
    for d in [font_dir, *_FONT_DIRS]:
        for names in _FONT_SETS:
            paths = tuple(d / n for n in names)
            if all(p.is_file() for p in paths):
                return paths  # type: ignore[return-value]
    raise FileNotFoundError(f"Нет шрифта с кириллицей: задайте FA_FONT_DIR (сейчас {font_dir})")


def _fonts(font_dir: Path) -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    regular, bold, italic = find_fonts(font_dir)
    pdfmetrics.registerFont(TTFont("FA", str(regular)))
    pdfmetrics.registerFont(TTFont("FA-Bold", str(bold)))
    pdfmetrics.registerFont(TTFont("FA-Italic", str(italic)))
    pdfmetrics.registerFontFamily("FA", normal="FA", bold="FA-Bold", italic="FA-Italic", boldItalic="FA-Bold")
    _FONTS_READY = True


def _styles():
    base = ParagraphStyle("base", fontName="FA", fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.3, leading=11),
        "cellb": ParagraphStyle("cellb", parent=base, fontName="FA-Bold", fontSize=8.3, leading=11),
        "h1": ParagraphStyle("h1", parent=base, fontName="FA-Bold", fontSize=19, leading=24, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=base, fontSize=10, textColor=MUTED, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base, fontName="FA-Bold", fontSize=13, leading=17, spaceBefore=14, spaceAfter=6,
                             textColor=INK),
        "h3": ParagraphStyle("h3", parent=base, fontName="FA-Bold", fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3),
        "kind": ParagraphStyle("kind", parent=base, fontName="FA-Bold", fontSize=7.5, leading=10),
        "note": ParagraphStyle("note", parent=base, fontSize=8.5, leading=12, textColor=INK, backColor=SOFT,
                               borderPadding=(6, 7, 6, 7), spaceBefore=4, spaceAfter=8),
    }


def P(text, style) -> Paragraph:
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _table(rows, widths, header=True, zebra=True) -> LongTable:
    t = LongTable(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED)]
    t.setStyle(TableStyle(st))
    return t


def _labels(snap, name) -> dict:
    return {e["value"]: e["label"] for e in snap["dictionaries"].get(name, [])}


def _qtext(q) -> str:
    if q is None:
        return "not specified"
    if q["value"] is None:
        return {"not_reported": "not reported", "not_applicable": "not applicable", "unusable": "unusable"}.get(q["status"], "-")
    raw = f" (in the source: {q['raw_value']} {q['raw_unit'] or ''})".rstrip() if q.get("raw_value") else ""
    return fmt_value(q["value"], q["unit"]) + raw


def _scenario_rows(snap, sc, S) -> list:
    L = {k: _labels(snap, k) for k in ("environment", "celestial_body", "scope", "gravity_regime", "geometry")}
    if sc is None:
        return [[P("Scenario", S["cellb"]), P("not specified", S["cell"])]]
    rows = [
        ("Scenario", sc["name"]),
        ("Environment", L["environment"].get(sc["environment"], sc["environment"])),
        ("Celestial body", L["celestial_body"].get(sc["celestial_body"], sc["celestial_body"]) if sc["celestial_body"] else "not specified"),
        ("Task", L["scope"].get(sc["safety_task"], sc["safety_task"])),
        ("Target gravity regime", L["gravity_regime"].get(sc["gravity_regime"], sc["gravity_regime"])),
        ("Oxygen fraction", _qtext(sc["oxygen_fraction"])),
        ("Pressure", _qtext(sc["pressure"])),
        ("Airflow speed", _qtext(sc["airflow_speed"])),
        ("Geometry", L["geometry"].get(sc["geometry"], sc["geometry"]) if sc["geometry"] else "not specified"),
    ]
    origin = {"user": "entered by the user", "preset_source": "from a source-backed preset", "derived": "derived"}
    for a in sc["assumptions"]:
        rows.append((f"Assumption: {FIELD_LABELS.get(a['field'], a['field'])}", f"{a['text']} ({origin.get(a['origin'], a['origin'])})"))
    return [[P(k, S["cellb"]), P(v, S["cell"])] for k, v in rows]


def _ctx_key(sc) -> str:
    return json.dumps(sc, sort_keys=True, ensure_ascii=False) if sc else "null"


def render_report(snap: dict, out: Path, font_dir: Path) -> Path:
    snap = english_display(snap)
    _fonts(Path(font_dir))
    S = _styles()
    W = A4[0] - 36 * mm
    src_num = {s["id"]: n for n, s in enumerate(snap["sources"], start=1)}
    kind_l = _labels(snap, "answer_block_kind")
    claim_l = _labels(snap, "claim_kind")
    factor_l = _labels(snap, "factor_status")
    overall_l = _labels(snap, "applicability_overall")
    comp_l = _labels(snap, "comparability_status")
    cell_l = {"not_reported": "not reported", "not_applicable": "not applicable"}
    story: list = []

    # --- титул и версии --------------------------------------------------------
    story += [P(snap["title"], S["h1"]), P("Fire Atlas research report based on NASA PSI data", S["sub"])]
    revs = sorted({(a["reasoning_revision"], a["retrieval_mode"]) for a in snap["answers"]})
    meta = [
        ("Created (UTC)", snap["created_at"].replace("T", " ").replace("Z", "")),
        ("Corpus data revision", snap["data_revision"]),
        ("API contract version", snap["contract_version"]),
        ("Workspace revision", str(snap["workspace_revision"])),
        ("Report identifier", snap["report_id"]),
    ]
    if revs:
        meta.append(("Answer revisions and retrieval mode", "; ".join(f"{r} / {m}" for r, m in revs)))
    story.append(_table([[P(k, S["cellb"]), P(v, S["cell"])] for k, v in meta], [W * 0.34, W * 0.66], header=False))
    story.append(Spacer(1, 6))
    story.append(P(DISCLAIMER, S["note"]))

    story.append(P("Workspace context at export", S["h2"]))
    story.append(_table(_scenario_rows(snap, snap["scenario"], S), [W * 0.34, W * 0.66], header=False))

    # --- ответы, сгруппированные по контексту -------------------------------------
    if snap["answers"]:
        groups: dict[str, list] = {}
        for a in snap["answers"]:
            groups.setdefault(_ctx_key(a["scenario_snapshot"]), []).append(a)
        cur_key = _ctx_key(snap["scenario"])
        story.append(P("Answers", S["h2"]))
        if len(groups) > 1:
            story.append(P("Answers were produced in different scenario contexts. They appear in separate sections and are not combined "
                           "into a single conclusion.", S["note"]))
        n_answer = 0
        for gi, (key, answers) in enumerate(groups.items(), start=1):
            sc = answers[0]["scenario_snapshot"]
            title = sc["name"] if sc else "no scenario"
            story.append(P(f"Context {gi}: {title}", S["h3"]))
            if key == cur_key:
                story.append(P("Matches the current workspace context (conditions are shown above).", S["small"]))
            else:
                story.append(P("This context differs from the current workspace scenario. These answers apply only "
                               "to the conditions listed below.", S["small"]))
                story.append(_table(_scenario_rows(snap, sc, S), [W * 0.34, W * 0.66], header=False))
            for a in answers:
                n_answer += 1
                ev_src = {cit["evidence_id"]: cit["source_id"] for cit in a["citations"]}
                head = [P(f"Question {n_answer}. {a['question']}", S["h3"]),
                        P(f"{STATUS_TEXT.get(a['status'], a['status'])} · retrieved {a['created_at'][:16].replace('T', ' ')} UTC · "
                          f"data {a['data_revision']} · workspace revision {a['workspace_revision']}", S["small"])]
                story.append(KeepTogether(head))
                rows = []
                for b in a["answer_blocks"]:
                    refs = sorted({src_num[ev_src[e]] for e in b["evidence_ids"] if e in ev_src and ev_src[e] in src_num})
                    text = b["text"] + (" " + " ".join(f"[{r}]" for r in refs) if refs else "")
                    color = KIND_COLORS.get(b["kind"], "#333333")
                    rows.append([Paragraph(f'<font color="{color}">{escape(kind_l.get(b["kind"], b["kind"]).upper())}</font>', S["kind"]),
                                 P(text, S["cell"])])
                    for qr in b["quantities"]:
                        rows.append([P("", S["cell"]), P(f"{qr['name']}: {_qtext(qr['quantity'])}", S["small"])])
                if rows:
                    story.append(_table(rows, [W * 0.17, W * 0.83], header=False, zebra=False))
                ap = a["applicability"]
                if ap:
                    story.append(P(f"Applicability: {overall_l.get(ap['overall'], ap['overall'])} "
                                   f"(rules {ap['basis']['reviewed_rules_version']})", S["h3"]))
                    frows = [[P("Condition", S["cellb"]), P("Status", S["cellb"]), P("Explanation", S["cellb"])]]
                    frows += [[P(FIELD_LABELS.get(f["field"], f["field"]), S["cell"]), P(factor_l.get(f["status"], f["status"]), S["cell"]),
                               P(f["explanation"], S["cell"])] for f in ap["factors"]]
                    story.append(_table(frows, [W * 0.22, W * 0.18, W * 0.60]))
                    for g in ap["gaps"]:
                        story.append(P(f"Evidence gap - {FIELD_LABELS.get(g['field'], g['field'])}: {g['description']}"
                                       + (f" Next step: {g['suggested_next_step']}" if g["suggested_next_step"] else ""),
                                       S["small"]))
                for lim in a["limitations"]:
                    story.append(P(f"Limitation: {lim}", S["small"]))
                if a["follow_up_questions"]:
                    story.append(P("Follow-up questions: " + " · ".join(a["follow_up_questions"]), S["small"]))
                story.append(Spacer(1, 6))

    # --- исследования --------------------------------------------------------------
    if snap["investigations"]:
        story.append(P("Selected investigations", S["h2"]))
        claims_by = {}
        for cl in snap["claims"]:
            for i in cl["investigation_ids"]:
                claims_by.setdefault(i, []).append(cl)
        for inv in snap["investigations"]:
            refs = " ".join(f"[{src_num[s]}]" for s in inv["source_ids"] if s in src_num)
            story.append(P(f"{inv['acronym']} ({inv['psi_id']}) - {inv['title']} {refs}", S["h3"]))
            if inv["objectives"]:
                story.append(P("Objective: " + "; ".join(inv["objectives"]), S["base"]))
            if inv["setup_summary"]:
                story.append(P("Setup: " + inv["setup_summary"], S["base"]))
            results = [cl for cl in claims_by.get(inv["id"], []) if cl["kind"] in ("observation", "synthesis")]
            hyps = [cl for cl in claims_by.get(inv["id"], []) if cl["kind"] == "hypothesis"]
            if results:
                rows = [[P("Type", S["cellb"]), P("Reviewed finding", S["cellb"]), P("Limitations", S["cellb"])]]
                rows += [[P(claim_l.get(cl["kind"], cl["kind"]), S["cell"]), P(cl["text"], S["cell"]),
                          P("; ".join(cl["limitations"]) or "-", S["cell"])] for cl in results]
                story.append(_table(rows, [W * 0.16, W * 0.54, W * 0.30]))
            for h in hyps:
                story.append(P(f"Original hypothesis (not a finding): {h['text']}", S["small"]))

    # --- сравнение -------------------------------------------------------------------
    comp = snap.get("comparison")
    if comp:
        invs = snap["investigations"]
        story.append(P("Compare investigations", S["h2"]))
        story.append(P(f"Comparability: {comp_l.get(comp['comparability']['status'], comp['comparability']['status'])}", S["base"]))
        for r in comp["comparability"]["reasons"]:
            story.append(P("• " + r["text"], S["small"]))
        hdr = [P("Attribute", S["cellb"])] + [P(i["acronym"], S["cellb"]) for i in invs]
        rows = [hdr]
        for row in comp["rows"]:
            rows.append([P(row["label"], S["cellb"])] +
                        [P(cl["value_text"] if cl["status"] == "known" else cell_l[cl["status"]], S["cell"]) for cl in row["cells"]])
        col = (W * 0.76) / len(invs)
        story.append(_table(rows, [W * 0.24] + [col] * len(invs)))

    # --- ограничения ------------------------------------------------------------------
    story.append(P("Limitations", S["h2"]))
    lims = [DISCLAIMER]
    scenarios = [snap["scenario"]] + [a["scenario_snapshot"] for a in snap["answers"]]
    if any(sc and sc["gravity_regime"] in ("partial", "simulated_partial") for sc in scenarios):
        lims.append("The PSI corpus contains no direct partial-gravity data (DR-07). Transferring microgravity findings "
                    "to the Moon or Mars requires separate justification.")
    if comp:
        lims += comp["limitations"]
    lims.append("This report was built from saved answers and the data revision listed above; no model was called during export.")
    for lim in dict.fromkeys(lims):
        story.append(P("• " + lim, S["base"]))

    # --- источники -----------------------------------------------------------------
    story.append(P("Original sources", S["h2"]))
    kind_s = _labels(snap, "source_kind")
    avail_s = _labels(snap, "source_availability")
    rows = [[P("№", S["cellb"]), P("Source", S["cellb"])]]
    for n, s in enumerate(snap["sources"], start=1):
        url = escape(s["canonical_url"])
        parts = [f"<b>{escape(s['title'])}</b>", f"{escape(kind_s.get(s['kind'], s['kind']))}; "
                 f"{escape(avail_s.get(s['availability'], s['availability']))}"]
        if s["doi"]:
            parts.append(f"DOI: {escape(s['doi'])}")
        parts.append(f'<link href="{url}" color="#1d4ed8">{url}</link>')
        parts.append(f"retrieved {escape(s['retrieved_at'][:10])}; id {escape(s['id'])}")
        rows.append([P(str(n), S["cell"]), Paragraph("<br/>".join(parts), S["cell"])])
    story.append(_table(rows, [W * 0.07, W * 0.93]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("FA", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"Fire Atlas · {snap['report_id']} · data {snap['data_revision']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"p. {doc.page}")
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(1.2)
        canvas.line(18 * mm, A4[1] - 12 * mm, 40 * mm, A4[1] - 12 * mm)
        canvas.restoreState()

    out = Path(out)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=snap["title"], author="Fire Atlas", subject="Research report",
                            creator="Fire Atlas API")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out


__all__ = ["render_report", "PageBreak"]
