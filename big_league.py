#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
축구는 유럽 빅리그만 올림 (2026-10-23 GitHub 실행 시간 줄이기)
- 5대 리그(프리미어리그·라리가·분데스리가·세리에A·리그앙) + UEFA 챔피언스리그·유로파리그·컨퍼런스리그
- 추가(2026-10-23 ): K리그1·에레디비시·포르투갈(프리메이라리가)
- 예외: 손흥민(LAFC)·메시(인터 마이애미) 경기는 리그와 상관없이 올림
- 농구·야구·배구는 영향 없음
"""
import re

BIG_IDS = {"epl", "primera", "bundesliga", "seria", "ligue1", "champs", "europa", "uel", "uecl", "conference",
           "kleague", "eredivisie", "portugal"}
BIG_NAMES = {"프리미어리그", "라리가", "분데스리가", "세리에 A", "세리에A", "리그 1", "리그1", "리그앙",
             "챔피언스리그", "유로파리그", "컨퍼런스리그", "UEFA 챔피언스리그", "UEFA 유로파리그", "UEFA 컨퍼런스리그",
             "K리그1", "에레디비시", "프리메이라리가"}
BIG_EN = {("England", "Premier League"), ("Spain", "La Liga"), ("Germany", "Bundesliga"), ("Italy", "Serie A"),
          ("France", "Ligue 1"), ("World", "UEFA Champions League"), ("World", "UEFA Europa League"),
          ("World", "UEFA Europa Conference League"), ("World", "UEFA Conference League"),
          ("South-Korea", "K League 1"), ("Netherlands", "Eredivisie"), ("Portugal", "Primeira Liga")}
UEFA_EN = {"UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League", "UEFA Conference League"}
# 손흥민·메시 소속팀 (이적하면 여기만 고침)
STAR_TEAMS = {"lafc", "la fc", "로스앤젤레스fc", "로스엔젤레스fc", "losangelesfc",
              "인터마이애미", "인터마이애미cf", "intermiami", "intermiamicf"}


def _n(s):
    return re.sub(r"[\s.\-·]", "", (s or "")).lower()


def star_game(*teams):
    """손흥민·메시 소속팀 경기인지 (팀 이름 중 하나라도)"""
    return any(_n(t) in STAR_TEAMS for t in teams if t)


def is_big_naver(g):
    """네이버 경기 정보(categoryId·categoryName)로 빅리그인지"""
    if not g:
        return False
    return (g.get("categoryId") or "") in BIG_IDS or (g.get("categoryName") or "") in BIG_NAMES


def is_big_match(mk):
    """h2h.py 가 만든 match_N.json 으로 빅리그인지 (네이버 한글 리그명 또는 API-Football 나라+리그)"""
    if not mk:
        return False
    if (mk.get("league_ko") or "") in BIG_NAMES:
        return True
    league, country = mk.get("league") or "", mk.get("country")
    if league in UEFA_EN:
        return True  # UEFA 대회는 나라 정보가 비어 있어도 (API-Football 'None')
    if (country, league) in BIG_EN:
        return True
    # 나라 정보가 없을 때: 이름이 겹치지 않는 리그만 인정 (Premier League 는 러시아·우크라이나 등과 겹쳐서 제외)
    return not country and league in {"La Liga", "Bundesliga", "Serie A", "Ligue 1", "K League 1", "Eredivisie", "Primeira Liga"}


# 제목만 보고 읽기 전에 거르기 (2026-10-25 이미지 읽는 시간 줄이기, K리그1이 섞인 묶음은 놓쳐도 괜찮음)
# 제목에 아래 비빅리그 이름이 있고 빅리그 이름이 하나도 없으면 읽지 않음. '해외축구'처럼 리그 이름이 없는 제목은 그대로 읽음.
TITLE_OUT = ["J리그", "J1", "J2", "J /", "J/", "A리그", "호주", "중국", "SL", "MLS", "메이저리그사커", "K리그", "K /", "K/",
             "사우디", "일본", "AFC", "아시안", "코파", "남미", "브라질", "아르헨", "멕시코", "터키", "러시아", "스코틀랜드"]
TITLE_BIG = ["프리미어", "EPL", "라리가", "분데스", "세리에", "리그앙", "리그 앙", "에레디", "프리메이라",
             "포르투갈", "챔피언스", "챔스", "UCL", "유로파", "UEL", "컨퍼런스", "UECL", "해외축구", "유럽", "손흥민", "LAFC", "메시", "마이애미"]
TITLE_BIG_RE = re.compile(r"(?<![A-Za-z])리그\s?1(?!\d)")  # '프랑스 리그1' 만 ('K리그 19경기'의 '리그 1'은 아님)


def skip_by_title(title):
    """축구 분석글 제목이 비빅리그뿐이면 True (읽지 않음). K리그는 K리그1도 함께 거름."""
    t = title or ""
    return any(w in t for w in TITLE_OUT) and not (any(w in t for w in TITLE_BIG) or TITLE_BIG_RE.search(t))
