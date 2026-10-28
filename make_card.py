#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_card.py

배구용 분석 카드 이미지(가로 1200, 세로는 글 길이에 맞춤, PNG 무손실) — 2026-10-16 지시:
"분석글은 이미지(HOME/AWAY 칸에 문단), 밑에는 텍스트로 승부 분석과 추천 픽".
원문 이미지는 쓰지 않고, 다시 쓴 본문(스타일 D)의 홈·원정 문단을 우리 디자인으로 그린다.
카드 자체가 어두운 배경이라 사이트 주간·야간 모드 어디서나 같은 대비로 보인다. 왼쪽 위 배지 (배너와 같은 크기·자리).

본문(post.json body)에서 쓰는 부분: "▣ <홈팀>" / "▣ <원정팀>" 아래 문단 (승부 분석·픽은 이미지 밑 글자로 올라감)
조합 픽이면 "@@경기N" 묶음마다 카드 1장.

사용법:
    python3 make_card.py --post 글/ls241158 --match 1 --league "KOVO컵 여자배구" --out 글/ls241158/card_1.png
"""
import argparse
import json
import os
import re

from PIL import Image, ImageDraw

from make_banner import FONT_MEDIUM, HERE, fit, font, get_logo, load_alias, placeholder

W = 1200
PAD = 40
BG_TOP, BG_BOTTOM = (30, 22, 60), (14, 11, 32)       # 짙은 보라 → 남색 (축구 초록·농구 파랑과 다르게)
PANEL = (24, 18, 48)
FRAME = (226, 205, 150)                              # 금빛 테두리
CHIP = (232, 214, 160)                               # 금빛 칩 (진한 글자)
CHIP_TEXT = (40, 28, 70)
WHITE = (248, 246, 255)
TEXT = (232, 228, 245)                               # 문단 글자 (배경 대비 13 이상)
MUTED = (176, 166, 214)
GOLD = (253, 224, 71)


def sections(text):
    """'▣ 제목' 으로 나눈 {제목: [줄]}"""
    out, cur = {}, None
    for line in text.split("\n"):
        line = line.strip().replace("**", "")
        if line.startswith("▣"):
            cur = line.lstrip("▣ ").strip()
            out[cur] = []
        elif cur and line and not line.startswith("▶ 픽:"):
            out[cur].append(line.lstrip("-·• ").strip())
    return out


def blocks(body):
    parts = re.split(r"(?m)^@@(경기\d+|결론)\s*$", body)
    if len(parts) == 1:
        return {"경기1": body}
    return dict(zip(parts[1::2], parts[2::2]))


def wrap(d, text, f, width):
    """낱말 단위로 줄바꿈 (낱말이 너무 길면 글자 단위)."""
    lines, cur = [], ""
    for word in text.split(" "):
        cand = (cur + " " + word).strip()
        if d.textlength(cand, font=f) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if d.textlength(cur + ch, font=f) > width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
    if cur:
        lines.append(cur)
    return lines


ROLE = {"home": ("홈팀", "홈", "HOME"), "away": ("원정팀", "원정", "AWAY")}


def team_text(sec, name, role=None):
    for k, v in sec.items():
        if re.sub(r"\s", "", k).startswith(re.sub(r"\s", "", name)):
            return " ".join(v)
    for k, v in sec.items():  # 소제목이 팀 이름 대신 '홈팀'·'원정팀'인 글 (2026-10-19 1065번 카드 칸이 빔)
        if role and re.sub(r"\s", "", k).split(":")[0].upper() in ROLE[role]:
            return " ".join(v)
    return ""


def make(post, idx, league, out):
    m = post["matches"][idx - 1]
    sec = sections(blocks(post["body"]).get(f"경기{idx}", post["body"]))
    texts = [team_text(sec, m["home"], "home"), team_text(sec, m["away"], "away")]

    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f_body = font(28, FONT_MEDIUM)
    col_w = (W - PAD * 2 - 24) // 2
    lines = [wrap(tmp, t, f_body, col_w - 56) for t in texts]
    lh = 44
    head_h = 290
    col_h = 104 + max(len(x) for x in lines) * lh + 28
    H = head_h + col_h + PAD

    canvas = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(canvas)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    d.rounded_rectangle((12, 12, W - 13, H - 13), radius=24, outline=FRAME, width=4)

    # 배지는 여기서 넣지 않음 (공개 쪽 코드에는 사이트 표시 없음, 등록 쪽에서 얹음)
    d.text((W // 2, 57), league, font=font(30, FONT_MEDIUM), fill=MUTED, anchor="mm")

    # 머리: 엠블럼 · 팀명 · 전적 · VS
    alias = load_alias()
    for name, en, rec, cx, color in ((m["home"], m.get("home_en"), m.get("home_record", ""), 300, (40, 110, 200)),
                                     (m["away"], m.get("away_en"), m.get("away_record", ""), 900, (190, 30, 50))):
        try:
            logo = get_logo(name, en or alias[name])
        except Exception:
            logo = placeholder(name, color)
        logo = fit(logo, 96)  # 줄이기만 함 (확대 금지)
        canvas.alpha_composite(logo, (cx - logo.width // 2, 140 - logo.height // 2))
        d = ImageDraw.Draw(canvas)
        d.text((cx, 214), name, font=font(56), fill=WHITE, anchor="mm")
        if rec:
            d.text((cx, 262), rec, font=font(32), fill=GOLD, anchor="mm")
    d.ellipse((W // 2 - 58, 178 - 58, W // 2 + 58, 178 + 58), fill=(44, 33, 86), outline=FRAME, width=4)
    d.text((W // 2, 178), "VS", font=font(54), fill=FRAME, anchor="mm")
    for sx in (W // 2 - 110, W // 2 + 110):
        d.text((sx, 178), "★", font=font(26), fill=FRAME, anchor="mm")

    # HOME / AWAY 칸 (가운데 정렬 문단)
    y0 = head_h
    for i, (label, name, ls) in enumerate((("HOME", m["home"], lines[0]), ("AWAY", m["away"], lines[1]))):
        x0 = PAD + i * (col_w + 24)
        x1 = x0 + col_w
        cx = (x0 + x1) / 2
        d.rounded_rectangle((x0, y0, x1, y0 + col_h), radius=18, fill=PANEL, outline=(90, 74, 140), width=2)
        chip = f"{label} : {name}"
        cw = d.textlength(chip, font=font(28)) + 60
        d.rounded_rectangle((cx - cw / 2, y0 + 22, cx + cw / 2, y0 + 72), radius=14, fill=CHIP)
        d.text((cx, y0 + 47), chip, font=font(28), fill=CHIP_TEXT, anchor="mm")
        for j, ln in enumerate(ls):
            d.text((cx, y0 + 104 + j * lh + lh / 2), ln, font=f_body, fill=TEXT, anchor="mm")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.convert("RGB").save(out, "PNG")
    print(f"분석 카드 저장: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", required=True, help="글 폴더 (post.json)")
    ap.add_argument("--match", type=int, default=1)
    ap.add_argument("--league", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    folder = a.post if os.path.isabs(a.post) else os.path.join(HERE, a.post)
    with open(os.path.join(folder, "post.json"), encoding="utf-8") as f:
        post = json.load(f)
    make(post, a.match, a.league or post.get("league_label", ""), a.out)


if __name__ == "__main__":
    main()
