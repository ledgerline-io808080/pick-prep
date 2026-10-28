#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
team_flow.py

축구·야구·배구 글에도 농구와 같은 '팀 흐름' 차트(최근 경기 득점·실점 꺾은선 + 최근 성적표)를 넣기 위해
네이버 스포츠 경기 결과에서 두 팀의 최근 경기를 가져와 flow_<n>.json 을 만든다 (2026-10-17 농구랑 동일하게).
make_stats_b.py 가 이 파일을 그대로 그린다(농구는 kbl_data.py 가 같은 모양의 kbl_<n>.json 을 만듦).

- 경기는 h2h.py 가 남긴 match_<n>.json 의 네이버 경기 번호(naver_game_id)로 찾는다. 점수는 네이버 결과 그대로.
- 같은 대회(리그) 경기만, 경기 시작 전 끝난 경기 중 최근 5경기. 배구는 세트 득실.

사용법:
    python3 team_flow.py 글/313186 --sport football
"""
import datetime
import json
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api-gw.sports.naver.com/schedule/games"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.sports.naver.com/"}
WEEK = "월화수목금토일"
RECENT = 5


def game_info(game_id):
    r = requests.get(f"{API}/{game_id}", headers=H, timeout=20)
    return r.json().get("result", {}).get("game") if r.ok else None


def games(upper, category, fr, to):
    r = requests.get(API, params={"fields": "basic,categoryId,categoryName", "upperCategoryId": upper,
                                  "categoryId": category, "fromDate": fr, "toDate": to, "size": 500},
                     headers=H, timeout=20)
    return r.json().get("result", {}).get("games", []) if r.ok else []


def recent(upper, category, code, before):
    """그 팀의 최근 끝난 경기 (오래된 → 최근)."""
    found, end = [], before.date()
    for _ in range(12):  # 2주씩 거슬러 올라가며 (최대 약 6달)
        start = end - datetime.timedelta(days=13)
        for g in games(upper, category, start.isoformat(), end.isoformat()):
            if g.get("statusCode") != "RESULT" or code not in (g["homeTeamCode"], g["awayTeamCode"]):
                continue
            if datetime.datetime.fromisoformat(g["gameDateTime"]) >= before.replace(tzinfo=None):
                continue
            if g["gameId"] not in {x["gameId"] for x in found}:
                found.append(g)
        if len(found) >= RECENT:
            break
        end = start - datetime.timedelta(days=1)
    found = sorted(found, key=lambda g: g["gameDateTime"])[-RECENT:]
    out = []
    for g in found:
        home = g["homeTeamCode"] == code
        pf, pa = (g["homeTeamScore"], g["awayTeamScore"]) if home else (g["awayTeamScore"], g["homeTeamScore"])
        out.append({"date": g["gameDate"][5:].replace("-", "."), "pf": pf, "pa": pa,
                    "result": "승" if pf > pa else "패" if pf < pa else "무",
                    "opp": g["awayTeamName"] if home else g["homeTeamName"], "home": home})
    return out


def main():
    folder = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    sport = sys.argv[sys.argv.index("--sport") + 1] if "--sport" in sys.argv else "football"
    with open(os.path.join(folder, "post.json"), encoding="utf-8") as f:
        post = json.load(f)
    for i, m in enumerate(post.get("matches", []), 1):
        mp = os.path.join(folder, f"match_{i}.json")
        mk = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
        g = game_info(mk["naver_game_id"]) if mk.get("naver_game_id") else None
        if not g:
            print(f"  [팀 흐름 없음] 경기 {i}: 네이버 경기 정보를 찾지 못함")
            continue
        hc, ac = g["homeTeamCode"], g["awayTeamCode"]
        if mk.get("swapped"):
            hc, ac = ac, hc
        ko = datetime.datetime.fromisoformat(g["gameDateTime"])
        try:
            data = {
                "title": f"{m['home']} vs {m['away']}",
                "when": f"{ko.month}/{ko.day}({WEEK[ko.weekday()]}) {ko:%H:%M}" + (f" · {g['stadium']}" if g.get("stadium") else ""),
                "source": "네이버 스포츠 경기 결과",
                "home": {"name": m["home"], "logo": m.get("home_en", ""), "recent": recent(g["upperCategoryId"], g["categoryId"], hc, ko)},
                "away": {"name": m["away"], "logo": m.get("away_en", ""), "recent": recent(g["upperCategoryId"], g["categoryId"], ac, ko)},
            }
        except Exception as e:
            print(f"  [팀 흐름 실패] 경기 {i}: {e}")
            continue
        if sport == "volleyball":
            data["pf_label"], data["pa_label"] = "딴 세트", "내준 세트"
        if not (data["home"]["recent"] or data["away"]["recent"]):
            print(f"  [팀 흐름 없음] 경기 {i}: 최근 경기 기록이 없음")
            continue
        with open(os.path.join(folder, f"flow_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  {data['title']}: 최근 {len(data['home']['recent'])}·{len(data['away']['recent'])}경기 ({g.get('categoryName', '')})")


if __name__ == "__main__":
    main()
