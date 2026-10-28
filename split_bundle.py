#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
split_bundle.py

3경기 이상 묶인 분석 글을 나눈다 (2026-10-17 ): 주요 리그는 경기별 글로, 잡리그는 리그별 묶음 글(최대 6경기)로.
Claude 는 원문 줄 번호로 경기별 범위만 정하고, 글자는 원문 줄을 그대로 잘라 쓴다 (데이터 원문 그대로).
나누기 전에 네이버 스포츠로 경기를 찾아, 이미 시작한 경기·이미 올린 경기는 미리 뺀다 (사용량 아끼기).

결과: 글/<원글번호>-<n>/article.json  (출력 "+ [<원글번호>-<n>] 홈 vs 원정" 줄을 run_pick.py 가 읽음)

사용법:
    python3 split_bundle.py 글/ls2544309 --sport football --posted posted_keys.json
"""
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROMPT = """\
아래는 스포츠 분석 글 원문이다. 줄마다 번호(L0, L1 …)가 붙어 있다. 여러 경기 분석이 이어져 있다.
경기마다 그 경기 분석이 들어 있는 줄 범위를 찾아라. 글자를 고치거나 요약하지 말고 줄 번호만 답한다.

- 한 경기 범위에는 그 경기의 팀 이름·전적·분석 문장·추천 픽 줄이 모두 들어가야 한다.
- 여러 경기에 공통인 머리말(리그 이름·날짜 등)은 "common" 에 줄 번호 목록으로.
- home/away 는 원문에 쓰인 팀 이름 글자 그대로 (원문이 홈/원정을 안 밝히면 먼저 나온 팀이 home).
- pick 은 그 경기 추천 픽을 원문 글자 그대로.
- 광고·문의·이벤트 줄은 어느 범위에도 넣지 않는다.

출력은 JSON 하나만:
{{"common": [줄번호…], "matches": [{{"home": "...", "away": "...", "start": 시작줄번호, "end": 끝줄번호, "pick": "..."}}]}}

