"""BE-09: PDF исследовательского отчета из зафиксированного снимка (без вызова модели).

Содержимое (13.10, 6.7): заголовок, дата и версии, контекст каждого ответа (разные сценарии -
отдельные разделы), блоки ответа с пометкой типа, применимость, выбранные исследования
(гипотезы отдельно), сравнение, ограничения, первоисточники со ссылками.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
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
    "answered": "Ответ по найденным доказательствам",
    "insufficient_evidence": "Недостаточно доказательств",
    "conflicting_evidence": "Доказательства расходятся",
}
DISCLAIMER = ("Отчет предназначен для исследовательского обсуждения. Он не является заключением о безопасности, "
              "сертификацией материала, оценкой вероятности пожара или инструкцией для экипажа. "
              "Отсутствие данных не означает безопасность.")

FIELD_LABELS = {
    "gravity_regime": "Режим гравитации", "safety_task": "Задача безопасности", "material_ids": "Материал",
    "oxygen_fraction": "Доля кислорода", "pressure": "Давление", "airflow_speed": "Скорость потока",
    "geometry": "Геометрия", "flow_configuration": "Направление потока", "ambient_temperature": "Температура среды",
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
        return "не задано"
    if q["value"] is None:
        return {"not_reported": "не сообщено", "not_applicable": "неприменимо", "unusable": "непригодно"}.get(q["status"], "-")
    raw = f" (в источнике: {q['raw_value']} {q['raw_unit'] or ''})".rstrip() if q.get("raw_value") else ""
    return fmt_value(q["value"], q["unit"]) + raw


def _scenario_rows(snap, sc, S) -> list:
    L = {k: _labels(snap, k) for k in ("environment", "celestial_body", "scope", "gravity_regime", "geometry")}
    if sc is None:
        return [[P("Сценарий", S["cellb"]), P("не задан", S["cell"])]]
    rows = [
        ("Сценарий", sc["name"]),
        ("Среда", L["environment"].get(sc["environment"], sc["environment"])),
        ("Небесное тело", L["celestial_body"].get(sc["celestial_body"], sc["celestial_body"]) if sc["celestial_body"] else "не указано"),
        ("Задача", L["scope"].get(sc["safety_task"], sc["safety_task"])),
        ("Целевой режим гравитации", L["gravity_regime"].get(sc["gravity_regime"], sc["gravity_regime"])),
        ("Доля кислорода", _qtext(sc["oxygen_fraction"])),
        ("Давление", _qtext(sc["pressure"])),
        ("Скорость потока", _qtext(sc["airflow_speed"])),
        ("Геометрия", L["geometry"].get(sc["geometry"], sc["geometry"]) if sc["geometry"] else "не задана"),
    ]
    origin = {"user": "задано пользователем", "preset_source": "из пресета с источником", "derived": "вычислено"}
    for a in sc["assumptions"]:
        rows.append((f"Допущение: {FIELD_LABELS.get(a['field'], a['field'])}", f"{a['text']} ({origin.get(a['origin'], a['origin'])})"))
    return [[P(k, S["cellb"]), P(v, S["cell"])] for k, v in rows]


def _ctx_key(sc) -> str:
    return json.dumps(sc, sort_keys=True, ensure_ascii=False) if sc else "null"


def render_report(snap: dict, out: Path, font_dir: Path) -> Path:
    _fonts(Path(font_dir))
    S = _styles()
    W = A4[0] - 36 * mm
    src_num = {s["id"]: n for n, s in enumerate(snap["sources"], start=1)}
    kind_l = _labels(snap, "answer_block_kind")
    claim_l = _labels(snap, "claim_kind")
    factor_l = _labels(snap, "factor_status")
    overall_l = _labels(snap, "applicability_overall")
    comp_l = _labels(snap, "comparability_status")
    cell_l = {"not_reported": "не сообщено", "not_applicable": "неприменимо"}
    story: list = []

    # --- титул и версии --------------------------------------------------------
    story += [P(snap["title"], S["h1"]), P("Исследовательский отчет Fire Atlas по данным NASA PSI", S["sub"])]
    revs = sorted({(a["reasoning_revision"], a["retrieval_mode"]) for a in snap["answers"]})
    meta = [
        ("Создан (UTC)", snap["created_at"].replace("T", " ").replace("Z", "")),
        ("Версия данных корпуса", snap["data_revision"]),
        ("Версия контракта API", snap["contract_version"]),
        ("Ревизия рабочего пространства", str(snap["workspace_revision"])),
        ("Идентификатор отчета", snap["report_id"]),
    ]
    if revs:
        meta.append(("Версии ответа и режим поиска", "; ".join(f"{r} / {m}" for r, m in revs)))
    story.append(_table([[P(k, S["cellb"]), P(v, S["cell"])] for k, v in meta], [W * 0.34, W * 0.66], header=False))
    story.append(Spacer(1, 6))
    story.append(P(DISCLAIMER, S["note"]))

    story.append(P("Контекст пространства на момент экспорта", S["h2"]))
    story.append(_table(_scenario_rows(snap, snap["scenario"], S), [W * 0.34, W * 0.66], header=False))

    # --- ответы, сгруппированные по контексту -------------------------------------
    if snap["answers"]:
        groups: dict[str, list] = {}
        for a in snap["answers"]:
            groups.setdefault(_ctx_key(a["scenario_snapshot"]), []).append(a)
        cur_key = _ctx_key(snap["scenario"])
        story.append(P("Ответы", S["h2"]))
        if len(groups) > 1:
            story.append(P("Ответы получены в разных контекстах сценария. Они приведены отдельными разделами и не объединяются "
                           "в общий вывод.", S["note"]))
        n_answer = 0
        for gi, (key, answers) in enumerate(groups.items(), start=1):
            sc = answers[0]["scenario_snapshot"]
            title = sc["name"] if sc else "без сценария"
            story.append(P(f"Контекст {gi}: {title}", S["h3"]))
            if key == cur_key:
                story.append(P("Совпадает с текущим контекстом пространства (условия приведены выше).", S["small"]))
            else:
                story.append(P("Внимание: этот контекст отличается от текущего сценария пространства. Ответы относятся только "
                               "к условиям, указанным ниже.", S["small"]))
                story.append(_table(_scenario_rows(snap, sc, S), [W * 0.34, W * 0.66], header=False))
            for a in answers:
                n_answer += 1
                ev_src = {cit["evidence_id"]: cit["source_id"] for cit in a["citations"]}
                head = [P(f"Вопрос {n_answer}. {a['question']}", S["h3"]),
                        P(f"{STATUS_TEXT.get(a['status'], a['status'])} · получен {a['created_at'][:16].replace('T', ' ')} UTC · "
                          f"данные {a['data_revision']} · ревизия пространства {a['workspace_revision']}", S["small"])]
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
                    story.append(P(f"Применимость: {overall_l.get(ap['overall'], ap['overall'])} "
                                   f"(правила {ap['basis']['reviewed_rules_version']})", S["h3"]))
                    frows = [[P("Условие", S["cellb"]), P("Статус", S["cellb"]), P("Пояснение", S["cellb"])]]
                    frows += [[P(FIELD_LABELS.get(f["field"], f["field"]), S["cell"]), P(factor_l.get(f["status"], f["status"]), S["cell"]),
                               P(f["explanation"], S["cell"])] for f in ap["factors"]]
                    story.append(_table(frows, [W * 0.22, W * 0.18, W * 0.60]))
                    for g in ap["gaps"]:
                        story.append(P(f"Пробел данных - {FIELD_LABELS.get(g['field'], g['field'])}: {g['description']}"
                                       + (f" Следующий шаг: {g['suggested_next_step']}" if g["suggested_next_step"] else ""),
                                       S["small"]))
                for lim in a["limitations"]:
                    story.append(P(f"Ограничение: {lim}", S["small"]))
                if a["follow_up_questions"]:
                    story.append(P("Уточняющие вопросы: " + " · ".join(a["follow_up_questions"]), S["small"]))
                story.append(Spacer(1, 6))

    # --- исследования --------------------------------------------------------------
    if snap["investigations"]:
        story.append(P("Выбранные исследования", S["h2"]))
        claims_by = {}
        for cl in snap["claims"]:
            for i in cl["investigation_ids"]:
                claims_by.setdefault(i, []).append(cl)
        for inv in snap["investigations"]:
            refs = " ".join(f"[{src_num[s]}]" for s in inv["source_ids"] if s in src_num)
            story.append(P(f"{inv['acronym']} ({inv['psi_id']}) - {inv['title']} {refs}", S["h3"]))
            if inv["objectives"]:
                story.append(P("Цель: " + "; ".join(inv["objectives"]), S["base"]))
            if inv["setup_summary"]:
                story.append(P("Установка: " + inv["setup_summary"], S["base"]))
            results = [cl for cl in claims_by.get(inv["id"], []) if cl["kind"] in ("observation", "synthesis")]
            hyps = [cl for cl in claims_by.get(inv["id"], []) if cl["kind"] == "hypothesis"]
            if results:
                rows = [[P("Тип", S["cellb"]), P("Проверенный вывод", S["cellb"]), P("Ограничения", S["cellb"])]]
                rows += [[P(claim_l.get(cl["kind"], cl["kind"]), S["cell"]), P(cl["text"], S["cell"]),
                          P("; ".join(cl["limitations"]) or "-", S["cell"])] for cl in results]
                story.append(_table(rows, [W * 0.16, W * 0.54, W * 0.30]))
            for h in hyps:
                story.append(P(f"Исходная гипотеза (не результат): {h['text']}", S["small"]))

    # --- сравнение -------------------------------------------------------------------
    comp = snap.get("comparison")
    if comp:
        invs = snap["investigations"]
        story.append(P("Сравнение исследований", S["h2"]))
        story.append(P(f"Сопоставимость: {comp_l.get(comp['comparability']['status'], comp['comparability']['status'])}", S["base"]))
        for r in comp["comparability"]["reasons"]:
            story.append(P("• " + r["text"], S["small"]))
        hdr = [P("Признак", S["cellb"])] + [P(i["acronym"], S["cellb"]) for i in invs]
        rows = [hdr]
        for row in comp["rows"]:
            rows.append([P(row["label"], S["cellb"])] +
                        [P(cl["value_text"] if cl["status"] == "known" else cell_l[cl["status"]], S["cell"]) for cl in row["cells"]])
        col = (W * 0.76) / len(invs)
        story.append(_table(rows, [W * 0.24] + [col] * len(invs)))

    # --- ограничения ------------------------------------------------------------------
    story.append(P("Ограничения", S["h2"]))
    lims = [DISCLAIMER]
    scenarios = [snap["scenario"]] + [a["scenario_snapshot"] for a in snap["answers"]]
    if any(sc and sc["gravity_regime"] in ("partial", "simulated_partial") for sc in scenarios):
        lims.append("Корпус PSI не содержит прямых данных частичной гравитации (DR-07). Перенос результатов микрогравитации "
                    "на Луну или Марс требует отдельного обоснования.")
    if comp:
        lims += comp["limitations"]
    lims.append("Отчет построен из сохраненных ответов и версии данных, указанных выше; при экспорте модель не вызывалась.")
    for lim in dict.fromkeys(lims):
        story.append(P("• " + lim, S["base"]))

    # --- источники -----------------------------------------------------------------
    story.append(P("Первоисточники", S["h2"]))
    kind_s = _labels(snap, "source_kind")
    avail_s = _labels(snap, "source_availability")
    rows = [[P("№", S["cellb"]), P("Источник", S["cellb"])]]
    for n, s in enumerate(snap["sources"], start=1):
        url = escape(s["canonical_url"])
        parts = [f"<b>{escape(s['title'])}</b>", f"{escape(kind_s.get(s['kind'], s['kind']))}; "
                 f"{escape(avail_s.get(s['availability'], s['availability']))}"]
        if s["doi"]:
            parts.append(f"DOI: {escape(s['doi'])}")
        parts.append(f'<link href="{url}" color="#1d4ed8">{url}</link>')
        parts.append(f"получен {escape(s['retrieved_at'][:10])}; id {escape(s['id'])}")
        rows.append([P(str(n), S["cell"]), Paragraph("<br/>".join(parts), S["cell"])])
    story.append(_table(rows, [W * 0.07, W * 0.93]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("FA", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"Fire Atlas · {snap['report_id']} · данные {snap['data_revision']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"стр. {doc.page}")
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(1.2)
        canvas.line(18 * mm, A4[1] - 12 * mm, 40 * mm, A4[1] - 12 * mm)
        canvas.restoreState()

    out = Path(out)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=snap["title"], author="Fire Atlas", subject="Исследовательский отчет",
                            creator="Fire Atlas API")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out


__all__ = ["render_report", "PageBreak"]
