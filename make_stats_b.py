#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_stats_b.py

두 번째 아이디용 차트 (숏돌이 글 차트와 다른 디자인).
팀별 최근 경기 득점·실점 꺾은선 그래프 + 최근 경기 성적표. 숫자는 kbl_<n>.json(공식 기록)에서만 읽음.
같은 폴더에 stats_<n>.json 이 있으면 아래에 최근 맞대결 요약도 붙인다.

사용법:
    python3 make_stats_b.py --data 글/312962/kbl_1.json --h2h 글/312962/stats_1.json --out 글/312962/stats_1.png
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(HERE, "로고")
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BOLD, MED = 6, 2

W = 1200
BG = (243, 245, 249)
CARD = (255, 255, 255)
INK = (22, 30, 52)
SUB = (104, 113, 132)
GRID = (230, 233, 240)
HEAD = (30, 41, 74)        # 패널 머리 띠
PF = (234, 88, 12)         # 득점 (주황)
PA = (22, 163, 74)         # 실점 (초록)
WIN = (37, 99, 235)
LOSE = (220, 38, 38)


def linux_font(weight_name):
    import glob
    for name in ([weight_name, "Regular"] if weight_name != "Bold" else ["Bold"]):
        hits = sorted(glob.glob(f"/usr/share/fonts/**/NotoSansCJK*-{name}.tt[co]", recursive=True))
        if hits:
            return hits[0]
    raise RuntimeError("한글 글꼴(Noto CJK)을 찾지 못했습니다.")


def font(size, w=BOLD):
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size, index=w)
    path = linux_font("Bold" if w == BOLD else "Medium")
    return ImageFont.truetype(path, size, index=1 if path.endswith(".ttc") else 0)


def logo(name, size):
    path = os.path.join(LOGO_DIR, f"{name}.png")
    if not os.path.exists(path):
        return None
    img = Image.open(path).convert("RGBA")
    box = img.getchannel("A").getbbox()
    if box:
        img = img.crop(box)
    img.thumbnail((size, size), Image.LANCZOS)
    return img


