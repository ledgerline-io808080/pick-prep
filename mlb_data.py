#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mlb_data.py

MLB 공식 기록(statsapi.mlb.com, 무료·키 없음)에서 경기마다 예고 선발 투수의 시즌 기록·최근 3경기와
두 팀 최근 맞대결 6경기를 가져온다 (야구 · 선발 매치업형, 2026-10-16).

- 원문 선발(post.json matches 의 home_pitcher_en / away_pitcher_en)과 공식 예고 선발의 성(last name)이 다르면
  pitcher_<n>.json 에 "mismatch" 를 적고 끝냄 → run_pick.py 가 게시하지 않음 (선발이 바뀐 경기일 수 있음)
- 결과: 글/<번호>/pitcher_<n>.json (선발 카드용), stats_<n>.json (상대 전적 차트용, h2h.py 결과를 덮어씀)

사용법:
    python3 mlb_data.py 글/312441
"""
import datetime
import json
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://statsapi.mlb.com/api/v1"
KST = datetime.timezone(datetime.timedelta(hours=9))
WEEK = "월화수목금토일"


def get(path, **params):
    r = requests.get(API + path, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def find_game(m, kickoff_kst):
    """경기 시간(한국) 앞뒤 하루에서 두 팀 이름이 맞는 경기."""
    ko = datetime.datetime.fromisoformat(kickoff_kst)
    us = (ko - datetime.timedelta(hours=13)).date()
    s = get("/schedule", sportId=1, startDate=(us - datetime.timedelta(days=1)).isoformat(),
            endDate=(us + datetime.timedelta(days=1)).isoformat(), hydrate="probablePitcher")
    best = None
    for d in s.get("dates", []):
        for g in d["games"]:
            names = {side: g["teams"][side]["team"]["name"] for side in ("home", "away")}
            hit = sum(any(w in norm(names[side]) for w in [norm(x) for x in m[f"{key}_en"].split() if len(x) > 3])
                      for side, key in (("home", "home"), ("away", "away")))
            gt = datetime.datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00"))
            gap = abs((gt - ko).total_seconds())
            if hit == 2 and (best is None or gap < best[0]):
                best = (gap, g)
    return best[1] if best else None


def pitcher(pid, before):
    """시즌(정규) 기록 + 정규·포스트시즌 합쳐 그 경기 전 최근 3경기."""
    season = before[:4]
    out = {"season": {}, "recent": []}
    logs = []
    for gt in ("R", "P"):
        r = get(f"/people/{pid}/stats", stats="season,gameLog", group="pitching", season=season, gameType=gt)
        for st in r.get("stats", []):
            if st["type"]["displayName"] == "season" and gt == "R" and st["splits"]:
                s = st["splits"][0]["stat"]
                out["season"] = {"w": s.get("wins"), "l": s.get("losses"), "era": s.get("era"),
                                 "ip": s.get("inningsPitched"), "so": s.get("strikeOuts"), "whip": s.get("whip")}
            if st["type"]["displayName"] == "gameLog":
                for x in st["splits"]:
                    if x["date"] < before:
                        logs.append({"date": x["date"], "opp": x["opponent"]["name"], "ip": x["stat"]["inningsPitched"],
                                     "er": x["stat"]["earnedRuns"], "so": x["stat"]["strikeOuts"],
                                     "post": gt == "P"})
    out["recent"] = sorted(logs, key=lambda x: x["date"], reverse=True)[:3]
    return out


def h2h(home_id, away_id, before, names):
    rows, dates = [], []
    for y in range(int(before[:4]), int(before[:4]) - 4, -1):  # 시즌별로 (한 번에 여러 해를 물으면 일부만 옴)
        s = get("/schedule", sportId=1, teamId=home_id, opponentId=away_id, season=y, gameType="R,F,D,L,W")
        dates += s.get("dates", [])
        if sum(len(d["games"]) for d in dates) >= 12:
            break
    for d in dates:
        for g in d["games"]:
            if g["status"].get("abstractGameState") != "Final" or g["officialDate"] >= before:
                continue
            t = g["teams"]
            if t["home"].get("score") is None:
                continue
            rows.append({"date": g["officialDate"], "home_id": t["home"]["team"]["id"],
                         "hs": t["home"]["score"], "as": t["away"]["score"]})
    rows = sorted(rows, key=lambda x: x["date"], reverse=True)[:6]
    w = l = 0
    matches = []
    for x in rows:
        home_is_ours = x["home_id"] == home_id
        mine, theirs = (x["hs"], x["as"]) if home_is_ours else (x["as"], x["hs"])
        res = "승" if mine > theirs else "패"
        w, l = w + (res == "승"), l + (res == "패")
        matches.append({"date": x["date"], "home": names[0] if home_is_ours else names[1],
                        "away": names[1] if home_is_ours else names[0],
                        "score": f"{x['hs']} - {x['as']}", "result": res})
    return w, l, matches


def main():
    folder = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    with open(os.path.join(folder, "post.json"), encoding="utf-8") as f:
        post = json.load(f)
    failed = 0
    for i, m in enumerate(post.get("matches", []), 1):
        mp = os.path.join(folder, f"match_{i}.json")
        if not os.path.exists(mp):
            print(f"  [실패] 경기 {i}: 경기 시간 정보(match_{i}.json)가 없음")
            failed += 1
            continue
        with open(mp, encoding="utf-8") as f:
            mk = json.load(f)
        try:
            g = find_game(m, mk["kickoff_kst"])
            if not g:
                raise RuntimeError("MLB 공식 일정에서 경기를 찾지 못함")
            before = g["officialDate"]
            card = {"title": g.get("seriesDescription") or "", "game": g.get("description") or "",
                    "label": mk.get("label", ""), "source": "MLB 공식 기록 (statsapi.mlb.com)"}
            mismatch = []
            for side, key in (("home", "home"), ("away", "away")):
                pp = g["teams"][side].get("probablePitcher")
                want = m.get(f"{key}_pitcher_en", "")
                info = {"team": m[key], "name_ko": m.get(f"{key}_pitcher", ""), "name_en": pp["fullName"] if pp else ""}
                if pp:
                    info.update(pitcher(pp["id"], before))
                if want and pp and norm(want.split()[-1]) != norm(pp["lastName"] if "lastName" in pp else pp["fullName"].split()[-1]):
                    mismatch.append(f"{m[key]} 원문 {want} / 공식 {pp['fullName']}")
                if not want and info["name_ko"]:  # 원문 선발을 영어로 못 옮겼으면 대조 불가 → 게시 안 함
                    mismatch.append(f"{m[key]} 원문 선발 {info['name_ko']} 영어 이름 없음(대조 불가)")
                if want and not pp:
                    mismatch.append(f"{m[key]} 공식 예고 선발 없음")
                card[key] = info
            if mismatch:
                card["mismatch"] = mismatch
                print(f"  [선발 불일치] {', '.join(mismatch)}")
            hid, aid = g["teams"]["home"]["team"]["id"], g["teams"]["away"]["team"]["id"]
            w, l, rows = h2h(hid, aid, before, (m["home"], m["away"]))
            stats = {"league": f"{m['home']} vs {m['away']} · {mk.get('label', '')}",
                     "basis": f"최근 맞대결 {len(rows)}경기 · 출처 MLB 공식 기록" if rows else "최근 맞대결 기록 없음 · 출처 MLB 공식 기록",
                     "home": {"name": m["home"], "logo": m["home_en"]}, "away": {"name": m["away"], "logo": m["away_en"]},
                     "h2h": {"home_w": w, "d": 0, "away_w": l, "label": f"{m['home']} 기준 {w}승 {l}패"} if rows else None,
                     "h2h_matches": rows}
            if len(post["matches"]) > 1 and mk.get("league_ko"):
                stats["league"] = f"{mk['league_ko']} · {stats['league']}"
            with open(os.path.join(folder, f"pitcher_{i}.json"), "w", encoding="utf-8") as f:
                json.dump(card, f, ensure_ascii=False, indent=2)
            with open(os.path.join(folder, f"stats_{i}.json"), "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            hp, ap = card["home"], card["away"]
            print(f"  {m['home']} vs {m['away']}: {card['game']} / 선발 {hp['name_en']} vs {ap['name_en']} / 맞대결 {w}승 {l}패")
        except Exception as e:
            print(f"  [실패] {m['home']} vs {m['away']}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
