#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글 맨 아래 '추천 픽' 막대 이미지(1200x200 PNG) — 큰 글씨 + 황소TV 빨강 (2026-11-25 제프: 마지막 추천 줄이 눈에 안 띔).
새 사이트는 글 안의 색·크기를 지우므로 이미지로 만든다. 본문 끝 글자 줄(닉네임 ▶ 픽: …)은 그대로 둔다.
사용: python3 make_pick_bar.py --pick "블랙번 승 @2.10" --out 글/123/pick_bar.png
"""
import argparse
import os

from PIL import Image, ImageDraw

import make_banner as mb

W, H = 1200, 200
RED = (196, 40, 28)


def make(pick, out):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # 바깥은 투명 → 주간·야간 어느 화면에서도 어울림 (2026-11-25)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((30, 26, W - 30, H - 26), radius=44, fill=RED + (255,))
    # 왼쪽 '추천 픽' 칩
    d.rounded_rectangle((52, 46, 262, H - 46), radius=32, fill=(255, 255, 255, 255))
    d.text((157, H // 2), "추천 픽", font=mb.font(40), fill=RED, anchor="mm")
    # 큰 추천 글씨 (길면 줄여 맞춤)
    area_l, area_r = 292, W - 56
    f = mb.fit_font(d, pick, 64, area_r - area_l, mb.FONT_BOLD, min_size=30)
    d.text(((area_l + area_r) // 2, H // 2 + 2), pick, font=f, fill=(255, 255, 255), anchor="mm")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out, "PNG")
    print(f"추천 막대 저장: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    make(a.pick, a.out)
