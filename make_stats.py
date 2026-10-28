#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_stats.py

전력 비교 차트 이미지(1200px 폭 PNG)를 만든다. 배너 아래, 본문 위에 붙이는 용도.
숫자는 stats.json 에서만 읽는다 (임의로 만들지 않음).

사용법:
    python3 make_stats.py --data 글/312942/stats.json --out 글/312942/stats.png

stats.json 예:
{
  "league": "A리그 2026/27", "basis": "지난 시즌 정규리그 기준",
  "home": {"name": "시드니FC", "logo": "Sydney FC", "rank": "5위", "points": 40,
           "w": 11, "d": 7, "l": 8, "gf": 41, "ga": 33, "form": ["승","무","승","패","승"]},
  "away": {...},
  "h2h": {"home_w": 4, "d": 1, "away_w": 1, "label": "최근 맞대결 6경기"},
  "sample": true   # true면 '디자인 시안 · 예시 숫자' 표시
}
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
BG = (11, 17, 31)
PANEL = (19, 28, 48)
LINE = (38, 50, 76)
WHITE = (240, 244, 250)
MUTED = (140, 153, 178)
HOME = (66, 153, 225)
AWAY = (232, 72, 85)
FORM = {"승": (46, 160, 110), "무": (120, 128, 145), "패": (200, 70, 80)}
WARN = (240, 180, 80)


def linux_font(weight_name):
    """서버(리눅스)의 Noto CJK 글꼴 파일을 찾는다. Medium이 없으면 Regular."""
    import glob
    for name in ([weight_name, "Regular"] if weight_name != "Bold" else ["Bold"]):
        hits = sorted(glob.glob(f"/usr/share/fonts/**/NotoSansCJK*-{name}.tt[co]", recursive=True))
        if hits:
            return hits[0]
    raise RuntimeError("한글 글꼴(Noto CJK)을 찾지 못했습니다.")


def font(size, w=BOLD):
    w_ = w
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size, index=w_)
    path = linux_font("Bold" if w_ == BOLD else "Medium")
    return ImageFont.truetype(path, size, index=1 if path.endswith(".ttc") else 0)  # ttc 1번 = 한국어(KR)


def logo(name, size):
    path = os.path.join(LOGO_DIR, f"{name}.png")
    if not os.path.exists(path):
        return None
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return img


def per_game(v, gp):
    return round(v / gp, 2) if gp else 0


