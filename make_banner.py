#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_banner.py

팀 로고 VS 배너 이미지(1200x630 PNG)를 만든다. 글 맨 위에 붙이는 용도.
로고는 TheSportsDB(무료)에서 영어 팀명으로 찾아 로고/ 폴더에 한 번 저장해 두고 재사용한다.

사용법:
    python3 make_banner.py \
        --home "시드니FC" --home-en "Sydney FC" \
        --away "웨스턴시드니W" --away-en "Western Sydney Wanderers" \
        --league "A리그 개막전" --pick "시드니FC 승 @2.02" \
        --out 글/312942/banner.png

    --home-en/--away-en 은 로고 검색용 영어 팀명. 한 번 찾으면 team_alias.json에
    한글 팀명 → 영어 팀명이 저장돼서, 다음부터는 한글 팀명만 줘도 된다.
    로고를 못 찾으면 팀명 앞글자로 만든 동그라미를 대신 넣는다.
"""
import argparse
import io
import json
import hashlib
import os
import re
import unicodedata
import urllib.parse

import requests

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(HERE, "로고")
ALIAS_PATH = os.path.join(HERE, "team_alias.json")
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT_BOLD, FONT_MEDIUM = 6, 2  # ttc 안의 굵기 번호
SEARCH_URL = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={}"

W, H = 1200, 630
BG_TOP, BG_BOTTOM = (14, 22, 40), (6, 10, 20)
WHITE = (245, 247, 250)
MUTED = (150, 162, 185)
ACCENT = (52, 211, 153)


def linux_font(weight_name):
    """서버(리눅스)의 Noto CJK 글꼴 파일을 찾는다. Medium이 없으면 Regular."""
    import glob
    for name in ([weight_name, "Regular"] if weight_name != "Bold" else ["Bold"]):
        hits = sorted(glob.glob(f"/usr/share/fonts/**/NotoSansCJK*-{name}.tt[co]", recursive=True))
        if hits:
            return hits[0]
    raise RuntimeError("한글 글꼴(Noto CJK)을 찾지 못했습니다.")


def font(size, weight=FONT_BOLD):
    w_ = weight
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size, index=w_)
    path = linux_font("Bold" if w_ == FONT_BOLD else "Medium")
    return ImageFont.truetype(path, size, index=1 if path.endswith(".ttc") else 0)  # ttc 1번 = 한국어(KR)


def load_alias():
    if os.path.exists(ALIAS_PATH):
        with open(ALIAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_alias(alias):
    with open(ALIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(alias, f, ensure_ascii=False, indent=2)


PLACEHOLDER_HASH = "3af186b6bd671981c6af4e8bcdc8cb17"  # 'image not available' 회색 카메라 그림 (2026-11-07 제프: 팀 로고는 정확히 확인하고 올림)
_GENERIC = {"fc", "sc", "cf", "afc", "ac", "as", "ssc", "us", "fk", "sk", "club", "football", "united", "city", "real", "sporting",
            "de", "la", "el", "the", "town", "athletic", "atletico", "stade", "borussia", "sv", "tsg", "rb", "vfl", "vfb", "1"}


def _tokens(name):
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()).split()
            if t not in _GENERIC and len(t) > 2}


def _img_hash(img):
    return hashlib.md5(img.convert("RGBA").tobytes()).hexdigest()


def _same_team_name(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta & tb) or re.sub(r"\W", "", a.lower()) == re.sub(r"\W", "", b.lower())


def _logo_ok(name_en, img):
    """회색 카메라 '이미지 없음' 그림이거나, 이미 저장된 다른 팀 로고와 똑같은 그림이면 안 씀 (엉뚱한 팀 로고 방지)."""
    h = _img_hash(img)
    if h == PLACEHOLDER_HASH:
        return False
    for f in os.listdir(LOGO_DIR):
        if not f.endswith(".png") or f[:-4] == name_en:
            continue
        try:
            other = Image.open(os.path.join(LOGO_DIR, f))
        except Exception:
            continue
        if _img_hash(other) == h and not _same_team_name(name_en, f[:-4]):
            return False
    return True


def get_logo(name_ko, name_en):
    """로고 PNG(RGBA)를 돌려준다. 로고/<영어팀명>.png 에 저장해 두고 재사용.
    검색으로 받을 때는 이름이 거의 같은 팀만 받고(첫 번째 결과 아무거나 X), 못 믿으면 오류를 내 글자 로고로 대체."""
    os.makedirs(LOGO_DIR, exist_ok=True)
    path = os.path.join(LOGO_DIR, f"{name_en}.png")
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        if _img_hash(img) == PLACEHOLDER_HASH:
            raise RuntimeError(f"로고가 '이미지 없음' 그림: {name_en}")
        return img
    url = SEARCH_URL.format(urllib.parse.quote(name_en))
    teams = requests.get(url, timeout=20).json().get("teams") or []
    soccer = [t for t in teams if t.get("strSport") == "Soccer"] or teams
    want = re.sub(r"\W", "", name_en.lower())
    exact = [t for t in soccer if re.sub(r"\W", "", (t.get("strTeam") or "").lower()) in (want, want + "fc", "fc" + want)]
    if not exact:
        raise RuntimeError(f"로고 검색 결과에 같은 이름의 팀이 없음: {name_en} ({[t.get('strTeam') for t in soccer[:3]]})")
    badge = exact[0].get("strBadge") or exact[0].get("strTeamBadge")
    img = Image.open(io.BytesIO(requests.get(badge, timeout=20).content)).convert("RGBA")
    if not _logo_ok(name_en, img):
        raise RuntimeError(f"로고가 '이미지 없음'이거나 다른 팀 로고와 같은 그림: {name_en}")
    img.save(path)
    print(f"  로고 저장: {name_ko} → {path}")
    return img


def placeholder(name_ko, color):
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((10, 10, 390, 390), fill=color)
    d.text((200, 200), name_ko[:2], font=font(150), fill=WHITE, anchor="mm")
    return img


def fit(img, box):
    img = img.copy()
    img.thumbnail((box, box), Image.LANCZOS)
    return img


def paste_logo(canvas, logo, cx, cy, box):
    logo = fit(logo, box)
    # 어두운 배경에서도 로고가 보이도록 은은한 빛 번짐
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    g = Image.new("RGBA", logo.size, (255, 255, 255, 0))
    g.putalpha(logo.getchannel("A").point(lambda a: int(a * 0.35)))
    glow.paste(g, (cx - logo.width // 2, cy - logo.height // 2), g)
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(logo, (cx - logo.width // 2, cy - logo.height // 2))


def make(home, away, league, pick, out, home_en=None, away_en=None):
    alias = load_alias()
    if home_en:
        alias[home] = home_en
    if away_en:
        alias[away] = away_en
    save_alias(alias)

    logos = []
    for name, color in ((home, (40, 110, 200)), (away, (190, 30, 50))):
        try:
            if name not in alias:
                raise RuntimeError("영어 팀명 없음")
            logos.append(get_logo(name, alias[name]))
        except Exception as e:
            print(f"  [로고 없음] {name}: {e} → 기본 동그라미로 대체")
            logos.append(placeholder(name, color))

    canvas = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(canvas)
    for y in range(H):  # 위→아래 그라데이션
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))

    # 배지는 여기서 넣지 않음 (공개 쪽 코드에는 사이트 표시 없음, 등록 쪽에서 얹음)

    # 상단 리그 라벨
    d.text((W // 2, 62), league, font=font(34, FONT_MEDIUM), fill=MUTED, anchor="mm")

    # 로고 + 팀명
    lx, rx, ly = 300, 900, 270
    paste_logo(canvas, logos[0], lx, ly, 260)
    paste_logo(canvas, logos[1], rx, ly, 260)
    d = ImageDraw.Draw(canvas)
    d.text((lx, 448), home, font=font(44), fill=WHITE, anchor="mm")
    d.text((rx, 448), away, font=font(44), fill=WHITE, anchor="mm")
    d.text((W // 2, ly), "VS", font=font(84), fill=WHITE, anchor="mm")

    # 하단 추천 바
    bar_h = 92
    d.rectangle((0, H - bar_h, W, H), fill=(10, 16, 30))
    d.line([(0, H - bar_h), (W, H - bar_h)], fill=ACCENT, width=3)
    label, value = "추천  ", pick
    f_label, f_value = font(36, FONT_MEDIUM), font(40)
    lw = d.textlength(label, font=f_label)
    vw = d.textlength(value, font=f_value)
    x0 = (W - lw - vw) / 2
    cy = H - bar_h / 2
    d.text((x0, cy), label, font=f_label, fill=MUTED, anchor="lm")
    d.text((x0 + lw, cy), value, font=f_value, fill=ACCENT, anchor="lm")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.convert("RGB").save(out, "PNG")
    print(f"배너 저장: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True, help="홈팀 한글명")
    ap.add_argument("--away", required=True, help="원정팀 한글명")
    ap.add_argument("--home-en", help="홈팀 영어명 (로고 검색용)")
    ap.add_argument("--away-en", help="원정팀 영어명 (로고 검색용)")
    ap.add_argument("--league", default="", help="상단 라벨 (예: A리그 개막전)")
    ap.add_argument("--pick", required=True, help="추천 (예: 시드니FC 승 @2.02)")
    ap.add_argument("--out", required=True, help="저장할 PNG 경로")
    args = ap.parse_args()
    make(args.home, args.away, args.league, args.pick, args.out, args.home_en, args.away_en)


if __name__ == "__main__":
    main()
