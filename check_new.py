#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_new.py

숏돌이 게시판에 아직 처리하지 않은 새 글이 있는지만 빠르게 확인한다 (브라우저 없이, 몇 초).
GitHub Actions 에서 새 글이 있을 때만 무거운 단계(설치·다시 쓰기·게시)를 돌리기 위한 용도.

사용법:
    python3 check_new.py           -> "new=true" 또는 "new=false" 출력 (GITHUB_OUTPUT 에도 기록)
"""
import json
import os
import re

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
COUNT = 3  # 최신 글 몇 개까지 볼지 (run_pick.py --count 와 같게)


def should_skip(v, done=None):  # run_prepare.py 와 같은 기준 (실패 글·묶음에서 나눈 실패 글은 다시)
    import sys
    sys.path.insert(0, HERE)
    from run_prepare import should_skip as f
    return f(v, done)


def main():
    with open(os.path.join(HERE, "boards.json"), encoding="utf-8") as f:
        boards = json.load(f)

    with open(os.path.join(HERE, "naver_session.json"), encoding="utf-8") as f:
        state = json.load(f)
    jar = requests.cookies.RequestsCookieJar()
    for c in state["cookies"]:
        jar.set(c["name"], c["value"], domain=c["domain"], path=c["path"])

    done = {}
    done_path = os.path.join(HERE, "done.json")
    if os.path.exists(done_path):
        with open(done_path, encoding="utf-8") as f:
            done = json.load(f)

    new = []
    new_keys = []  # 새 글이 있는 게시판 → run_prepare 가 이 게시판만 읽음 (서버 실행 시간 줄이기, 2026-10-25 )
    for b in boards:
        if b.get("paused"):
            continue
        if b.get("source") == "livescore":  # 라이브스코어는 네이버 로그인 없이 목록만
            import sys
            sys.path.insert(0, HERE)
            import livescore_fetch
            import datetime
            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
            days = {now.strftime("%Y-%m-%d"), (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")}
            latest = [f"ls{w}" for w, _, d in livescore_fetch.list_articles(b["board_url"], b["author"]) if d in days]
            b_new = [a for a in latest if not should_skip(done.get(a), done)]
            new += b_new
            if b_new:
                new_keys.append(b["key"])
            print(f"{b['name']}: 최신 {', '.join(latest) or '없음'} / 새 글: {', '.join(b_new) or '없음'}")
            continue
        club, menu = re.search(r"cafes/(\d+)/menus/(\d+)", b["board_url"]).groups()
        url = (f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{club}/menus/{menu}/articles"
               f"?page=1&pageSize=15&sortBy=TIME&viewType=L")
        r = requests.get(url, cookies=jar, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://cafe.naver.com/"})
        r.raise_for_status()
        items = [a["item"] for a in r.json()["result"]["articleList"] if a.get("type") == "ARTICLE"]
        latest = sorted((str(i["articleId"]) for i in items), key=int, reverse=True)[:COUNT]
        b_new = [a for a in latest if not should_skip(done.get(a), done)]
        new += b_new
        if b_new:
            new_keys.append(b["key"])
        print(f"{b['name']}: 최신 {', '.join(latest)} / 새 글: {', '.join(b_new) or '없음'}")

    with open(os.path.join(HERE, "new_boards.json"), "w", encoding="utf-8") as f:
        json.dump({"keys": new_keys}, f, ensure_ascii=False)
    print(f"new={'true' if new else 'false'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"new={'true' if new else 'false'}\n")


if __name__ == "__main__":
    main()
