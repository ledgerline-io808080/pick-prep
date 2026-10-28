#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_pitcher_card.py

야구용 선발 투수 맞대결 카드(가로 1200, PNG 무손실). 데이터는 mlb_data.py 가 만든 pitcher_<n>.json
(MLB 공식 기록 그대로). 카드가 어두운 남색 바탕이라 사이트 주간·야간 어디서나 같은 대비. 왼쪽 위 배지.

사용법:
    python3 make_pitcher_card.py --data 글/312441/pitcher_1.json --out 글/312441/pitcher_1.png
"""
import argparse
import datetime
import json
import os

from PIL import Image, ImageDraw

from make_banner import FONT_MEDIUM, HERE, fit, font, get_logo, load_alias, placeholder

W = 1200
BG_TOP, BG_BOTTOM = (16, 28, 54), (26, 12, 24)       # 남색 → 짙은 자주 (야구장 밤 느낌)
PANEL = (22, 34, 62)
BOX = (30, 46, 80)
RED = (185, 28, 28)                                   # 팀 칩 (흰 글자 대비 6.4)
LINE = (220, 38, 38)
WHITE = (248, 250, 252)
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)
GOLD = (253, 224, 71)


def kdate(s):
    d = datetime.date.fromisoformat(s)
    return f"{d.month}/{d.day}"


def column(canvas, d, x0, x1, y0, p, team_en, color):
    cx = (x0 + x1) / 2
    d.rounded_rectangle((x0, y0, x1, y0 + 560), radius=18, fill=PANEL)
    # 팀 칩 + 엠블럼
    chip = p["team"]
    cw = d.textlength(chip, font=font(28)) + 56
    d.rounded_rectangle((cx - cw / 2, y0 + 22, cx + cw / 2, y0 + 70), radius=24, fill=RED)
    d.text((cx, y0 + 46), chip, font=font(28), fill=WHITE, anchor="mm")
    try:
        logo = get_logo(p["team"], team_en)
    except Exception:
        logo = placeholder(p["team"], color)
    logo = fit(logo, 84)  # 줄이기만 함
    canvas.alpha_composite(logo, (int(cx - logo.width / 2), int(y0 + 120 - logo.height / 2)))
    d = ImageDraw.Draw(canvas)
    # 투수 이름
    d.text((cx, y0 + 200), p.get("name_ko") or p.get("name_en") or "미정", font=font(50), fill=WHITE, anchor="mm")
    d.text((cx, y0 + 244), p.get("name_en", ""), font=font(24, FONT_MEDIUM), fill=MUTED, anchor="mm")
    # 시즌 기록 4칸
    s = p.get("season", {})
    cells = [("시즌 승패", f"{s.get('w', '-')}승 {s.get('l', '-')}패"), ("평균자책점", s.get("era", "-")),
             ("이닝", s.get("ip", "-")), ("탈삼진", str(s.get("so", "-")))]
    bw = (x1 - x0 - 40 - 3 * 12) / 4
    for k, (lab, val) in enumerate(cells):
        bx = x0 + 20 + k * (bw + 12)
        d.rounded_rectangle((bx, y0 + 280, bx + bw, y0 + 384), radius=12, fill=BOX)
        d.text((bx + bw / 2, y0 + 308), lab, font=font(20, FONT_MEDIUM), fill=MUTED, anchor="mm")
        d.text((bx + bw / 2, y0 + 350), val, font=font(32), fill=GOLD if lab == "평균자책점" else WHITE, anchor="mm")
    # 최근 3경기
    d.text((x0 + 24, y0 + 412), "최근 3경기", font=font(24), fill=TEXT)
    for k, r in enumerate(p.get("recent", [])):
        y = y0 + 452 + k * 34
        tag = " (PS)" if r.get("post") else ""
        d.text((x0 + 24, y), f"{kdate(r['date'])}  vs {r['opp']}{tag}", font=font(21, FONT_MEDIUM), fill=TEXT)
        d.text((x1 - 24, y), f"{r['ip']}이닝 {r['er']}자책 {r['so']}K", font=font(21, FONT_MEDIUM), fill=WHITE, anchor="ra")
    return d


def make(data, out, home_en, away_en):
    H = 760
    canvas = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(canvas)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    d.rounded_rectangle((10, 10, W - 11, H - 11), radius=24, outline=LINE, width=3)

    # 배지는 여기서 넣지 않음 (공개 쪽 코드에는 사이트 표시 없음, 등록 쪽에서 얹음)
    d.text((W // 2, 52), "선발 투수 맞대결", font=font(40), fill=WHITE, anchor="mm")
    sub = " · ".join(x for x in (data.get("game"), data.get("label")) if x)
    d.text((W // 2, 96), sub, font=font(24, FONT_MEDIUM), fill=MUTED, anchor="mm")

    col_w = (W - 40 * 2 - 80) / 2
    y0 = 128
    d = column(canvas, d, 40, 40 + col_w, y0, data["home"], home_en, (40, 110, 200))
    d = column(canvas, d, W - 40 - col_w, W - 40, y0, data["away"], away_en, (190, 30, 50))
    d.ellipse((W / 2 - 34, y0 + 166, W / 2 + 34, y0 + 234), outline=LINE, width=3)
    d.text((W / 2, y0 + 200), "VS", font=font(30), fill=WHITE, anchor="mm")
    d.text((W / 2, H - 34), f"출처 {data.get('source', 'MLB 공식 기록')} · 시즌 기록은 정규시즌 · PS = 포스트시즌",
           font=font(19, FONT_MEDIUM), fill=MUTED, anchor="mm")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.convert("RGB").save(out, "PNG")
    print(f"선발 카드 저장: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--home-en", default="")
    ap.add_argument("--away-en", default="")
    a = ap.parse_args()
    with open(a.data, encoding="utf-8") as f:
        data = json.load(f)
    alias = load_alias()
    make(data, a.out, a.home_en or alias.get(data["home"]["team"], ""), a.away_en or alias.get(data["away"]["team"], ""))


if __name__ == "__main__":
    main()
