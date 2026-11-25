#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
팀 최근 5경기 결과(승·무·패)를 ESPN 공개 자료에서 가져온다 (2026-11-25 제프: 배너에 최근 5경기 칩).
네이버가 서버에서 응답이 없어도 되도록 ESPN만 쓴다. 못 찾으면 빈 목록 — 글은 그대로 올라가고 칩만 빠진다.
"""
import datetime
import re

import requests

UA = {"User-Agent": "Mozilla/5.0"}
_cache = {}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _ascii(t):
    """é·ü 같은 악센트 글자는 차트 글꼴에서 네모로 나와 기본 글자로 바꿈"""
    import unicodedata
    t = (t or "").translate(str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "œ": "oe"}))
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


_STOP = {"fc", "sc", "cf", "rc", "fk", "ac", "as", "afc", "club", "cd", "sk", "bk", "if", "fcsb"}


def _core(t):
    """팀 이름에서 FC·SC 같은 흔한 꼬리표·악센트·기호를 빼고 핵심 단어만 (예: 'FC Porto'='Porto', 'Houston Dynamo FC'='Houston Dynamo')"""
    words = re.findall(r"[a-z0-9]+", _ascii(t).lower())
    core = [w for w in words if w not in _STOP]
    return "".join(core or words)


def team_id(name_en):
    """영어 팀명으로 ESPN (팀 번호, 대표 리그). 같은 이름이 여럿(여자팀·21세 이하)이면 남자 1군."""
    key = ("id", name_en)
    if key in _cache:
        return _cache[key]
    best, tid, lgslug = 0.0, None, ""
    try:
        import difflib
        want = _core(name_en)
        plain = re.sub(r"[^A-Za-z0-9 ]+", " ", _ascii(name_en)).split()
        queries = [name_en, " ".join(plain), " ".join(w for w in plain if w.lower() not in _STOP)]  # ESPN 검색은 'RC Lens'·'FK Bodø/Glimt' 같은 이름은 못 찾음 → 꼬리표·기호를 뺀 이름도 시도
        seen_q = set()
        for q in queries:
            if not q or q in seen_q:
                continue
            seen_q.add(q)
            r = requests.get("https://site.web.api.espn.com/apis/common/v3/search",
                             params={"query": q, "type": "team", "limit": 8, "sport": "soccer"}, timeout=20, headers=UA)
            for it in r.json().get("items") or []:
                nm = _core(it.get("displayName") or it.get("name"))
                lg = it.get("league") or ""
                if ".w." in lg or re.search(r"u\d\d", _norm(it.get("displayName") or "")):
                    continue
                sc = 1.0 if nm == want else (0.9 if (want and nm and (want in nm or nm in want)) else difflib.SequenceMatcher(None, want, nm).ratio())
                if sc > best:
                    best, tid, lgslug = sc, it.get("id"), lg
            if best >= 0.9:
                break
        if best < 0.7:
            tid, lgslug = None, ""
    except Exception:
        tid, lgslug = None, ""
    _cache[key] = (tid, lgslug)
    return _cache[key]


def recent_games(team, before_iso, n=5):
    """before_iso 전에 끝난 최근 n경기 상세 → [{"date":"11.21","pf":2,"pa":1,"result":"승|무|패","opp":"상대(영어)","home":True}] 오래된 순.
    ESPN 전체 일정(all)과 그 팀 대표 리그 일정을 합쳐 본다(MLS 등은 all 에 없음). 가장 최근 경기가 3주보다 오래됐으면 '최근'이 아니라 빈 목록."""
    tid, lg = team
    if not tid:
        return []
    key = ("games", tid, before_iso, n)
    if key in _cache:
        return _cache[key]
    out = []
    try:
        before = datetime.datetime.fromisoformat(before_iso)
        if before.tzinfo is None:
            before = before.replace(tzinfo=datetime.timezone.utc)
        kst = datetime.timezone(datetime.timedelta(hours=9))
        seen, rows = set(), []
        for slug in ("all", lg):
            if not slug:
                continue
            try:
                j = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams/{tid}/schedule", timeout=25, headers=UA).json()
            except Exception:
                continue
            for e in j.get("events", []):
                if e.get("id") in seen:
                    continue
                c = e["competitions"][0]
                if not c["status"]["type"]["completed"]:
                    continue
                ko = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
                if ko >= before:
                    continue
                me = [x for x in c["competitors"] if str(x["team"]["id"]) == str(tid)]
                op = [x for x in c["competitors"] if str(x["team"]["id"]) != str(tid)]
                if not me or not op:
                    continue

                def sc(x):
                    v = x.get("score")
                    v = v.get("displayValue") if isinstance(v, dict) else v
                    return int(float(v))
                a, b = sc(me[0]), sc(op[0])
                seen.add(e.get("id"))
                rows.append((ko, {"date": ko.astimezone(kst).strftime("%m.%d"), "pf": a, "pa": b,
                                  "result": "승" if a > b else ("패" if a < b else "무"),
                                  "opp": _ascii(op[0]["team"].get("shortDisplayName") or op[0]["team"].get("displayName", "")),
                                  "home": me[0].get("homeAway") == "home"}))
        rows.sort(key=lambda r: r[0])
        if rows and (before - rows[-1][0]) <= datetime.timedelta(days=21):
            out = [r for _, r in rows[-n:]]
    except Exception:
        out = []
    _cache[key] = out
    return out


def last5(team, before_iso):
    """['W','D','L', ...] 오래된 순 (배너 칩용)"""
    return [{"승": "W", "무": "D", "패": "L"}[g["result"]] for g in recent_games(team, before_iso)]


def forms(home_en, away_en, before_iso):
    """(홈 최근 5경기, 원정 최근 5경기). 하나라도 못 찾으면 둘 다 비움(한쪽만 있으면 어색해서)."""
    if not (home_en and away_en and before_iso):
        return [], []
    h, a = last5(team_id(home_en), before_iso), last5(team_id(away_en), before_iso)
    if len(h) < 3 or len(a) < 3:
        return [], []
    return h, a


if __name__ == "__main__":
    import sys
    print(forms(sys.argv[1], sys.argv[2], sys.argv[3]))
