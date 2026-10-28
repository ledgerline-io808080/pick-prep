#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save_state.py

서버(GitHub Actions)가 실행 끝에 처리 기록(done.json 등)을 저장소에 올린다. 그 사이에 다른 커밋(코드 수정 등)이
먼저 올라가 있어도 거부되지 않도록, 저장소의 최신 기록과 이번 실행 기록을 합친 뒤 올리고 실패하면 다시 시도한다.
(2026-10-17 버그: 기록 올리기가 거부돼 808번 글 기록이 사라져 중복 게시 위험이 생겼음)

합치는 방법: done.json·seen.json·team_ids.json·team_alias.json 은 키별로 합침(이번 실행 값 우선),
로고/ 폴더는 새 파일만 더함.

사용법 (워크플로 마지막 단계):  python3 save_state.py
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DICT_FILES = ["done.json", "seen.json", "team_ids.json", "team_alias.json"]
LIST_FILES = []


def sh(*args, check=True):
    r = subprocess.run(list(args), cwd=HERE, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {r.stderr.strip()}")
    return r


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    tmp = tempfile.mkdtemp()
    for name in DICT_FILES + LIST_FILES:
        if os.path.exists(os.path.join(HERE, name)):
            shutil.copy(os.path.join(HERE, name), os.path.join(tmp, name))
    logo_tmp = os.path.join(tmp, "로고")
    if os.path.isdir(os.path.join(HERE, "로고")):
        shutil.copytree(os.path.join(HERE, "로고"), logo_tmp)

    for attempt in range(1, 6):
        sh("git", "fetch", "-q", "origin", "main")
        sh("git", "reset", "-q", "--hard", "origin/main")  # 저장소 최신 상태 위에
        for name in DICT_FILES:
            mine = load(os.path.join(tmp, name), None)
            if mine is None:
                continue
            merged = load(os.path.join(HERE, name), {})
            if name == "done.json":  # 이미 '게시 완료'인 기록은 겹친 실행의 '중복 경기' 등으로 덮어쓰지 않음 (2026-10-19 버그: 1121·1123번 기록이 사라짐)
                mine = {k: v for k, v in mine.items()
                        if not (isinstance(merged.get(k), dict) and merged[k].get("status") == "전달 완료"
                                and not (isinstance(v, dict) and v.get("status") == "전달 완료"))}
            merged.update(mine)
            with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
        for name in LIST_FILES:
            mine = load(os.path.join(tmp, name), None)
            if mine is None:
                continue
            theirs = load(os.path.join(HERE, name), [])
            seen, merged = set(), []
            for x in theirs + mine:
                k = json.dumps(x, ensure_ascii=False, sort_keys=True)
                if k not in seen:
                    seen.add(k)
                    merged.append(x)
            with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
                json.dump(merged[-50:], f, ensure_ascii=False, indent=2)
        if os.path.isdir(logo_tmp):
            os.makedirs(os.path.join(HERE, "로고"), exist_ok=True)
            for fn in os.listdir(logo_tmp):
                dst = os.path.join(HERE, "로고", fn)
                if not os.path.exists(dst):
                    shutil.copy(os.path.join(logo_tmp, fn), dst)
        sh("git", "add", *[n for n in DICT_FILES + LIST_FILES if os.path.exists(os.path.join(HERE, n))], "로고", check=False)
        if sh("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
            print("처리 기록: 바뀐 것 없음")
            return
        sh("git", "commit", "-q", "-m", "처리 기록 갱신")
        if sh("git", "push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            print(f"처리 기록 저장 완료 ({attempt}번째 시도)")
            return
        print(f"처리 기록 올리기 거부됨 → 최신 기록과 다시 합쳐서 재시도 ({attempt}/5)")
        time.sleep(5 * attempt)
    raise SystemExit("처리 기록을 5번 시도했지만 올리지 못함")


if __name__ == "__main__":
    main()
