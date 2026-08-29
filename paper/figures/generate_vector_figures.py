#!/usr/bin/env python3
"""Regenerate the RAGWarrant arXiv vector figure PDFs.

The figures use only sanitized labels and aggregate rates from figure_data.json.
They do not read raw datasets, prompts, source documents, API responses, or
generated answers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "figure_data.json").read_text(encoding="utf-8"))
W, H = landscape(letter)


def wrap(c: canvas.Canvas, text: str, x: float, y: float, width: float, size: int = 8) -> float:
    c.setFillColor(colors.black)
    c.setFont("Helvetica", size)
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if c.stringWidth(candidate, "Helvetica", size) <= width:
            line = candidate
        else:
            c.drawString(x, y, line)
            y -= size + 2
            line = word
    if line:
        c.drawString(x, y, line)
    return y - size - 2


def box(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    body: str = "",
    fill=colors.HexColor("#EEF4FA"),
) -> None:
    c.setStrokeColor(colors.HexColor("#28536B"))
    c.setFillColor(fill)
    c.roundRect(x, y, w, h, 6, stroke=1, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x + w / 2, y + h - 14, title)
    if body:
        wrap(c, body, x + 8, y + h - 29, w - 16, 7)


def arrow(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float) -> None:
    c.setStrokeColor(colors.HexColor("#333333"))
    c.line(x1, y1, x2, y2)
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 7
    for offset in (math.pi * 0.82, -math.pi * 0.82):
        c.line(x2, y2, x2 + length * math.cos(angle + offset), y2 + length * math.sin(angle + offset))


def new_pdf(name: str) -> canvas.Canvas:
    c = canvas.Canvas(str(HERE / name), pagesize=landscape(letter))
    c.setTitle(name)
    return c


def figure_01() -> None:
    c = new_pdf("figure_01_governance_loop.pdf")
    steps = [
        ("Candidate policies", "retrieval, routing, context, generator"),
        ("Evidence & telemetry", "quality, cost, latency, risk"),
        ("Hard gates", "provenance, leakage, safety"),
        ("Promotion decision", "promote, reject, block, inconclusive"),
        ("Append-only ledger", "positive, mixed, negative evidence"),
    ]
    x, y, w, h = 45, 255, 125, 80
    for i, (title, body) in enumerate(steps):
        box(c, x + i * 145, y, w, h, title, body)
        if i < len(steps) - 1:
            arrow(c, x + i * 145 + w, y + h / 2, x + (i + 1) * 145, y + h / 2)
    arrow(c, x + 4 * 145 + w / 2, y, x + w / 2, 225)
    wrap(c, "Artifacts, telemetry, and negative results feed the next evaluation cycle.", 240, 215, 350, 10)
    c.save()


def figure_02() -> None:
    c = new_pdf("figure_02_decision_geometry.pdf")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(80, 520, "Quality preservation and operational gain must both pass")
    c.setStrokeColor(colors.black)
    c.line(100, 120, 100, 460)
    c.line(100, 120, 690, 120)
    c.setFont("Helvetica", 9)
    c.drawString(95, 470, "Quality delta")
    c.drawString(620, 100, "Cost or latency delta")
    c.setStrokeColor(colors.HexColor("#BBBBBB"))
    c.line(100, 260, 690, 260)
    c.line(395, 120, 395, 460)
    c.setFillColor(colors.HexColor("#DDF3E4"))
    c.rect(100, 260, 295, 200, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#F7DDDD"))
    c.rect(395, 120, 295, 340, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#F8EECF"))
    c.rect(100, 120, 295, 140, stroke=0, fill=1)
    box(c, 150, 335, 170, 58, "Promotable region", "quality above margin; cost or latency improves", colors.white)
    box(c, 445, 320, 170, 58, "No operational gain", "quality may pass, but efficiency does not", colors.white)
    box(c, 155, 160, 170, 58, "Quality loss", "operational savings blocked", colors.white)
    c.save()


def figure_03() -> None:
    c = new_pdf("figure_03_evidence_ladder.pdf")
    levels = [
        "0 synthetic",
        "1 smoke/fixture",
        "2 external transfer",
        "3 public development",
        "4 public confirmatory",
        "5 multi-corpus mixed",
        "6 bounded generative",
        "7 human/platform/prod",
    ]
    for i, level in enumerate(levels):
        yy = 85 + i * 48
        fill = colors.HexColor("#DDECF6") if i <= 6 else colors.HexColor("#F2F2F2")
        box(c, 130, yy, 520, 32, level, "claim ceiling increases with evidence class", fill)
        if i < 6:
            arrow(c, 390, yy + 32, 390, yy + 48)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(120, 500, "Evidence ladder: bounded public/generative evidence, not Level 7")
    c.save()


def figure_04() -> None:
    c = new_pdf("figure_04_cloud_job_contract.pdf")
    stages = [
        ("Inputs", "policy configs; metrics/evidence; constraints"),
        ("Container job", "finite runner; validator; no raw data export"),
        ("Outputs", "decision JSON; audit bundle; validation report"),
    ]
    x = 90
    for i, (title, body) in enumerate(stages):
        box(c, x + i * 230, 285, 170, 95, title, body)
        if i < 2:
            arrow(c, x + i * 230 + 170, 332, x + (i + 1) * 230, 332)
    box(
        c,
        265,
        150,
        260,
        70,
        "Publication hygiene boundary",
        "raw datasets, prompts, generated answers, secrets, and private paths are excluded",
        colors.HexColor("#FFF2CC"),
    )
    arrow(c, 405, 285, 405, 220)
    c.save()


def figure_05() -> None:
    c = new_pdf("figure_05_evidence_map.pdf")
    items = [
        ("Positive", "CRAG mock API; source/retrieval"),
        ("Bounded", "public mini; Docker job"),
        ("Mixed", "generative CRAG; repeat offsets"),
        ("Negative", "HotpotQA; quality loss"),
        ("Blocked", "quality-risk; guardrail v2"),
    ]
    fills = ["#DDF3E4", "#DDECF6", "#F8EECF", "#F7DDDD", "#E8E8E8"]
    for i, ((title, body), fill) in enumerate(zip(items, fills)):
        box(c, 70 + i * 140, 285, 105, 90, title, body, colors.HexColor(fill))
        if i < 4:
            arrow(c, 70 + i * 140 + 105, 330, 70 + (i + 1) * 140, 330)
    wrap(c, "The ledger preserves the evidence arc rather than collapsing results into one leaderboard.", 190, 230, 420, 11)
    c.save()


def figure_06() -> None:
    c = new_pdf("figure_06_selector_stress_test.pdf")
    rows = DATA["selector_ablation"]
    labels = [r["selector"] for r in rows]
    blocked = [float(r["blocked_rate"]) for r in rows]
    loss = [float(r["quality_loss_rate"]) for r in rows]
    c.setFont("Helvetica-Bold", 12)
    c.drawString(75, 520, "Selector stress test: blocked rate and quality-loss rate")
    chart_x, chart_y, chart_w, chart_h = 70, 140, 650, 320
    c.setStrokeColor(colors.black)
    c.line(chart_x, chart_y, chart_x, chart_y + chart_h)
    c.line(chart_x, chart_y, chart_x + chart_w, chart_y)
    for value in (0, 0.25, 0.5, 0.75, 1.0):
        yy = chart_y + value * chart_h
        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.line(chart_x, yy, chart_x + chart_w, yy)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7)
        c.drawRightString(chart_x - 5, yy - 3, f"{value:.2f}")
    group = chart_w / len(labels)
    bw = group * 0.32
    for i, label in enumerate(labels):
        x0 = chart_x + i * group + group * 0.18
        for j, (value, color) in enumerate(((blocked[i], "#3B6EA8"), (loss[i], "#D98A30"))):
            c.setFillColor(colors.HexColor(color))
            c.rect(x0 + j * bw, chart_y, bw, value * chart_h, stroke=0, fill=1)
        c.saveState()
        c.translate(x0 + bw, chart_y - 8)
        c.rotate(55)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 6)
        c.drawRightString(0, 0, label.replace("_", " "))
        c.restoreState()
    c.setFillColor(colors.HexColor("#3B6EA8"))
    c.rect(540, 500, 12, 8, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.drawString(557, 499, "blocked rate")
    c.setFillColor(colors.HexColor("#D98A30"))
    c.rect(620, 500, 12, 8, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.drawString(637, 499, "quality-loss rate")
    c.save()


def main() -> None:
    figure_01()
    figure_02()
    figure_03()
    figure_04()
    figure_05()
    figure_06()
    print("Regenerated 6 vector figure PDFs in", HERE)


if __name__ == "__main__":
    main()