[원문]
{numbered}
"""

from big_league import is_big_naver, star_game

GROUP_MAX = 6  # 잡리그 묶음 글 한 개에 최대 경기 수
# 주요 리그 = 경기별로 따로 올림, 그 밖(잡리그)은 리그별 묶음 글 (2026-10-17 )
MAJOR_FOOTBALL_IDS = {"epl", "england2", "primera", "bundesliga", "seria", "ligue1", "eredivisie", "portugal",
                      "champs", "europa", "uel", "uecl", "conference", "kleague", "mls"}  # mls: 2026-10-18 (인기 있어 경기별 글)
MAJOR_FOOTBALL_NAMES = {"프리미어리그", "잉글랜드 챔피언십", "라리가", "분데스리가", "세리에 A", "리그 1", "에레디비시",
                        "프리메이라리가", "챔피언스리그", "유로파리그", "컨퍼런스리그", "UEFA 챔피언스리그", "UEFA 유로파리그",
                        "UEFA 컨퍼런스리그", "K리그1", "메이저리그사커"}


def is_major(g, sport):
    """주요 리그인지. 축구는 유럽 주요 리그·UEFA 대회·잉글랜드 챔피언십·K리그1, 다른 종목은 네이버 정규 리그(KBO·MLB·NPB·KBL·NBA·V리그)."""
    if not g:
        return False  # 네이버에도 없는 리그 = 잡리그
    cid, name = g.get("categoryId") or "", g.get("categoryName") or ""
    if sport == "football":
        return cid in MAJOR_FOOTBALL_IDS or name in MAJOR_FOOTBALL_NAMES
    return "etc" not in cid and "기타" not in name


def norm(s):
    return re.sub(r"\s+", "", s or "")


# 네이버 조회가 실패해도(응답 지연 등) 글 제목에 주요 리그 이름이 있으면 주요 리그로 봄 (2026-10-28: NBA 경기가 잡리그 묶음 '[NBA 4경기]'로 올라감)
MAJOR_TITLE = re.compile(r"(?<![A-Za-z])(NBA|KBL|MLB|KBO|NPB)(?![A-Za-z])|V리그|KOVO")


def major_by_title(title, sport):
    return sport != "football" and bool(MAJOR_TITLE.search(title or ""))


def src_league(seg):
    """네이버에 없는 경기: 원문 경기 머리줄의 리그명 (예: 'AFC CUP 10월 23일(금) 22시25분' → 'AFC CUP').
    2026-10-23 '기타' 한 묶음으로 A리그·AFC컵이 섞여 '[A리그 3경기]' 제목으로 올라감 → 원문 리그명별로 묶음."""
    m = re.search(r"^\s*([가-힣A-Za-z][^\n]{1,18}?)\s+(?:20\d\d\.\d{1,2}\.\d{1,2}|\d{1,2}월\s*\d{1,2}일)", "\n".join(seg), re.M)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def main():
    folder = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    sport = sys.argv[sys.argv.index("--sport") + 1] if "--sport" in sys.argv else "football"
    posted = set()
    if "--posted" in sys.argv:
        p = sys.argv[sys.argv.index("--posted") + 1]
        if os.path.exists(p):
            posted = set(json.load(open(p, encoding="utf-8")))
    exclude = []  # 지난번 경기 시간을 어디서도 못 찾은 경기 (2026-10-20: 이 경기만 빼고 나머지는 올림)
    if "--exclude" in sys.argv:
        p = sys.argv[sys.argv.index("--exclude") + 1]
        if os.path.exists(p):
            exclude = [[norm(t) for t in x.split(" vs ", 1)] for x in json.load(open(p, encoding="utf-8")) if " vs " in x]
    aid = os.path.basename(folder.rstrip("/"))
    base = aid  # 원문 폴더
    if "--suffix" in sys.argv:  # 다시 나눌 때는 새 번호 (이미 올린 이전 번호와 안 겹치게, 2026-10-18)
        aid = f"{aid}-{sys.argv[sys.argv.index('--suffix') + 1]}"
    art = json.load(open(os.path.join(folder, "article.json"), encoding="utf-8"))
    lines = [ln for ln in art["text"].replace("​", "").split("\n")]
    numbered = "\n".join(f"L{i}: {ln}" for i, ln in enumerate(lines))

    from rewrite import ask_claude
    res = ask_claude(PROMPT.format(numbered=numbered))
    common = [lines[i] for i in res.get("common", []) if 0 <= i < len(lines)]

    import h2h
    h2h.SPORT = sport
    try:
        at = datetime.datetime.strptime(art.get("date", ""), "%Y-%m-%d %H:%M").replace(tzinfo=h2h.KST)
    except ValueError:
        at = None
    now = datetime.datetime.now(h2h.KST)
    kept = 0
    groups = {}  # 잡리그 경기 → 리그별로 묶어서 글 하나 (2026-10-17 )
    for k, m in enumerate(res.get("matches", []), 1):
        s, e = int(m.get("start", -1)), int(m.get("end", -1))
        if not (0 <= s <= e < len(lines)):
            print(f"  [나누기 실패] {k}번째 경기 줄 범위가 이상함 ({s}~{e})")
            continue
        seg = lines[s:e + 1]
        seg_n = norm("\n".join(seg))
        if norm(m.get("pick")) not in seg_n or not (norm(m.get("home")) in seg_n or norm(m.get("away")) in seg_n):
            print(f"  [나누기 실패] {m.get('home')} vs {m.get('away')}: 범위 안에 팀 이름·추천이 원문 그대로 없음")
            continue
        label = f"{m['home']} vs {m['away']}"
        hn, an = norm(m["home"]), norm(m["away"])
        if any((hn in eh or eh in hn) and (an in ea or ea in an) for eh, ea in exclude if eh and ea):
            print(f"  [건너뜀] {label}: 경기 시간을 확인하지 못한 경기")
            continue
        g = None
        try:
            g = h2h.naver_find({"home": m["home"], "away": m["away"]}, at)
        except Exception:
            pass
        if g:
            ko = datetime.datetime.fromisoformat(g["gameDateTime"]).replace(tzinfo=h2h.KST)
            if ko <= now:
                print(f"  [건너뜀] {label}: 이미 시작한 경기 ({ko:%m/%d %H:%M})")
                continue
            if any(f"naver:{x}" in posted for x in [g["gameId"]] + h2h.naver_replaced(g)):
                print(f"  [건너뜀] {label}: 이미 올린 경기")
                continue
        if sport == "football" and not (is_big_naver(g) or star_game(m.get("home"), m.get("away"))):
            print(f"  [건너뜀] {label}: 유럽 빅리그·손흥민·메시 경기가 아님 ({(g or {}).get('categoryName') or '리그 모름'})")
            continue  # 2026-10-23 축구는 유럽 빅리그 + 손흥민·메시 경기만
        if not is_major(g, sport) and not (not g and major_by_title(art.get("title", ""), sport)):  # 잡리그 → 리그별 묶음
            league = (g or {}).get("categoryName") or src_league(seg) or src_league(lines[max(0, s - 2):s]) or "기타"
            groups.setdefault(league, []).append((label, seg))
            continue
        sub = f"{aid}-{k}"
        sf = os.path.join(HERE, "글", sub)
        os.makedirs(sf, exist_ok=True)
        sub_art = dict(art, article_id=sub, parent=base, title=f"{label} ({art.get('title', '')})",
                       text="\n".join(common + seg), images=[])
        with open(os.path.join(sf, "article.json"), "w", encoding="utf-8") as f:
            json.dump(sub_art, f, ensure_ascii=False, indent=2)
        kept += 1
        print(f"      + [{sub}] {label}" + (f" ({g['gameDateTime'][5:16]})" if g else ""))
    # 잡리그: 리그별 묶음 글 (한 글에 최대 6경기)
    gi = 0
    for league, items in groups.items():
        for c in range(0, len(items), GROUP_MAX):
            chunk = items[c:c + GROUP_MAX]
            gi += 1
            sub = f"{aid}-g{gi}"
            sf = os.path.join(HERE, "글", sub)
            os.makedirs(sf, exist_ok=True)
            text = "\n".join(common) + "\n" + "\n\n".join("\n".join(seg) for _, seg in chunk)
            sub_art = dict(art, article_id=sub, parent=base, group=True, group_league=league,
                           title=f"{league} {len(chunk)}경기 ({art.get('title', '')})", text=text.strip(), images=[])
            with open(os.path.join(sf, "article.json"), "w", encoding="utf-8") as f:
                json.dump(sub_art, f, ensure_ascii=False, indent=2)
            kept += 1
            print(f"      + [{sub}] {league} 묶음 {len(chunk)}경기: " + ", ".join(lb for lb, _ in chunk))
    print(f"  묶음 {len(res.get('matches', []))}경기 → 올릴 글 {kept}개")

if __name__ == "__main__":
    main()