def panel(img, d, x0, y0, w, team):
    rec = team["recent"]
    # 머리 띠: 로고 + 팀명
    d.rounded_rectangle((x0, y0, x0 + w, y0 + 64), radius=14, fill=HEAD)
    lg = logo(team.get("logo", ""), 46)
    tx = x0 + 22
    if lg:
        img.alpha_composite(lg, (int(tx), int(y0 + 32 - lg.height / 2)))
        tx += lg.width + 14
    d.text((tx, y0 + 32), team["name"], font=font(28), fill=(255, 255, 255), anchor="lm")
    d.text((x0 + w - 22, y0 + 32), f"최근 {len(rec)}경기", font=font(20, MED), fill=(190, 200, 225), anchor="rm")

    # 꺾은선 그래프
    gx0, gx1, gy0, gy1 = x0 + 56, x0 + w - 24, y0 + 100, y0 + 330
    if rec:
        vals = [r["pf"] for r in rec] + [r["pa"] for r in rec]
        if max(vals) <= 15:  # 축구 골·배구 세트·야구 점수처럼 작으면 0부터, 눈금은 정수 간격 (2026-10-17)
            step = 1 if max(vals) <= 5 else 2 if max(vals) <= 10 else 3
            lo, hi = 0, (max(vals) // step + 1) * step
        else:
            step = 10
            lo, hi = max(0, (min(vals) // 10) * 10 - 10), (max(vals) // 10) * 10 + 10
        n_tick = int((hi - lo) / step)
        for k in range(n_tick + 1):  # 눈금 숫자와 칸이 정확히 맞게
            v = lo + step * k
            y = gy1 - (gy1 - gy0) * k / n_tick
            d.line([(gx0, y), (gx1, y)], fill=GRID, width=1)
            d.text((gx0 - 10, y), f"{v:.0f}", font=font(16, MED), fill=SUB, anchor="rm")
        n = len(rec)
        xs = [gx0 + (gx1 - gx0) * (i + 0.5) / n for i in range(n)]
        ys = lambda key: [gy1 - (gy1 - gy0) * (r[key] - lo) / (hi - lo) for r in rec]
        for key, color in (("pa", PA), ("pf", PF)):
            pts = list(zip(xs, ys(key)))
            d.line(pts, fill=color, width=4, joint="curve")
            for (px, py), r in zip(pts, rec):
                d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=CARD, outline=color, width=3)
        for x, r in zip(xs, rec):
            d.text((x, gy1 + 18), r["date"], font=font(16, MED), fill=SUB, anchor="mm")
        # 범례
        for k, (label, color) in enumerate(((LABELS[0], PF), (LABELS[1], PA))):
            lx = gx0 + 8 + k * 92
            d.line([(lx, gy0 - 22), (lx + 26, gy0 - 22)], fill=color, width=4)
            d.text((lx + 34, gy0 - 22), label, font=font(17, MED), fill=SUB, anchor="lm")

    # 성적표
    ty = gy1 + 52
    cols = [("일자", 0.10), (LABELS[0], 0.30), (LABELS[1], 0.46), ("결과", 0.63), ("상대", 0.84)]
    d.rectangle((x0, ty, x0 + w, ty + 40), fill=(236, 239, 246))
    for label, fx in cols:
        d.text((x0 + w * fx, ty + 20), label, font=font(18, MED), fill=SUB, anchor="mm")
    for i, r in enumerate(reversed(rec)):  # 최근 경기가 위
        y = ty + 40 + i * 42 + 21
        if i % 2:
            d.rectangle((x0, y - 21, x0 + w, y + 21), fill=(249, 250, 252))
        d.text((x0 + w * 0.10, y), r["date"], font=font(19, MED), fill=INK, anchor="mm")
        d.text((x0 + w * 0.30, y), str(r["pf"]), font=font(20), fill=PF, anchor="mm")
        d.text((x0 + w * 0.46, y), str(r["pa"]), font=font(20), fill=PA, anchor="mm")
        c = WIN if r["result"] == "승" else LOSE if r["result"] == "패" else (120, 128, 145)  # 무승부는 회색
        cx = x0 + w * 0.63
        d.rounded_rectangle((cx - 20, y - 15, cx + 20, y + 15), radius=6, fill=c)
        d.text((cx, y), r["result"], font=font(18), fill=(255, 255, 255), anchor="mm")
        d.text((x0 + w * 0.84, y), ("vs " if r.get("home") else "@ ") + r["opp"], font=font(19, MED), fill=INK, anchor="mm")
    return ty + 40 + len(rec) * 42


LABELS = ("득점", "실점")


def make(data, h2h, out):
    global LABELS
    LABELS = (data.get("pf_label", "득점"), data.get("pa_label", "실점"))  # 배구는 딴 세트·내준 세트
    rows = max(len(data["home"]["recent"]), len(data["away"]["recent"]))
    H = 140 + 64 + 330 + 52 + 40 + rows * 42 + (110 if h2h else 50)
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((40, 44), data["title"], font=font(34), fill=INK, anchor="lm")
    d.text((40, 88), data.get("when", ""), font=font(22, MED), fill=SUB, anchor="lm")
    d.text((W - 40, 44), "팀 흐름", font=font(22), fill=HEAD, anchor="rm")
    d.text((W - 40, 88), "출처 " + data.get("source", ""), font=font(18, MED), fill=SUB, anchor="rm")

    pw, gap, top = 548, 24, 130
    bottom = 0
    for k, team in enumerate((data["home"], data["away"])):
        x0 = 40 + k * (pw + gap)
        d.rounded_rectangle((x0 - 8, top - 8, x0 + pw + 8, H - (90 if h2h else 30)), radius=18, fill=CARD)
        bottom = max(bottom, panel(img, d, x0, top, pw, team))

    if h2h and h2h.get("h2h"):
        hh = h2h["h2h"]
        y = H - 52
        txt = f"최근 맞대결 {len(h2h.get('h2h_matches', []))}경기  ·  {data['home']['name']} {hh['home_w']}승  {data['away']['name']} {hh['away_w']}승"
        if hh.get("d"):
            txt += f"  무승부 {hh['d']}"
        d.rounded_rectangle((40, y - 28, W - 40, y + 28), radius=28, fill=HEAD)
        d.text((W // 2, y), txt, font=font(22), fill=(255, 255, 255), anchor="mm")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.convert("RGB").save(out, "PNG")
    print(f"차트 저장: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="kbl_<n>.json")
    ap.add_argument("--h2h", help="stats_<n>.json (있으면 맞대결 요약 추가)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    h2h = None
    if args.h2h and os.path.exists(args.h2h):
        with open(args.h2h, encoding="utf-8") as f:
            h2h = json.load(f)
    make(data, h2h, args.out)


if __name__ == "__main__":
    main()
