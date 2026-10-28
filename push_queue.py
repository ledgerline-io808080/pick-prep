#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_queue.py

run_prepare.py 가 queue/ 에 넣은 완성된 글(글 번호별 폴더: post.json·이미지·meta.json)과 알림(_alert.json)을
이 저장소의 'queue' 가지에 올린다. 비공개 쪽이 이 가지를 읽어 등록한다 (2026-10-28 공개/비공개 분리).
3일 지난 글 폴더는 가지에서 지움. 올릴 새 내용이 있으면 GITHUB_OUTPUT 에 staged=true.

사용법 (워크플로 마지막 단계):  python3 push_queue.py
"""
import datetime
import json
import os
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "queue")
TREE = os.path.join(HERE, "_queue_tree")
KST = datetime.timezone(datetime.timedelta(hours=9))


def sh(*args, cwd=HERE, check=True):
    r = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {r.stderr.strip()}")
    return r


def prune(tree):
    now = datetime.datetime.now(KST)
    for name in os.listdir(tree):
        p = os.path.join(tree, name)
        if name == ".git" or not os.path.isdir(p):
            continue
        try:
            at = json.load(open(os.path.join(p, "meta.json"), encoding="utf-8"))["staged_at"]
            age = now - datetime.datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        except Exception:
            age = datetime.timedelta(days=99)
        if age > datetime.timedelta(days=3):
            shutil.rmtree(p)


def main():
    items = [n for n in os.listdir(SRC)] if os.path.isdir(SRC) else []
    out = os.environ.get("GITHUB_OUTPUT")
    if not items:
        print("전달할 새 글 없음")
        if out:
            open(out, "a").write("staged=false\n")
        return
    for attempt in range(1, 6):
        shutil.rmtree(TREE, ignore_errors=True)
        sh("git", "worktree", "prune", check=False)
        if sh("git", "fetch", "-q", "origin", "queue", check=False).returncode == 0:
            sh("git", "worktree", "add", "-f", "--detach", TREE, "origin/queue")
        else:  # 처음이면 빈 가지 만들기
            sh("git", "worktree", "add", "-f", "--detach", TREE, "HEAD")
            sh("git", "checkout", "-q", "--orphan", "queue", cwd=TREE)
            sh("git", "rm", "-rfq", ".", cwd=TREE, check=False)
        for n in items:
            dst = os.path.join(TREE, n)
            if os.path.isdir(os.path.join(SRC, n)):
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(os.path.join(SRC, n), dst)
            else:
                shutil.copy(os.path.join(SRC, n), dst)
        prune(TREE)
        sh("git", "add", "-A", cwd=TREE)
        if sh("git", "diff", "--cached", "--quiet", cwd=TREE, check=False).returncode == 0:
            print("전달 가지: 바뀐 것 없음")
            break
        sh("git", "-c", "user.name=builder", "-c", "user.email=builder@users.noreply.github.com",
           "commit", "-q", "-m", "전달", cwd=TREE)
        if sh("git", "push", "-q", "origin", "HEAD:queue", cwd=TREE, check=False).returncode == 0:
            print(f"전달 가지에 올림 ({attempt}번째 시도): {', '.join(sorted(items))}")
            if out:
                open(out, "a").write("staged=true\n")
            break
        print(f"전달 가지 올리기 거부됨 → 다시 ({attempt}/5)")
        time.sleep(4 * attempt)
    else:
        raise SystemExit("전달 가지를 5번 시도했지만 올리지 못함")
    shutil.rmtree(TREE, ignore_errors=True)
    sh("git", "worktree", "prune", check=False)


if __name__ == "__main__":
    main()
