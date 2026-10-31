#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
h2h.py

API-Football(무료)에서 경기마다 두 팀의 최근 맞대결·다음 경기 시간·팀 로고를 가져온다.
요청 수: 경기당 팀 검색 최대 2회(한 번 찾으면 team_ids.json 에 저장해 재사용) + 맞대결 1회.
로고 이미지는 로고/<영어팀명>.png 로 저장 (make_banner.py, make_stats.py 가 그대로 씀).

사용법:
    python3 h2h.py 글/312942        (post.json 의 matches 사용)
    -> 글/312942/stats_1.json, match_1.json, stats_2.json ... (경기 순서대로)
"""
import datetime
import io
import json
import os
import re
import unicodedata
import sys
import time
from difflib import SequenceMatcher

import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.expanduser("~/.config/jeff/apifootball_key")
IDS_PATH = os.path.join(HERE, "team_ids.json")
LOGO_DIR = os.path.join(HERE, "로고")
KST = datetime.timezone(datetime.timedelta(hours=9))
WEEK = "월화수목금토일"


SPORT = "football"  # --sport 로 바꿈 (football / basketball)
BASES = {"football": "https://v3.football.api-sports.io", "basketball": "https://v1.basketball.api-sports.io"}
DONE_STATUS = {"FT", "AET", "PEN", "AOT"}  # 끝난 경기 (축구 연장·승부차기, 농구 연장 포함)


def api(path, **params):
    key = os.environ.get("APIFOOTBALL_KEY") or open(KEY_PATH).read().strip()  # 서버는 환경변수
    for _ in range(3):
        r = requests.get(BASES[SPORT] + path, headers={"x-apisports-key": key}, params=params, timeout=30).json()
        if "rateLimit" in str(r.get("errors")):  # 무료 등급 분당 요청 한도 → 1분 쉬고 다시
            print("  [API 분당 한도] 1분 쉬고 다시 요청")
            time.sleep(62)
            continue
        break
    if r.get("errors"):
        raise RuntimeError(f"API 오류 {path}: {r['errors']}")
    return r.get("response", [])


def load_ids():
    if os.path.exists(IDS_PATH):
        with open(IDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_logo(name_en, url):
    os.makedirs(LOGO_DIR, exist_ok=True)
    path = os.path.join(LOGO_DIR, f"{name_en}.png")
    if url and not os.path.exists(path):
        try:
            Image.open(io.BytesIO(requests.get(url, timeout=20).content)).convert("RGBA").save(path)
        except Exception as e:
            print(f"  [로고 저장 실패] {name_en}: {e}")


def team_id(name_en, country, ids):
    key = name_en if SPORT == "football" else f"{SPORT}:{name_en}"
    if key in ids:
        return ids[key]

    def bad(n):  # 여자팀·유소년팀 제외
        return bool(re.search(r"\b(W|U\d{2}|Women|II|B)\b", n))

    def core(n):  # FC/SC 같은 꼬리표 빼고 비교 (API는 'Sydney FC'를 'Sydney'로 부르기도 함)
        return " ".join(w for w in re.sub(r"[^a-z0-9 ]", " ", n.lower()).split()
                        if w not in ("fc", "sc", "cf", "afc", "fk", "kf", "club", "royale", "real"))

    cands = []
    q_name = unicodedata.normalize("NFKD", name_en).encode("ascii", "ignore").decode()  # Köln → Koln (검색어는 영문만 됨)
    words = sorted(re.sub(r"[^A-Za-z0-9 ]", " ", q_name).split(), key=len, reverse=True)
    words = [w for w in words if len(w) >= 4]  # 단어 하나씩도 찾아봄 (예: Goyang Sono Skygunners → Goyang)
    for q in dict.fromkeys([re.sub(r"[^A-Za-z0-9 ]", " ", q_name).strip(), core(q_name)] + words):
        if len(q) < 3:
            continue
        found = api("/teams", search=q)
        cands = [t.get("team", t) for t in found if not bad(t.get("team", t)["name"])]
        if country:
            def cname(t):
                c = t.get("country")
                return (c.get("name") if isinstance(c, dict) else c or "").lower().replace("-", " ")
            cands = [t for t in cands if cname(t) == country.lower().replace("-", " ")] or cands
        if cands:
            break
    exact = [t for t in cands if core(t["name"]) == core(name_en)]
    pick = (exact or cands or [None])[0]
    if not pick:
        raise RuntimeError(f"팀을 찾지 못함: {name_en}")
    ids[key] = pick["id"]
    with open(IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
    save_logo(name_en, pick.get("logo"))
    print(f"  팀 찾음: {name_en} → {pick['name']} (id {pick['id']})")
    return pick["id"]


def h2h_rows(hid, aid):
    if SPORT == "football":
        return api("/fixtures/headtohead", h2h=f"{hid}-{aid}")
    return api("/games", h2h=f"{hid}-{aid}")


def norm(x):
    """축구·농구 경기 정보를 같은 모양으로."""
    if SPORT == "football":
        return {"date": x["fixture"]["date"], "status": x["fixture"]["status"]["short"],
                "home_id": x["teams"]["home"]["id"], "away_id": x["teams"]["away"]["id"],
                "home_name": x["teams"]["home"]["name"], "away_name": x["teams"]["away"]["name"],
                "hs": x["goals"]["home"], "as": x["goals"]["away"], "league": x["league"]["name"],
                "country": x["league"].get("country"),
                "venue": x["fixture"]["venue"]["name"], "round": x["league"].get("round")}
    return {"date": x["date"], "status": x["status"]["short"],
            "home_id": x["teams"]["home"]["id"], "away_id": x["teams"]["away"]["id"],
            "home_name": x["teams"]["home"]["name"], "away_name": x["teams"]["away"]["name"],
            "hs": x["scores"]["home"]["total"], "as": x["scores"]["away"]["total"],
            "league": x["league"]["name"], "venue": None, "round": x.get("week")}


def one_match(m, league_label, ids, article_time=None):
    hid = team_id(m["home_en"], m.get("home_country_en"), ids)
    aid = team_id(m["away_en"], m.get("away_country_en"), ids)
    rows = sorted(map(norm, h2h_rows(hid, aid)), key=lambda x: x["date"], reverse=True)
    names = {hid: m["home"], aid: m["away"]}
    now = datetime.datetime.now(datetime.timezone.utc)

    # 글의 경기 = 글 작성 시각 이후 열리는, 홈·원정이 같은 가장 빠른 경기
    posted = article_time or now
    same = [x for x in rows if x["home_id"] == hid
            and datetime.datetime.fromisoformat(x["date"]) > posted - datetime.timedelta(hours=6)]
    target = min(same, key=lambda x: x["date"]) if same else None
    match = {}
    finished = [x for x in rows if x["status"] in DONE_STATUS]
    if target:
        ko = datetime.datetime.fromisoformat(target["date"]).astimezone(KST)
        label = f"{ko.month}/{ko.day}({WEEK[ko.weekday()]}) {ko:%H:%M} KST"
        match = {"kickoff_kst": ko.isoformat(), "label": label, "league": target["league"], "country": target.get("country"),
                 "venue": target["venue"], "round": target["round"],
                 "api_ids": sorted([hid, aid])}  # 네이버·ESPN에 없는 리그 중복 막기용 (2026-10-21: EASL 같은 팀을 TSG/고스트호크스/타이난으로 다르게 씀)
        if target["status"] in DONE_STATUS or ko < now.astimezone(KST):
            match["finished"] = True
            if target["hs"] is not None:
                match["label"] = f"{label} 종료 {target['hs']}-{target['as']}"
        finished = [y for y in finished if y is not target]  # 그 경기 자체는 상대 전적에서 뺌
    done = finished[:6]
    w = d = l = 0
    matches = []
    for x in done:
        mine, theirs = (x["hs"], x["as"]) if x["home_id"] == hid else (x["as"], x["hs"])
        res = "승" if mine > theirs else "패" if mine < theirs else "무"
        w, d, l = w + (res == "승"), d + (res == "무"), l + (res == "패")
        matches.append({"date": x["date"][:10], "home": names.get(x["home_id"], x["home_name"]),
                        "away": names.get(x["away_id"], x["away_name"]),
                        "score": f"{x['hs']} - {x['as']}", "result": res})

    title = f"{m['home']} vs {m['away']}"
    stats = {
        "league": f"{title} · {match['label']}" if match else title,
        "basis": f"최근 맞대결 {len(done)}경기 · 출처 API-Sports" if done else "최근 맞대결 기록 없음 · 출처 API-Sports",
        "home": {"name": m["home"], "logo": m["home_en"]},
        "away": {"name": m["away"], "logo": m["away_en"]},
        "h2h": {"home_w": w, "d": d, "away_w": l, "label": f"{m['home']} 기준 {w}승 {d}무 {l}패"} if done else None,
        "h2h_matches": matches,
    }
    print(f"  {title}: 맞대결 {len(done)}경기 {w}승 {d}무 {l}패 / 경기 시간: {match.get('label', '찾지 못함')}")
    return stats, match


# ---------------------------------------------------------------- 네이버 스포츠 (2026-10-16 지시)
# API-Sports 로 못 가져오면 네이버 스포츠 일정·결과로 경기 시간·종료 여부·같은 리그 맞대결을 확인한다.
# 조합 픽 배너·차트에 붙이는 한글 리그명(에레디비시, 분데스리가 …)도 여기서 가져온다.
NAVER = "https://api-gw.sports.naver.com/schedule/games"
NAVER_UPPER = {"football": ["wfootball", "kfootball"], "basketball": ["kbasketball", "wbasketball"],
               "baseball": ["kbaseball", "wbaseball"], "volleyball": ["kvolleyball", "wvolleyball"]}
NAVER_ALL = ["wfootball", "kfootball", "kbasketball", "wbasketball", "kbaseball", "wbaseball", "kvolleyball",
             "wvolleyball"]  # 종목 확인용
NAVER_ONLY = {"volleyball", "baseball"}  # API-Sports 무료 키를 안 쓰고 네이버 스포츠로만 (배구, 2026-10-16)
_naver_cache = {}


def naver_games(upper, fr, to, category=None):
    key = (upper, fr, to, category)
    if key not in _naver_cache:
        params = {"fields": "basic,categoryId,categoryName", "upperCategoryId": upper, "fromDate": fr, "toDate": to, "size": 500}
        if category:
            params["categoryId"] = category
        if _naver_down[0]:  # 네이버가 완전히 먹통이면 같은 실행에서 또 기다리지 않음 (2026-10-28 장애로 실행 시간 낭비)
            raise requests.exceptions.ConnectionError("네이버 스포츠 응답 없음 (이번 실행에서 이미 실패)")
        for attempt in range(4):  # 서버에서 읽기 시간 초과가 가끔 나서 재시도 (2026-10-27 MLB 월드시리즈 글 막힘)
            try:
                r = requests.get(NAVER, params=params, timeout=45,
                                 headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.sports.naver.com/"})
                break
            except requests.exceptions.RequestException:
                if attempt == 3:
                    _naver_down[0] = True
                    raise
                time.sleep(3)
        _naver_cache[key] = r.json().get("result", {}).get("games", []) if r.ok else []
    return _naver_cache[key]


_naver_down = [False]
NAVER_ALIAS = {}
_alias_path = os.path.join(HERE, "naver_alias.json")  # 원문 표기 → 네이버 표기 (예: 덴하흐 → ADO 덴 하그)
if os.path.exists(_alias_path):
    with open(_alias_path, encoding="utf-8") as _f:
        NAVER_ALIAS = json.load(_f)


def name_score(a, b):
    a = NAVER_ALIAS.get(a.strip(), NAVER_ALIAS.get(re.sub(r"\s+", "", a), a))  # 띄어쓰기만 다른 표기도 (2026-10-20 파리 생제르망)
    a, b = re.sub(r"\s+", "", a), re.sub(r"\s+", "", b)
    return 1.0 if a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a)) else SequenceMatcher(None, a, b).ratio()


def naver_bracket(g, upper):
    """결승처럼 팀이 '준결승 A승'·'준결승 B승' 으로만 적힌 경기를 앞 준결승 승리 팀으로 바꿔 줌.
    (2026-10-25 버그: KOVO컵 남자 결승 대한항공 vs 현대캐피탈을 못 찾음) 앞 경기일 경기가 정확히 2개일 때만, 시간 순 A·B."""
    names = [re.fullmatch(r"(?:준결승|4강)\s*([AB])승", g.get(k, "")) for k in ("homeTeamName", "awayTeamName")]
    if not all(names):
        return g
    day = datetime.date.fromisoformat(g["gameDate"])
    prev = [x for x in naver_games(upper, (day - datetime.timedelta(days=3)).isoformat(),
                                   (day - datetime.timedelta(days=1)).isoformat(), g["categoryId"])
            if x.get("statusCode") == "RESULT" and x.get("categoryName") == g.get("categoryName") and not x.get("cancel")]
    if not prev:
        return g
    last = max(x["gameDate"] for x in prev)
    semis = sorted((x for x in prev if x["gameDate"] == last), key=lambda x: x["gameDateTime"])
    if len(semis) != 2 or any(x.get("winner") not in ("HOME", "AWAY") for x in semis):
        return g
    g = dict(g)
    for side, mt in zip(("home", "away"), names):
        s = semis["AB".index(mt.group(1))]
        w = "home" if s["winner"] == "HOME" else "away"
        for f in ("TeamName", "TeamCode", "TeamEmblemUrl"):
            g[side + f] = s[w + f]
    return g


def naver_find(m, article_time=None, uppers=None):
    """원문 한글 팀명으로 네이버 일정에서 그 경기를 찾는다 (글 작성일~4일 뒤).
    한 팀 이름이 같으면 그 경기 (나흘 안에 같은 팀 경기는 보통 하나, 표기 차이 예: 헤이렌베인/히렌빈). 아니면 두 팀 다 비슷해야 함."""
    start = (article_time or datetime.datetime.now(KST)).astimezone(KST).date()
    fr, to = start.isoformat(), (start + datetime.timedelta(days=4)).isoformat()
    after = ((article_time or datetime.datetime.now(KST)).astimezone(KST) - datetime.timedelta(hours=6)).replace(tzinfo=None)
    hits = []
    errs = []
    for upper in uppers or NAVER_UPPER.get(SPORT, []):
        try:  # 한 종류가 시간 초과여도 다른 종류에서 찾음 (2026-10-27 서버에서 MLB 글이 계속 막힘)
            day_games = naver_games(upper, fr, to)
        except requests.exceptions.RequestException as e:
            errs.append(e)
            continue
        for g in day_games:
            if g.get("cancel"):  # 연기·취소 경기는 건너뛰고 다시 잡힌 경기를 고름 (2026-10-17 버그: 연기된 ALCS 4차전을 '종료'로 봄)
                continue
            g = naver_bracket(g, upper)
            for swapped in (False, True):  # 원문에서 홈·원정을 알 수 없는 경우(야구 등) 뒤바뀐 것도 찾음
                hn, an = (g["awayTeamName"], g["homeTeamName"]) if swapped else (g["homeTeamName"], g["awayTeamName"])
                h, a = name_score(m["home"], hn), name_score(m["away"], an)
                # 한 팀 이름이 같아도 다른 팀이 전혀 안 닮았으면 다른 경기 (2026-10-17 버그: A리그 '뉴캐슬 제츠'를 EPL 뉴캐슬로 착각).
                # 표기가 크게 다른 팀은 naver_alias.json 에 적어 둠 (예: 헤이렌베인 → 히렌빈)
                if ((max(h, a) == 1.0 and min(h, a) >= 0.34) or min(h, a) >= 0.6) and \
                        datetime.datetime.fromisoformat(g["gameDateTime"]) >= after:
                    hits.append((g["gameDateTime"], -(h + a) + (0.01 if swapped else 0), dict(g, upper=upper, swapped=swapped)))
    # 같은 두 팀이 며칠 안에 여러 번 붙으면(야구 시리즈 등) 글 작성 뒤 가장 빠른 경기 (2026-10-17 버그: 6차전을 골랐음)
    if not hits and errs:
        raise errs[0]
    return min(hits, key=lambda x: (x[0], x[1]))[2] if hits else None


def naver_replaced(g):
    """연기·취소돼 이 경기로 다시 잡힌 앞 경기 번호 (같은 두 팀, 나흘 안). 같은 경기 중복 막기용
    (2026-10-25 버그: 비로 취소된 KS 1차전 10/25 14:00 → 10/26 18:30 으로 번호가 바뀌어 1723·1739 중복 게시)."""
    try:
        day = datetime.date.fromisoformat(g["gameDate"])
        teams = {g["homeTeamCode"], g["awayTeamCode"]}
        return [x["gameId"] for x in naver_games(g["upper"], (day - datetime.timedelta(days=4)).isoformat(), day.isoformat())
                if x.get("cancel") and x["gameId"] != g["gameId"] and {x["homeTeamCode"], x["awayTeamCode"]} == teams
                and x["gameDateTime"] < g["gameDateTime"]]
    except Exception:
        return []


def naver_match(m, article_time=None):
    """네이버만으로 경기 정보 + 같은 리그 최근 맞대결 6경기 (API-Sports 실패 시)."""
    g = naver_find(m, article_time)
    if not g:
        raise RuntimeError("네이버 스포츠에서도 경기를 찾지 못함")
    now = datetime.datetime.now(KST)
    ko = datetime.datetime.fromisoformat(g["gameDateTime"]).replace(tzinfo=KST)
    label = f"{ko.month}/{ko.day}({WEEK[ko.weekday()]}) {ko:%H:%M} KST"
    match = {"kickoff_kst": ko.isoformat(), "label": label, "league": g["categoryName"],
             "league_ko": g["categoryName"], "venue": None, "round": None, "source": "네이버 스포츠"}
    if g["statusCode"] == "RESULT" or ko < now:
        match["finished"] = True
        if g["statusCode"] == "RESULT":
            hs, as_ = (g["awayTeamScore"], g["homeTeamScore"]) if g.get("swapped") else (g["homeTeamScore"], g["awayTeamScore"])
            match["label"] = f"{label} 종료 {hs}-{as_}"
    hc, ac = g["homeTeamCode"], g["awayTeamCode"]
    if g.get("swapped"):
        hc, ac = ac, hc
        match["swapped"] = True
    if SPORT in NAVER_ONLY:  # 구단 엠블럼 = 네이버 이미지 (원본 크기 그대로, 확대 안 함)
        urls = (g.get("awayTeamEmblemUrl"), g.get("homeTeamEmblemUrl")) if g.get("swapped") else (g.get("homeTeamEmblemUrl"), g.get("awayTeamEmblemUrl"))
        for name_en, url in zip((m["home_en"], m["away_en"]), urls):
            save_logo(name_en, url)
    rows = []
    for y in ([] if SPORT == "baseball" else range(ko.year, ko.year - 5, -1)):  # 최근 5년, 같은 리그 (야구는 mlb_data.py 가 공식 기록으로)
        for x in naver_games(g["upper"], f"{y}-01-01", f"{y}-12-31", g["categoryId"]):
            if {x["homeTeamCode"], x["awayTeamCode"]} == {hc, ac} and x["statusCode"] == "RESULT" \
                    and x["gameId"] != g["gameId"]:
                rows.append(x)
    rows = sorted(rows, key=lambda x: x["gameDateTime"], reverse=True)[:6]
    w = d = l = 0
    matches = []
    for x in rows:
        mine, theirs = (x["homeTeamScore"], x["awayTeamScore"]) if x["homeTeamCode"] == hc else (x["awayTeamScore"], x["homeTeamScore"])
        res = "승" if mine > theirs else "패" if mine < theirs else "무"
        w, d, l = w + (res == "승"), d + (res == "무"), l + (res == "패")
        matches.append({"date": x["gameDate"], "home": m["home"] if x["homeTeamCode"] == hc else m["away"],
                        "away": m["away"] if x["homeTeamCode"] == hc else m["home"],
                        "score": f"{x['homeTeamScore']} - {x['awayTeamScore']}", "result": res})
    title = f"{m['home']} vs {m['away']}"
    stats = {
        "league": f"{title} · {match['label']}",
        "basis": f"최근 맞대결 {len(rows)}경기({g['categoryName']}) · 출처 네이버 스포츠" if rows else "최근 맞대결 기록 없음 · 출처 네이버 스포츠",
        "home": {"name": m["home"], "logo": m["home_en"]},
        "away": {"name": m["away"], "logo": m["away_en"]},
        "h2h": {"home_w": w, "d": d, "away_w": l, "label": f"{m['home']} 기준 {w}승 {d}무 {l}패"} if rows else None,
        "h2h_matches": matches,
    }
    print(f"  {title}: [네이버] 맞대결 {len(rows)}경기 {w}승 {d}무 {l}패 / 경기 시간: {match['label']} / {g['categoryName']}")
    return stats, match


ESPN_LEAGUE_KO = {"chinese-super-league": "중국 슈퍼리그"}


def espn_match(m, article_time=None):
    """ESPN 축구 일정으로 경기 시간 확인 (API-Football 한도 소진 + 네이버에 없는 리그, 2026-10-18 다른 출처로 확인하고 올림).
    영어 팀명 두 개가 모두 비슷해야 같은 경기. 맞대결 기록은 없음."""
    if SPORT != "football":
        raise RuntimeError("ESPN 확인은 축구만")
    start = (article_time or datetime.datetime.now(KST)).astimezone(KST)
    after = start - datetime.timedelta(hours=6)
    hits = []
    for k in range(-1, 4):  # ESPN 날짜는 미국 기준이라 하루 앞도 봄
        day = (start + datetime.timedelta(days=k)).strftime("%Y%m%d")
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard",
                         params={"dates": day, "limit": 1000}, timeout=30).json()
        for e in r.get("events", []):
            teams = {c["homeAway"]: c["team"] for c in e["competitions"][0]["competitors"]}
            if "home" not in teams or "away" not in teams:
                continue
            ko = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(KST)
            if ko < after:
                continue
            for swapped in (False, True):
                ht, at = (teams["away"], teams["home"]) if swapped else (teams["home"], teams["away"])
                h = max(name_score(m["home_en"].lower(), (ht.get(x) or "").lower()) for x in ("displayName", "shortDisplayName"))
                a = max(name_score(m["away_en"].lower(), (at.get(x) or "").lower()) for x in ("displayName", "shortDisplayName"))
                if min(h, a) >= 0.8:  # 두 팀 모두 거의 같은 이름일 때만 (비슷한 이름 착각 방지: Shanghai Port/Shanghai Shenhua 0.59)
                    hits.append((ko, -(h + a), e, swapped, ht, at))
    if not hits:
        raise RuntimeError("ESPN 에서도 경기를 찾지 못함")
    ko, _, e, swapped, ht, at = min(hits, key=lambda x: (x[0], x[1]))
    now = datetime.datetime.now(KST)
    label = f"{ko.month}/{ko.day}({WEEK[ko.weekday()]}) {ko:%H:%M} KST"
    slug = re.sub(r"^\d{4}(-\d{2})?-", "", e.get("season", {}).get("slug", ""))
    league_en = slug.replace("-", " ").title()
    league = ESPN_LEAGUE_KO.get(slug) or league_en
    match = {"kickoff_kst": ko.isoformat(), "label": label, "league": league_en, "league_ko": league,
             "venue": None, "round": None, "source": "ESPN", "espn_game_id": e["id"]}
    if swapped:
        match["swapped"] = True
    if ko < now or e["status"]["type"].get("state") != "pre":
        match["finished"] = True
    for name_en, t in ((m["home_en"], ht), (m["away_en"], at)):  # 구단 로고 = ESPN 이미지 (원본 크기 그대로)
        if t.get("logo"):
            try:
                save_logo(name_en, t["logo"])
            except Exception:
                pass
    title = f"{m['home']} vs {m['away']}"
    stats = {"league": f"{title} · {label}", "basis": "최근 맞대결 기록 없음 · 경기 시간 출처 ESPN",
             "home": {"name": m["home"], "logo": m["home_en"]}, "away": {"name": m["away"], "logo": m["away_en"]},
             "h2h": None, "h2h_matches": []}
    print(f"  {title}: [ESPN] {ht.get('displayName')} vs {at.get('displayName')} / 경기 시간: {label} / {league}")
    return stats, match


def mlb_match(m, article_time=None):
    """MLB 공식 일정(statsapi.mlb.com)으로 경기 시간 확인 (2026-10-27 네이버 읽기 시간 초과로 월드시리즈 글이 막혀 MLB 공식으로 변경)."""
    import re as _re
    def nm(x):
        return _re.sub(r"[^a-z]", "", (x or "").lower())
    now = datetime.datetime.now(KST)
    base = (article_time or now).astimezone(KST)
    start = (base - datetime.timedelta(days=1)).date()
    r = requests.get("https://statsapi.mlb.com/api/v1/schedule", timeout=30,
                     params={"sportId": 1, "startDate": start.isoformat(),
                             "endDate": (start + datetime.timedelta(days=4)).isoformat()})
    r.raise_for_status()
    found = []
    for d in r.json().get("dates", []):
        for g in d["games"]:
            names = {s: nm(g["teams"][s]["team"]["name"]) for s in ("home", "away")}
            ok = all(any(nm(w) in names[s] for w in m[f"{k}_en"].split() if len(w) > 3) for s, k in (("home", "home"), ("away", "away")))
            if ok and g["status"]["detailedState"] not in ("Postponed", "Cancelled"):
                found.append(g)
    if not found:
        raise RuntimeError("MLB 공식 일정에서 경기를 찾지 못함")
    found.sort(key=lambda g: g["gameDate"])
    upcoming = [g for g in found if g["status"]["abstractGameState"] == "Preview"]
    g = upcoming[0] if upcoming else found[-1]
    ko = datetime.datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")).astimezone(KST)
    label = f"{ko.month}/{ko.day}({WEEK[ko.weekday()]}) {ko:%H:%M} KST"
    match = {"kickoff_kst": ko.isoformat(), "label": label, "league": "MLB", "league_ko": "MLB",
             "venue": None, "round": None, "source": "MLB 공식 일정"}
    if g["status"]["abstractGameState"] != "Preview" or ko < now:
        match["finished"] = True
    title = f"{m['home']} vs {m['away']}"
    stats = {
        "league": f"{title} · {label}",
        "basis": "최근 맞대결 기록 없음 · 출처 MLB 공식",
        "home": {"name": m["home"], "logo": m["home_en"]},
        "away": {"name": m["away"], "logo": m["away_en"]},
        "h2h": None,
        "h2h_matches": [],
    }
    print(f"  {title}: [MLB 공식] 경기 시간: {label} ({g['status']['detailedState']})")
    return stats, match


# ---------------------------------------------------------------- KBO·NPB 공식 일정 (2026-10-29)
# 네이버 스포츠가 서버에서 자주 응답하지 않아(읽기 시간 초과) 야구는 경기 시간을 공식 일정으로 먼저 확인한다.
KBO_TEAMS = {"기아": "KIA", "kia": "KIA", "kt": "KT", "lg": "LG", "nc": "NC", "ssg": "SSG", "삼성": "삼성", "두산": "두산",
             "롯데": "롯데", "한화": "한화", "키움": "키움"}
NPB_TEAMS = {"소프트뱅크": "ソフトバンク", "니혼햄": "日本ハム", "닛폰햄": "日本ハム", "롯데": "ロッテ", "라쿠텐": "楽天",
             "세이부": "西武", "오릭스": "オリックス", "요미우리": "巨人", "한신": "阪神", "요코하마": "DeNA", "DeNA": "DeNA",
             "dena": "DeNA", "히로시마": "広島", "야쿠르트": "ヤクルト", "주니치": "中日"}


def _official_result(m, title_src, ko, league, now):
    label = f"{ko.month}/{ko.day}({WEEK[ko.weekday()]}) {ko:%H:%M} KST"
    match = {"kickoff_kst": ko.isoformat(), "label": label, "league": league, "league_ko": league,
             "venue": None, "round": None, "source": f"{league} 공식 일정"}
    if ko < now:
        match["finished"] = True
    title = f"{m['home']} vs {m['away']}"
    stats = {"league": f"{title} · {label}", "basis": f"최근 맞대결 기록 없음 · 출처 {title_src}",
             "home": {"name": m["home"], "logo": m.get("home_en", m["home"])},
             "away": {"name": m["away"], "logo": m.get("away_en", m["away"])}, "h2h": None, "h2h_matches": []}
    print(f"  {title}: [{league} 공식] 경기 시간: {label}")
    return stats, match


def _pick_game(cands, base):
    """글이 올라온 시각 직후의 가장 빠른 경기(글이 올라오기 6시간 전까지는 인정), 없으면 가장 최근 경기.
    (지금 시각 기준으로 고르면 지난 글이 며칠 뒤 다른 경기로 잘못 이어짐)"""
    cands.sort()
    after = [c for c in cands if c >= base - datetime.timedelta(hours=6)]
    return after[0] if after else cands[-1]


def kbo_match(m, article_time=None):
    """KBO 공식 일정(koreabaseball.com)으로 경기 시간 확인."""
    now = datetime.datetime.now(KST)
    base = (article_time or now).astimezone(KST)
    want = set()
    for k in ("home", "away"):
        n = KBO_TEAMS.get(re.sub(r"\s+", "", m[k]).lower())
        if not n:
            raise RuntimeError(f"KBO 팀이 아님: {m[k]}")
        want.add(n)
    start, end = base - datetime.timedelta(days=1), base + datetime.timedelta(days=5)
    months = sorted({(start.year, start.month), (end.year, end.month)})
    cands = []
    for yy, mm in months:
        r = requests.post("https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList", timeout=30,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.koreabaseball.com/Schedule/Schedule.aspx"},
                          data={"leId": 1, "srIdList": "0,1,3,4,5,7,8,9,6", "seasonId": yy, "gameMonth": f"{mm:02d}", "teamId": ""})
        r.raise_for_status()
        day = None
        for row in r.json().get("rows", []):
            cells = [re.sub(r"<[^>]+>", "", c.get("Text") or "").strip() for c in row["row"]]
            htmls = [c.get("Text") or "" for c in row["row"]]
            if cells and re.match(r"\d{2}\.\d{2}\(", cells[0]):
                day = cells.pop(0)
                htmls.pop(0)
            if day is None or len(cells) < 8:
                continue
            tm = re.match(r"\d{1,2}:\d{2}$", cells[0])
            teams = re.findall(r"<span>([^<]+)</span>", htmls[1])
            if not tm or len(teams) < 2 or {teams[0], teams[-1]} != want or "취소" in cells[7]:
                continue
            mo, dd = int(day[:2]), int(day[3:5])
            hh, mi = cells[0].split(":")
            cands.append(datetime.datetime(yy, mo, dd, int(hh), int(mi), tzinfo=KST))
    cands = [c for c in cands if start <= c <= end]
    if not cands:
        raise RuntimeError("KBO 공식 일정에서 경기를 찾지 못함")
    return _official_result(m, "KBO 공식", _pick_game(cands, base), "KBO", now)


def npb_match(m, article_time=None):
    """NPB 공식 일정(npb.jp)으로 경기 시간 확인."""
    now = datetime.datetime.now(KST)
    base = (article_time or now).astimezone(KST)
    want = set()
    for k in ("home", "away"):
        n = NPB_TEAMS.get(re.sub(r"\s+", "", m[k]).lower()) or NPB_TEAMS.get(re.sub(r"\s+", "", m[k]))
        if not n:
            raise RuntimeError(f"NPB 팀이 아님: {m[k]}")
        want.add(n)
    start, end = base - datetime.timedelta(days=1), base + datetime.timedelta(days=5)
    months = sorted({(start.year, start.month), (end.year, end.month)})
    cands = []
    for yy, mm in months:
        r = requests.get(f"https://npb.jp/games/{yy}/schedule_{mm:02d}_detail.html", timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        r.encoding = "utf-8"
        day = None
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
            dm = re.search(r"<th[^>]*>\s*(\d{1,2})/(\d{1,2})", tr)
            if dm:
                day = (int(dm.group(1)), int(dm.group(2)))
            t1 = re.search(r'class="team1">([^<]+)<', tr)
            t2 = re.search(r'class="team2">([^<]+)<', tr)
            tm = re.search(r'class="time">\s*(\d{1,2}):(\d{2})', tr)
            if not (day and t1 and t2 and tm) or {t1.group(1).strip(), t2.group(1).strip()} != want:
                continue
            cands.append(datetime.datetime(yy, day[0], day[1], int(tm.group(1)), int(tm.group(2)), tzinfo=KST))
    cands = [c for c in cands if start <= c <= end]
    if not cands:
        raise RuntimeError("NPB 공식 일정에서 경기를 찾지 못함")
    return _official_result(m, "NPB 공식", _pick_game(cands, base), "NPB", now)


KOVO_ALIAS = {"soop": ["정관장", "kgc"], "한국도로공사": ["도로공사"], "ibk기업은행": ["기업은행"], "페퍼저축은행": ["페퍼"],
              "한국전력": ["한전", "kepco"], "ok저축은행": ["okc", "읏맨"], "kb손해보험": ["kb"], "gs칼텍스": ["gs", "칼텍스"]}


def _kovo_same(kname, article_name):
    a = re.sub(r"\s+", "", article_name).lower()
    for t in [re.sub(r"\s+", "", kname).lower()] + KOVO_ALIAS.get(re.sub(r"\s+", "", kname).lower(), []):
        if len(t) >= 2 and t in a:
            return True
    return False


def kovo_match(m, article_time=None):
    """KOVO 공식 일정(user-api.kovo.co.kr)으로 V리그 경기 시간 확인. 오늘·가까운 경기 몇 개만 내려옴."""
    now = datetime.datetime.now(KST)
    base = (article_time or now).astimezone(KST)
    r = requests.get("https://user-api.kovo.co.kr/mains/games/schedules", timeout=30,
                     headers={"User-Agent": "Mozilla/5.0", "Origin": "https://kovo.co.kr"})
    r.raise_for_status()
    start, end = base - datetime.timedelta(days=1), base + datetime.timedelta(days=5)
    cands = []
    for g in r.json().get("payload") or []:
        h, a = g["homeTeam"]["name"], g["awayTeam"]["name"]
        ok = (_kovo_same(h, m["home"]) and _kovo_same(a, m["away"])) or (_kovo_same(h, m["away"]) and _kovo_same(a, m["home"]))
        if not ok:
            continue
        hh, mi = g["startTime"].split(":")
        y, mo, dd = map(int, g["gameDate"].split("-"))
        cands.append(datetime.datetime(y, mo, dd, int(hh), int(mi), tzinfo=KST))
    cands = [c for c in cands if start <= c <= end]
    if not cands:
        raise RuntimeError("KOVO 공식 일정에서 경기를 찾지 못함")
    return _official_result(m, "KOVO 공식", _pick_game(cands, base), "V-리그", now)


KBL_HEADERS = {"teamcode": "XX", "lang": "ko", "channel": "WEB", "x-requested-with": "XMLHttpRequest",
               "referer": "https://www.kbl.or.kr/", "user-agent": "Mozilla/5.0", "accept": "application/json, text/plain, */*"}


def kbl_match(m, article_time=None):
    """KBL 공식 일정(api.kbl.or.kr)으로 경기 시간 확인."""
    now = datetime.datetime.now(KST)
    base = (article_time or now).astimezone(KST)
    start, end = base - datetime.timedelta(days=1), base + datetime.timedelta(days=5)
    r = requests.get("https://api.kbl.or.kr/match/list", timeout=30, headers=KBL_HEADERS,
                     params={"fromDate": start.strftime("%Y%m%d"), "toDate": end.strftime("%Y%m%d"), "tcodeList": "all"})
    r.raise_for_status()
    key = {k: re.sub(r"\s+", "", m[k]) for k in ("home", "away")}
    cands = []
    for g in r.json():
        h, a = re.sub(r"\s+", "", g["tnameH"]), re.sub(r"\s+", "", g["tnameA"])
        if not ((key["home"] in h and key["away"] in a) or (key["home"] in a and key["away"] in h)) or "취소" in str(g.get("gameStatus", "")):
            continue
        cands.append(datetime.datetime.strptime(g["gameDate"] + g["gameStart"], "%Y%m%d%H%M").replace(tzinfo=KST))
    cands = [c for c in cands if start <= c <= end]
    if not cands:
        raise RuntimeError("KBL 공식 일정에서 경기를 찾지 못함")
    return _official_result(m, "KBL 공식", _pick_game(cands, base), "KBL", now)


def nba_match(m, article_time=None):
    """NBA 일정(ESPN scoreboard)으로 경기 시간 확인. 영어 팀명 두 개가 모두 거의 같아야 인정."""
    now = datetime.datetime.now(KST)
    base = (article_time or now).astimezone(KST)
    start, end = base - datetime.timedelta(days=1), base + datetime.timedelta(days=5)
    cands = []
    for k in range(-1, 6):  # ESPN 날짜는 미국 기준이라 하루 앞도 봄
        day = (base + datetime.timedelta(days=k)).strftime("%Y%m%d")
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", params={"dates": day}, timeout=30)
        r.raise_for_status()
        for e in r.json().get("events", []):
            teams = [c["team"] for c in e["competitions"][0]["competitors"]]
            if len(teams) != 2:
                continue
            for t1, t2 in ((teams[0], teams[1]), (teams[1], teams[0])):
                h = max(name_score(m["home_en"].lower(), (t1.get(x) or "").lower()) for x in ("displayName", "shortDisplayName"))
                a = max(name_score(m["away_en"].lower(), (t2.get(x) or "").lower()) for x in ("displayName", "shortDisplayName"))
                if min(h, a) >= 0.8:
                    cands.append(datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(KST))
    cands = [c for c in cands if start <= c <= end]
    if not cands:
        raise RuntimeError("NBA 일정(ESPN)에서 경기를 찾지 못함")
    return _official_result(m, "NBA 일정(ESPN)", _pick_game(cands, base), "NBA", now)


def main():
    global SPORT
    if "--sport" in sys.argv:
        SPORT = sys.argv[sys.argv.index("--sport") + 1]
    folder = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    with open(os.path.join(folder, "post.json"), encoding="utf-8") as f:
        post = json.load(f)
    ids = load_ids()
    article_time = None
    art_path = os.path.join(folder, "article.json")
    if os.path.exists(art_path):
        with open(art_path, encoding="utf-8") as f:
            d = json.load(f).get("date", "")
        try:
            article_time = datetime.datetime.strptime(d, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        except ValueError:
            pass
    # 라이브스코어 글은 날짜만(00:00) 있음 → 처음 발견한 시각(seen.json)으로 (2026-10-19 버그: 10/18 22:40 에 본
    # '10월19일 클리블랜드 vs 탬파베이' 글을 이미 끝난 10/18 09:08 경기로 찾아 '이미 올린 경기'로 건너뜀)
    base = os.path.basename(folder.rstrip("/")).split("-")[0]
    if base.startswith("ls") and article_time and article_time.strftime("%H:%M") == "00:00":
        try:
            with open(os.path.join(HERE, "seen.json"), encoding="utf-8") as f:
                first = json.load(f).get(base)
            if first:
                article_time = max(article_time, datetime.datetime.strptime(first, "%Y-%m-%d %H:%M").replace(tzinfo=KST))
        except Exception:
            pass
    failed = 0
    combo = len(post.get("matches", [])) > 1
    for i, m in enumerate(post.get("matches", []), 1):
        try:
            if SPORT in NAVER_ONLY:
                raise RuntimeError("이 종목은 네이버 스포츠로 확인")
            stats, match = one_match(m, post.get("league_label", ""), ids, article_time)
            if not match.get("kickoff_kst"):  # 팀을 잘못 찾아 경기가 없으면 네이버로 (2026-10-18 버그: 정관장을 다른 나라 팀으로 찾아 경기 시간 없음 → 게시 막힘)
                raise RuntimeError("API-Sports 에서 이 경기를 찾지 못함")
            try:  # 한글 리그명은 네이버에서 (못 찾으면 영어 리그명 그대로)
                g = naver_find(m, article_time)
                match["league_ko"] = g["categoryName"] if g else match.get("league")
            except Exception:
                match["league_ko"] = match.get("league")
        except Exception as e:
            print(f"  [API-Sports 실패] {m.get('home')} vs {m.get('away')}: {e} → 네이버 스포츠로 확인")
            try:
                if SPORT == "baseball":  # MLB 는 공식 일정 먼저 (KBO·NPB 는 이름이 안 맞아 아래 네이버로)
                    try:
                        stats, match = mlb_match(m, article_time)
                    except Exception as e0:
                        print(f"  [MLB 공식 일정 없음] {e0} → KBO 공식")
                        try:
                            stats, match = kbo_match(m, article_time)
                        except Exception as e1:
                            print(f"  [KBO 공식 일정 없음] {e1} → NPB 공식")
                            try:
                                stats, match = npb_match(m, article_time)
                            except Exception as e1b:
                                print(f"  [NPB 공식 일정 없음] {e1b} → 네이버")
                                stats, match = naver_match(m, article_time)
                elif SPORT == "volleyball":  # 네이버가 안 되면 KOVO 공식 일정 (2026-10-31: 네이버 응답 없음으로 배구 글 막힘)
                    try:
                        stats, match = naver_match(m, article_time)
                    except Exception as e0:
                        print(f"  [네이버 실패] {e0} → KOVO 공식")
                        stats, match = kovo_match(m, article_time)
                elif SPORT == "basketball":  # 네이버가 안 되면 KBL 공식 → NBA(ESPN) 일정
                    try:
                        stats, match = naver_match(m, article_time)
                    except Exception as e0:
                        print(f"  [네이버 실패] {e0} → KBL 공식")
                        try:
                            stats, match = kbl_match(m, article_time)
                        except Exception as e1:
                            print(f"  [KBL 공식 일정 없음] {e1} → NBA(ESPN)")
                            stats, match = nba_match(m, article_time)
                else:
                    stats, match = naver_match(m, article_time)
            except Exception as e2:
                try:  # 네이버에도 없는 리그 → ESPN 으로 경기 시간 확인 (2026-10-18 )
                    stats, match = espn_match(m, article_time)
                except Exception as e3:
                    print(f"  [실패] {m.get('home')} vs {m.get('away')}: {e2} / {e3}")
                    failed += 1
                    continue
        if str(match.get("source", "")).endswith("공식 일정"):  # 공식 일정으로 찾은 경기는 네이버 종목 확인·경기 번호를 건너뜀
            with open(os.path.join(folder, f"stats_{i}.json"), "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            with open(os.path.join(folder, f"match_{i}.json"), "w", encoding="utf-8") as f:
                json.dump(match, f, ensure_ascii=False, indent=2)
            continue
        try:  # 종목 확인: 모든 종목 일정에서 찾아 어느 종목 경기인지 기록 → run_pick 이 게시판 종목과 다르면 막음
            # 게시판 종목에서 먼저 찾고, 없을 때만 다른 종목까지 (2026-10-17 버그: 농구 'LG'를 야구 KIA vs LG로 착각)
            g_any = naver_find(m, article_time) or naver_find(m, article_time, NAVER_ALL)
            if g_any:
                match["naver_upper"] = g_any["upper"]
                match["naver_game"] = f"{g_any['categoryName']} {g_any['homeTeamName']} vs {g_any['awayTeamName']}"
                match["naver_game_id"] = g_any["gameId"]  # 같은 경기 중복 막기용
                match["naver_replaces"] = naver_replaced(g_any)  # 연기 전 경기 번호도 같은 경기로
        except Exception:
            pass
        if combo and match.get("league_ko"):  # 조합 픽: 차트 제목에 경기별 리그명 (2026-10-16 지시)
            stats["league"] = f"{match['league_ko']} · {stats['league']}"
        with open(os.path.join(folder, f"stats_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(os.path.join(folder, f"match_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(match, f, ensure_ascii=False, indent=2)
    sys.exit(1 if failed == len(post.get("matches", [])) else 0)


if __name__ == "__main__":
    main()
