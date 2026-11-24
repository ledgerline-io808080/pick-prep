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


def team_id(name_en):
    """영어 팀명으로 ESPN 팀 번호. 같은 이름이 여럿(여자팀·21세 이하)이면 맨 앞 남자 1군."""
    key = ("id", name_en)
    if key in _cache:
        return _cache[key]
    tid = None
    lgslug = ""
    try:
        r = requests.get("https://site.web.api.espn.com/apis/common/v3/search",
                         params={"query": name_en, "type": "team", "limit": 6, "sport": "soccer"}, timeout=20, headers=UA)
        items = r.json().get("items") or []
        want = _norm(name_en)
        for it in items:
            nm = _norm(it.get("displayName") or it.get("name"))
            lg = (it.get("league") or "")
            if nm == want and ".w." not in lg and not re.search(r"u\d\d", nm):
                tid = it.get("id")
                lgslug = lg
                break
    except Exception:
        tid = None
    _cache[key] = (tid, lgslug)
    return _cache[key]


def last5(team, before_iso):
    """before_iso(경기 시작 시각) 전에 끝난 경기 중 최근 5개 → ['W','D','L', ...] 오래된 순.
    ESPN 전체 일정(all)과 그 팀 대표 리그 일정을 합쳐 본다(MLS 등은 all 에 없음). 가장 최근 경기가 3주보다 오래됐으면 '최근'이 아니라 빈 목록."""
    tid, lg = team
    if not tid:
        return []
    key = ("form", tid, before_iso)
    if key in _cache:
        return _cache[key]
    out = []
    try:
        before = datetime.datetime.fromisoformat(before_iso)
        if before.tzinfo is None:
            before = before.replace(tzinfo=datetime.timezone.utc)
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
                rows.append((ko, "W" if a > b else ("L" if a < b else "D")))
        rows.sort()
        if rows and (before - rows[-1][0]) <= datetime.timedelta(days=21):
            out = [r for _, r in rows[-5:]]
    except Exception:
        out = []
    _cache[key] = out
    return out


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
