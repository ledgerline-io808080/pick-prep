#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
축구는 유럽 빅리그만 올림 (2026-10-23 GitHub 실행 시간 줄이기)
- 5대 리그(프리미어리그·라리가·분데스리가·세리에A·리그앙) + UEFA 챔피언스리그·유로파리그·컨퍼런스리그
- 추가(2026-10-23 ): K리그1·에레디비시·포르투갈(프리메이라리가)
- 추가(2026-11-04 제프: 새 사이트는 글이 많아야 함): 아시아 챔피언스리그(엘리트)·챔피언스리그2
- 예외: 손흥민(LAFC)·메시(인터 마이애미) 경기는 리그와 상관없이 올림
- 농구·야구·배구는 영향 없음
"""
import re

BIG_IDS = {"epl", "primera", "bundesliga", "seria", "ligue1", "champs", "europa", "uel", "uecl", "conference",
           "kleague", "eredivisie", "portugal", "mls"}
BIG_NAMES = {"프리미어리그", "라리가", "분데스리가", "세리에 A", "세리에A", "리그 1", "리그1", "리그앙",
             "챔피언스리그", "유로파리그", "컨퍼런스리그", "UEFA 챔피언스리그", "UEFA 유로파리그", "UEFA 컨퍼런스리그",
             "K리그1", "에레디비시", "프리메이라리가", "메이저리그사커", "MLS", "잉글랜드 챔피언십", "챔피언십"}
BIG_EN = {("England", "Premier League"), ("Spain", "La Liga"), ("Germany", "Bundesliga"), ("Italy", "Serie A"),
          ("France", "Ligue 1"), ("World", "UEFA Champions League"), ("World", "UEFA Europa League"),
          ("World", "UEFA Europa Conference League"), ("World", "UEFA Conference League"),
          ("South-Korea", "K League 1"), ("Netherlands", "Eredivisie"), ("Portugal", "Primeira Liga"),
          ("USA", "Major League Soccer"), ("England", "Championship")}  # 2026-11-19 제프: MLS도 올림
# ESPN 리그 이름 (네이버가 안 될 때 ESPN 으로 경기를 찾은 경우, 2026-10-31)
ESPN_BIG = {"English Premier League", "Laliga", "German Bundesliga", "Italian Serie A", "Ligue 1",
            "Portuguese Primeira Liga", "Dutch Eredivisie", "Korean K League 1", "Major League Soccer", "MLS"}
UEFA_EN = {"UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League", "UEFA Conference League"}
# 손흥민·메시 소속팀 (이적하면 여기만 고침)
STAR_TEAMS = {"lafc", "la fc", "로스앤젤레스fc", "로스엔젤레스fc", "losangelesfc",
              "인터마이애미", "인터마이애미cf", "intermiami", "intermiamicf"}


# 2026-11-15 제프: 축구 경기가 없는 휴식기엔 유럽·아프리카 대표팀 경기도 올림 — UEFA 네이션스리그 + 아프리카 네이션스컵(예선 포함).
# 국제 친선경기·오세아니아는 안 올림(북중미 대회는 2026-11-15 제프 요청으로 올림). 라이브스코어 제목·원문 리그 머리줄에 '네이션스컵'·'네이션스리그'가 있어야 하고,
CONCACAF_WORDS = ["그레나다", "세인트", "버뮤다", "푸에르토리코", "도미니카", "과테말라", "캐나다", "퀴라소", "파나마", "아이티",
                  "미국", "자메이카", "멕시코", "온두라스", "코스타리카", "엘살바도르", "수리남", "트리니다드", "쿠바", "가이아나",
                  "니카라과", "벨리즈", "앤티가", "바베이도스", "케이맨", "몬트세랫", "아루바", "바하마", "앵귈라", "버진"]


def intl_ok(text, home="", away=""):
    """제목·리그 머리줄(text)이 유럽 네이션스리그(UEFA) 또는 아프리카 네이션스컵이면 True"""
    t = text or ""
    # 2026-11-17 제프: 한국 대표팀 경기는 친선경기도 올림(다른 나라 친선경기는 안 올림)
    korea = any(("대한민국" in x or x in ("한국",)) for x in (home or "", away or ""))
    if "친선" in t and korea and not re.search(r"U-?\d{2}|청소년|유스|여자", t):
        return True
    if "친선" in t or "OFC" in t or "오세아니아" in t or "골드컵" in t \
            or re.search(r"U-?\d{2}|청소년|유스", t):  # 청소년 대표팀 제외
        return False
    if ("챔피언쉽" in t or "챔피언십" in t) and not re.search(r"아시아|AFC|UEFA|K리그|클럽|월드|여자|U-?\d{2}", t):
        return True  # 2026-11-22 제프: 잉글랜드 챔피언십도 올림
    if "MLS" in t.upper() or "메이저리그사커" in t:  # 2026-11-19 제프: MLS(플레이오프 포함)도 올림
        return True
    if "네이션스컵" in t or "아프리카" in t or "AFCON" in t.upper():
        return True
    # 2026-11-15 제프: 빅리그 경기가 없을 때를 위해 월드컵·유로·아시안컵 등 대표팀 예선도 올림(친선경기만 제외)
    if "예선" in t or "월드컵" in t or "유로 20" in t or "유로2" in t:
        return True
    if "네이션스리그" in t:
        return True  # 2026-11-15 제프: 북중미 네이션스리그도 올림
    return False


def is_acl(s):
    """AFC(아시아) 챔피언스리그 계열 이름인지 (한글·영문·네이버 이름 모두, 2026-11-04)"""
    s = s or ""
    return "아시아 챔피언스리그" in s or "AFC 챔피언스리그" in s or "AFC Champions" in s


def _n(s):
    return re.sub(r"[\s.\-·]", "", (s or "")).lower()


def star_game(*teams):
    """손흥민·메시 소속팀 경기인지 (팀 이름 중 하나라도)"""
    return any(_n(t) in STAR_TEAMS for t in teams if t)


def is_big_naver(g):
    """네이버 경기 정보(categoryId·categoryName)로 빅리그인지"""
    if not g:
        return False
    return ((g.get("categoryId") or "") in BIG_IDS or (g.get("categoryName") or "") in BIG_NAMES
            or is_acl(g.get("categoryName")))


def is_uefa_title(t):
    """제목의 리그명이 UEFA 유로파·컨퍼런스·챔피언스면 True (2026-11-05 제프: 유로파 경기 누락 금지 — 이름이 낯선 팀이라
    경기 조회가 안 돼 '빅리그 아님'으로 빠지던 7경기)"""
    t = t or ""
    return any(w in t for w in ("유로파", "컨퍼런스")) or ("챔피언스" in t and "아시아" not in t and "AFC" not in t)


def is_big_match(mk):
    """h2h.py 가 만든 match_N.json 으로 빅리그인지 (네이버 한글 리그명 또는 API-Football 나라+리그)"""
    if not mk:
        return False
    if (mk.get("league_ko") or "") in BIG_NAMES or is_acl(mk.get("league_ko")) or is_acl(mk.get("league")):
        return True
    league, country = mk.get("league") or "", mk.get("country")
    if mk.get("source") == "ESPN" and league in ESPN_BIG:
        return True
    if league in UEFA_EN:
        return True  # UEFA 대회는 나라 정보가 비어 있어도 (API-Football 'None')
    if (country, league) in BIG_EN:
        return True
    # 나라 정보가 없을 때: 이름이 겹치지 않는 리그만 인정 (Premier League 는 러시아·우크라이나 등과 겹쳐서 제외)
    return not country and league in {"La Liga", "Bundesliga", "Serie A", "Ligue 1", "K League 1", "Eredivisie", "Primeira Liga"}


# 제목만 보고 읽기 전에 거르기 (2026-10-25 이미지 읽는 시간 줄이기, K리그1이 섞인 묶음은 놓쳐도 괜찮음)
# 제목에 아래 비빅리그 이름이 있고 빅리그 이름이 하나도 없으면 읽지 않음. '해외축구'처럼 리그 이름이 없는 제목은 그대로 읽음.
TITLE_OUT = ["J리그", "J1", "J2", "J /", "J/", "A리그", "호주", "중국", "SL", "MLS", "메이저리그사커", "K리그", "K /", "K/",
             "사우디", "일본", "아시안", "코파", "남미", "브라질", "아르헨", "멕시코", "터키", "러시아", "스코틀랜드"]
TITLE_BIG = ["프리미어", "EPL", "라리가", "분데스", "세리에", "리그앙", "리그 앙", "에레디", "프리메이라",
             "포르투갈", "챔피언스", "챔스", "AFC", "MLS", "메이저리그사커", "챔피언쉽", "챔피언십", "UCL", "유로파", "UEL", "컨퍼런스", "UECL", "해외축구", "유럽", "손흥민", "LAFC", "메시", "마이애미"]
TITLE_BIG_RE = re.compile(r"(?<![A-Za-z])리그\s?1(?!\d)")  # '프랑스 리그1' 만 ('K리그 19경기'의 '리그 1'은 아님)


def skip_by_title(title):
    """축구 분석글 제목이 비빅리그뿐이면 True (읽지 않음). K리그는 K리그1도 함께 거름."""
    t = title or ""
    return any(w in t for w in TITLE_OUT) and not (any(w in t for w in TITLE_BIG) or TITLE_BIG_RE.search(t))
