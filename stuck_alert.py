#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stuck_alert.py

글 만들기가 여러 번 다시 시도해도 계속 막힌 글(코드 버그 의심)이 있으면 알림 내용을 queue/_alert.json 에 남긴다.
공개 저장소라 사람 이름·연락처는 적지 않고, 비공개 쪽 실행이 이 파일을 읽어 GitHub 이슈(메일 알림)를 연다 (2026-10-28 공개/비공개 분리).
같은 글은 한 번만 알림 (done.json 에 alerted 표시).

대상: 오늘·어제(한국 날짜) 기록 중 재시도 대상 실패 또는 '종목 불일치'이고 2번 이상 시도한 글.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KST = datetime.timezone(datetime.timedelta(hours=9))
FAIL = {"대조 불일치", "다시 쓰기 실패", "경기 확인 실패 - 게시 안 함", "가져오기 실패 - 건너뜀", "종목 불일치 - 게시 안 함"}


def main():
    with open(os.path.join(HERE, "done.json"), encoding="utf-8") as f:
        done = json.load(f)
    now = datetime.datetime.now(KST)
    days = (now.strftime("%Y-%m-%d"), (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
    rows = []
    for aid, v in done.items():
        if v.get("alerted") or not str(v.get("at", "")).startswith(days):
            continue
        if v.get("status") in FAIL and v.get("tries", 1) >= 2:
            v["alerted"] = now.strftime("%Y-%m-%d %H:%M")
            rows.append({"aid": aid, "board": v.get("board", ""), "status": v.get("status"), "tries": v.get("tries"),
                         "title": v.get("title", "")})
    with open(os.path.join(HERE, "done.json"), "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(HERE, "queue"), exist_ok=True)
    if rows:
        with open(os.path.join(HERE, "queue", "_alert.json"), "w", encoding="utf-8") as f:
            json.dump({"at": now.strftime("%Y-%m-%d %H:%M"), "rows": rows}, f, ensure_ascii=False, indent=2)
    print(f"계속 막힌 글: {len(rows)}개")


if __name__ == "__main__":
    main()