def make(data, out):
    h, a = data["home"], data["away"]
    season = "w" in h  # 시즌 기록이 없으면(무료 API 범위 밖) 상대 전적만 그림
    for t in (h, a):
        t["gp"] = t["w"] + t["d"] + t["l"] if season else 0

    rows = [] if not season else [
        ("순위", h["rank"], a["rank"], None),
        ("승점", str(h["points"]), str(a["points"]), (h["points"], a["points"])),
        ("전적", f'{h["w"]}승 {h["d"]}무 {h["l"]}패', f'{a["w"]}승 {a["d"]}무 {a["l"]}패', None),
        ("득점 / 실점", f'{h["gf"]} / {h["ga"]}', f'{a["gf"]} / {a["ga"]}', None),
        ("평균 득점", f'{per_game(h["gf"], h["gp"]):.2f}', f'{per_game(a["gf"], a["gp"]):.2f}',
         (per_game(h["gf"], h["gp"]), per_game(a["gf"], a["gp"]))),
        ("평균 실점", f'{per_game(h["ga"], h["gp"]):.2f}', f'{per_game(a["ga"], a["gp"]):.2f}',
         (per_game(h["ga"], h["gp"]), per_game(a["ga"], a["gp"]))),
    ]

    top, row_h = 196, 64
    form_y = top + row_h * len(rows) + 30
    h2h_y = form_y + 130 if season else top + 30
    matches = data.get("h2h_matches", [])
    list_y = h2h_y + 150
    H = list_y + (len(matches) * 58 + 30 if matches else 0)

    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 헤더: 리그 / 기준 / 팀
    d.text((40, 36), data.get("league", ""), font=font(30), fill=WHITE)
    d.text((40, 78), data.get("basis", ""), font=font(22, MED), fill=MUTED)
    if data.get("sample"):
        tag = "디자인 시안 · 숫자는 예시"
        tw = d.textlength(tag, font=font(20))
        d.rounded_rectangle((W - 40 - tw - 28, 34, W - 40, 72), radius=19, outline=WARN, width=2)
        d.text((W - 40 - tw - 14, 53), tag, font=font(20), fill=WARN, anchor="lm")

    cx = W // 2
    for t, x, color, anchor in ((h, 300, HOME, "mm"), (a, 900, AWAY, "mm")):
        lg = logo(t.get("logo", ""), 56)
        label = t["name"]
        if lg:
            tw = d.textlength(label, font=font(30))
            sx = int(x - (lg.width + 12 + tw) / 2)
            img.alpha_composite(lg, (sx, 146 - lg.height // 2))
            d.text((sx + lg.width + 12, 146), label, font=font(30), fill=WHITE, anchor="lm")
        else:
            d.text((x, 146), label, font=font(30), fill=WHITE, anchor=anchor)
    d.line([(40, top - 6), (W - 40, top - 6)], fill=LINE, width=2)

    # 비교 행: 왼쪽 홈 값 | 가운데 항목 | 오른쪽 원정 값, 숫자 행은 양쪽 막대
    bar_max = 230
    for i, (label, hv, av, nums) in enumerate(rows):
        y = top + i * row_h + row_h // 2
        if i % 2 == 0:
            d.rectangle((40, y - row_h // 2, W - 40, y + row_h // 2), fill=PANEL)
        d.rounded_rectangle((cx - 90, y - 20, cx + 90, y + 20), radius=8, fill=LINE)
        d.text((cx, y), label, font=font(22, MED), fill=WHITE, anchor="mm")
        if nums:
            m = max(nums) or 1
            hw, aw = int(bar_max * nums[0] / m), int(bar_max * nums[1] / m)
            d.rounded_rectangle((cx - 110 - bar_max, y - 9, cx - 110, y + 9), radius=9, fill=LINE)
            d.rounded_rectangle((cx + 110, y - 9, cx + 110 + bar_max, y + 9), radius=9, fill=LINE)
            if hw:
                d.rounded_rectangle((cx - 110 - hw, y - 9, cx - 110, y + 9), radius=9, fill=HOME)
            if aw:
                d.rounded_rectangle((cx + 110, y - 9, cx + 110 + aw, y + 9), radius=9, fill=AWAY)
            d.text((cx - 130 - bar_max, y), hv, font=font(26), fill=WHITE, anchor="rm")
            d.text((cx + 130 + bar_max, y), av, font=font(26), fill=WHITE, anchor="lm")
        else:
            d.text((cx - 130, y), hv, font=font(26), fill=WHITE, anchor="rm")
            d.text((cx + 130, y), av, font=font(26), fill=WHITE, anchor="lm")

    # 최근 경기 결과 칩
    if season:
        d.text((cx, form_y + 10), "최근 5경기 (왼쪽이 최근)", font=font(22, MED), fill=MUTED, anchor="mm")
    chip, gap = 54, 10
    for t, right_align in (((h, True), (a, False)) if season else ()):
        form = t.get("form", [])[:5]
        total = len(form) * chip + (len(form) - 1) * gap
        x0 = cx - 110 - total if right_align else cx + 110
        for j, r in enumerate(form):
            x = x0 + j * (chip + gap)
            d.rounded_rectangle((x, form_y + 40, x + chip, form_y + 40 + chip), radius=10, fill=FORM.get(r, LINE))
            d.text((x + chip / 2, form_y + 40 + chip / 2), r, font=font(26), fill=WHITE, anchor="mm")

    # 상대 전적 막대
    hh = data.get("h2h")
    if hh:
        total = hh["home_w"] + hh["d"] + hh["away_w"]
        d.text((cx, h2h_y), hh.get("label", "상대 전적"), font=font(22, MED), fill=MUTED, anchor="mm")
        x0, x1, by = 140, W - 140, h2h_y + 46
        segs = [(hh["home_w"], HOME, f'{h["name"]} {hh["home_w"]}승'),
                (hh["d"], FORM["무"], f'{hh["d"]}무'),
                (hh["away_w"], AWAY, f'{a["name"]} {hh["away_w"]}승')]
        x = x0
        for n, color, _ in segs:
            if not n:
                continue
            w = (x1 - x0) * n / total
            d.rectangle((x, by - 18, x + w, by + 18), fill=color)
            d.text((x + w / 2, by), str(n), font=font(24), fill=WHITE, anchor="mm")
            x += w
        d.text((x0, by + 48), segs[0][2], font=font(22), fill=HOME, anchor="lm")
        d.text((cx, by + 48), segs[1][2], font=font(22), fill=MUTED, anchor="mm")
        d.text((x1, by + 48), segs[2][2], font=font(22), fill=AWAY, anchor="rm")

    # 상대 전적 경기 목록 (날짜 | 홈 스코어 원정 | 결과)
    for k, m in enumerate(matches):
        y = list_y + k * 58 + 29
        if k % 2 == 0:
            d.rectangle((140, y - 29, W - 140, y + 29), fill=PANEL)
        d.text((170, y), m["date"], font=font(22, MED), fill=MUTED, anchor="lm")
        d.text((cx - 60, y), m["home"], font=font(24), fill=WHITE, anchor="rm")
        d.text((cx, y), m["score"], font=font(26), fill=WHITE, anchor="mm")
        d.text((cx + 60, y), m["away"], font=font(24), fill=WHITE, anchor="lm")
        r = m.get("result", "")
        if r:
            d.rounded_rectangle((W - 140 - 66, y - 19, W - 140 - 20, y + 19), radius=8, fill=FORM.get(r, LINE))
            d.text((W - 140 - 43, y), r, font=font(22), fill=WHITE, anchor="mm")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.convert("RGB").save(out, "PNG")
    print(f"차트 저장: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="stats.json 경로")
    ap.add_argument("--out", required=True, help="저장할 PNG 경로")
    args = ap.parse_args()
    with open(args.data, encoding="utf-8") as f:
        make(json.load(f), args.out)


if __name__ == "__main__":
    main()
