#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kbl_data.py

KBL 공식 사이트(kbl.or.kr)에서 이번 시즌 경기 결과·경기 시간·구단 엠블럼을 가져와
글 폴더에 kbl_<n>.json 을 만든다 (두 번째 아이디 차트용). 점수는 공식 기록 그대로.

사용법:
    python3 kbl_data.py 글/312962      (post.json 의 matches 사용)
    -> 글/312962/kbl_1.json, 로고/<영어팀명>.png (공식 엠블럼으로 교체)
"""
import datetime
import json
import os
import sys

import requests
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(HERE, "로고")
SITE = "https://www.kbl.or.kr"
API = "https://api.kbl.or.kr"
WEEK = "월화수목금토일"
RECENT = 6  # 팀별 최근 경기 수


def load_site():
    """공식 일정 페이지를 열어 사이트가 쓰는 요청 정보·팀 목록을 받는다."""
    info = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()

        def on(r):
            if "api.kbl.or.kr/match/list?" in r.url and "headers" not in info:
                info["headers"] = {k: v for k, v in r.request.headers.items()
                                   if not k.startswith(":") and k.lower() not in ("content-length",)}
            if "common/teamList" in r.url:
                try:
                    info["teams"] = r.json()
                except Exception:
                    pass
        pg.on("response", on)
        pg.goto(SITE + "/match/schedule", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(1500)
        info["page"] = (b, pg, p)
        logos = {}
        for t in info.get("teams", []):
            cls = t.get("teamLogoClass")
            if cls and cls != "kbl":
                logos[t["teamCode"]] = f"{SITE}/assets/img/logo/logo-{cls}.svg"
        info["logos"] = logos
        # 엠블럼 svg → png (브라우저로 그려서 저장)
        info["logo_png"] = {}
        for code, url in logos.items():
            try:
                pg.set_content(f'<html><body style="margin:0;background:transparent">'
                               f'<img id="l" src="{url}" style="width:400px;height:400px;object-fit:contain"></body></html>')
                pg.wait_for_function("document.getElementById('l').complete", timeout=10000)
                info["logo_png"][code] = pg.locator("#l").screenshot(omit_background=True)
            except Exception:
                pass
        b.close()
    return info


def games(headers, start, end):
    r = requests.get(f"{API}/match/list", params={"fromDate": start, "toDate": end, "tcodeList": "all"},
                     headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def find_team(name, teams):
    """본문의 짧은 팀명(소노, 모비스)으로 공식 팀 찾기."""
    key = name.replace(" ", "")
    for t in teams:
        for field in ("teamName", "teamNameFull"):
            if t.get("teamCode") != "XX" and (key in (t.get(field) or "").replace(" ", "")):
                return t
    return None


def main():
    folder = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    with open(os.path.join(folder, "post.json"), encoding="utf-8") as f:
        post = json.load(f)

    info = load_site()
    teams = info.get("teams", [])
    today = datetime.date.today()
    rows = games(info["headers"], (today - datetime.timedelta(days=75)).strftime("%Y%m%d"),
                 (today + datetime.timedelta(days=3)).strftime("%Y%m%d"))
    os.makedirs(LOGO_DIR, exist_ok=True)

    for i, m in enumerate(post.get("matches", []), 1):
        th, ta = find_team(m["home"], teams), find_team(m["away"], teams)
        if not th or not ta:
            print(f"  [KBL 팀 못 찾음] {m['home']} / {m['away']}")
            continue
        # 공식 엠블럼으로 로고 교체 (배너·차트가 이 파일을 씀)
        for t, en in ((th, m["home_en"]), (ta, m["away_en"])):
            png = info["logo_png"].get(t["teamCode"])
            if png:
                with open(os.path.join(LOGO_DIR, f"{en}.png"), "wb") as f:
                    f.write(png)

        def recent(code):
            out = []
            for g in sorted(rows, key=lambda g: (g["gameDate"], g["gameStart"])):
                if not g.get("isEnded") or code not in (g["tcodeH"], g["tcodeA"]):
                    continue
                if g.get("seasonCategory") and g["seasonCategory"] != "R":
                    continue  # 정규시즌만 (컵대회·시범경기 제외)
                home = g["tcodeH"] == code
                pf, pa = (g["scoreH"], g["scoreA"]) if home else (g["scoreA"], g["scoreH"])
                opp = g["tnameA"] if home else g["tnameH"]
                out.append({"date": f"{g['gameDate'][4:6]}.{g['gameDate'][6:]}", "pf": pf, "pa": pa,
                            "result": "승" if pf > pa else "패", "opp": opp.split(" ")[-1], "home": home})
            return out[-RECENT:]

        today_game = next((g for g in rows if not g.get("isEnded")
                           and {g["tcodeH"], g["tcodeA"]} == {th["teamCode"], ta["teamCode"]}), None)
        label = ""
        if today_game:
            d = datetime.datetime.strptime(today_game["gameDate"] + today_game["gameStart"], "%Y%m%d%H%M")
            label = f"{d.month}/{d.day}({WEEK[d.weekday()]}) {d:%H:%M} · {today_game.get('stadiumname', '')}"
        season_h2h = [g for g in rows if g.get("isEnded")
                      and {g["tcodeH"], g["tcodeA"]} == {th["teamCode"], ta["teamCode"]}]

        out = {
            "title": f"{m['home']} vs {m['away']}",
            "when": label,
            "home": {"name": m["home"], "logo": m["home_en"], "recent": recent(th["teamCode"])},
            "away": {"name": m["away"], "logo": m["away_en"], "recent": recent(ta["teamCode"])},
            "season_h2h": len(season_h2h),
            "source": "KBL 공식 기록",
        }
        with open(os.path.join(folder, f"kbl_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"  {out['title']}: 최근 {len(out['home']['recent'])}·{len(out['away']['recent'])}경기 / {label or '경기 시간 못 찾음'}")


if __name__ == "__main__":
    main()
