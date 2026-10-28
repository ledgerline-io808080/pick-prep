#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
livescore_fetch.py

라이브스코어(livescore.co.kr) 모바일 게시판에서 특정 글쓴이의 분석 글을 가져온다 (배구 · 픽타벅스, 2026-10-16).
PC 버전은 Cloudflare 보안 확인이 있어 모바일 버전만 쓴다 (로그인 필요 없음).
본문이 글자 없이 이미지뿐이라, 이미지를 받아 Claude 로 두 번 따로 읽고(글자 옮기기) 두 결과의
숫자·이름이 같을 때만 article.json 의 text 로 쓴다. 다르면 그 글은 건너뜀 (데이터 원문 그대로 원칙).

사용법:
    python3 livescore_fetch.py --url "<게시판 주소>" --author 픽타벅스 --count 3
    python3 livescore_fetch.py --url "<게시판 주소>" --author 픽타벅스 --article 241158
    -> 글/ls<글번호>/article.json, src_1.jpg ...  (출력의 "+ [ls241158] 제목" 줄을 run_pick.py 가 읽음)
"""
import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "글")
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
      "Referer": "https://livescore.co.kr/mobile/"}
SKIP_WORDS = ("EVENT", "이벤트", "공지", "적중 내역", "결과")  # 분석 글이 아닌 것


def log(msg):
    print(msg, flush=True)


def get(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    if "Just a moment" in r.text[:2000]:
        raise RuntimeError("Cloudflare 보안 확인 화면이 떠서 가져올 수 없음")
    return r.text


PICKSTER_ICON = "25_ICON_01_016_"  # 라이브스코어 픽스터 등급 배지 (적중PD·부스터픽대통령·픽타벅스 등)
MAX_GAMES = 2  # 대체 글은 경기 2개 이하만 (수십 경기 묶음 글 제외)


def list_articles(board_url, author):
    """게시판 1페이지 분석 글 [(글번호, 제목, 날짜)] (최신순).
    author 가 "*" 이면 픽스터 배지가 있는 아무 글쓴이 (대체 글용, 위에서부터 = 최신순)."""
    t = get(board_url)
    out = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", t, re.S):
        m = re.search(r'wr_id=(\d+)', li)
        if not m or "bo_table=notice" in li:
            continue
        name = re.search(r'class="sv_guest\s*">(.*?)</span>', li)
        subj = re.search(r"<span>(.*?)</span>", li, re.S)
        date = re.search(r'class="td_date">([\d-]+)<', li)
        if not (name and subj and date):
            continue
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", subj.group(1)))).strip()
        if any(w in title for w in SKIP_WORDS) or "정보" in title:
            continue
        if "bo_table=soccer" in board_url:  # 축구: 제목이 비빅리그뿐이면 읽지 않음 (이미지 읽는 시간 줄이기, 2026-10-25 )
            sys.path.insert(0, HERE)
            from big_league import skip_by_title
            if skip_by_title(title):
                continue
        who = html.unescape(name.group(1)).strip()
        many = False  # 묶음 글도 가져옴 → run_pick 이 경기별로 나눠 올림 (2026-10-17 )
        if author == "*":
            if PICKSTER_ICON not in li or many:
                continue
        elif "," in author:  # 정해진 픽스터 여러 명 (2026-10-17 적중PD·픽타벅스·부스터픽대통령)
            if who not in [a.strip() for a in author.split(",")] or many:
                continue
        elif who != author or "분석" not in title:
            continue
        out.append((m.group(1), title, date.group(1)))
    return sorted(set(out), key=lambda x: int(x[0]), reverse=True)


def article_images(board_url, wr_id):
    t = get(re.sub(r"&wr_id=\d+", "", board_url) + f"&wr_id={wr_id}")
    m = re.search(r'<div id="bo_v_con">(.*?)<!-- } 본문 내용 끝', t, re.S)
    if not m:
        raise RuntimeError("본문을 찾지 못함")
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return re.findall(r'<img[^>]+src="(https://img\.livescore\.co\.kr/[^"]+)"', m.group(1)), text


TRANSCRIBE = """\
아래 이미지 파일들을 Read 도구로 하나씩 열어 보고 답하라: {files}

1) 각 이미지가 경기 분석(팀 이름·전적·분석 문장·추천 픽이 있는 것)인지, 홍보·광고(문의·오픈채팅·기프티콘·로고만 있는 것)인지 가른다.
2) 분석 이미지에 적힌 글자를 보이는 그대로 옮겨 적는다. 고치거나 요약하거나 덧붙이지 않는다. 숫자·팀명·선수명·전적·추천 문구는 글자 그대로.
   위에서 아래, 왼쪽에서 오른쪽 순서. 홈/원정 칸이 나뉘어 있으면 "HOME : 팀명", "AWAY : 팀명" 같은 머리 글자도 그대로 적는다.
3) 큰 글씨로 강조된 추천 픽(예: "현대건설 플핸 승")은 맨 끝에 "추천: <그대로>" 한 줄로 한 번 더 적는다.

출력은 JSON 하나만 (설명·코드블록 표시 없이):
{{"analysis_files": ["분석 이미지 파일 이름"], "ad_files": ["광고 이미지 파일 이름"], "text": "옮겨 적은 글자 전부 (줄바꿈은 \\n)"}}
"""


def claude_bin():
    sys.path.insert(0, HERE)
    from rewrite import claude_bin as cb
    return cb()


def transcribe(folder, files):
    rel = ", ".join(os.path.relpath(os.path.join(folder, f), HERE) for f in files)
    r = subprocess.run([claude_bin(), "-p", TRANSCRIBE.format(files=rel), "--allowedTools", "Read"],
                       capture_output=True, text=True, timeout=600, cwd=HERE)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if r.returncode != 0 or not m:
        raise RuntimeError(f"이미지 읽기 실패: {(r.stderr or r.stdout).strip()[:200]}")
    return json.loads(m.group(0))


def strip_files(text):
    """읽은 글에 섞여 들어온 이미지 파일 이름(src_4.png 등)은 뺌 (2026-10-17 버그: 파일 이름 숫자 때문에 대조 실패)."""
    return re.sub(r"\b(?:[\w./-]*/)?src_\d+\.(?:png|jpe?g|gif|webp)\b", "", text, flags=re.I)


def tokens(text):
    """두 번 읽은 결과 비교용: 숫자 표현 + 한글·영문 낱말."""
    t = re.sub(r"\s+", " ", strip_files(text))
    return set(re.findall(r"\d+(?:[.:-]\d+)*", t)), set(re.findall(r"[가-힣A-Za-z]{2,}", t))


def fetch_one(board_url, wr_id, title, date):
    aid = f"ls{wr_id}"
    folder = os.path.join(OUT_DIR, aid)
    os.makedirs(folder, exist_ok=True)
    urls, plain = article_images(board_url, wr_id)
    files = []
    for i, u in enumerate(urls, 1):
        ext = os.path.splitext(u)[1].lower() or ".jpg"
        name = f"src_{i}{ext}"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(requests.get(u, headers=UA, timeout=30).content)
        files.append(name)
    if not files and not plain:
        raise RuntimeError("본문에 글도 이미지도 없음")

    text = plain
    if files:
        def same(x, y):  # 숫자는 하나라도 다르면 안 됨, 낱말은 어미 차이 정도만
            (nx, wx), (ny, wy) = tokens(x["text"]), tokens(y["text"])
            return not (nx ^ ny) and len(wx ^ wy) <= max(8, len(wx | wy) // 10), (nx ^ ny, wx ^ wy)

        # 두 번 따로 읽어 대조 — 동시에 읽어서 시간을 절반으로 (2026-10-25 서버 실행 시간 줄이기)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            f1, f2 = ex.submit(transcribe, folder, files), ex.submit(transcribe, folder, files)
            reads = [f1.result(), f2.result()]
        ok, (dn, dw) = same(reads[0], reads[1])
        a = reads[0]
        if not ok:  # 다르면 한 번 더 읽어서 세 번 중 두 번이 같으면 그 결과 (2026-10-17: 긴 묶음 글이 계속 막힘)
            reads.append(transcribe(folder, files))
            pair = next(((i, j) for i, j in ((0, 2), (1, 2)) if same(reads[i], reads[j])[0]), None)
            if not pair:
                raise RuntimeError(f"이미지를 세 번 읽어도 두 번 같은 결과가 없음 (숫자 {sorted(dn)[:8]}, 낱말 {sorted(dw)[:8]})")
            a = reads[pair[0]]
            print(f"      (두 번 읽은 결과가 달라 한 번 더 읽음 → {pair[0] + 1}번째·{pair[1] + 1}번째 결과가 같아서 사용)")
        text = (plain + "\n" if plain else "") + strip_files(a["text"])
        ads = a.get("ad_files", [])
    else:
        ads = []

    art = {"source": "livescore", "article_id": aid, "url": f"{board_url}&wr_id={wr_id}", "title": title,
           "date": f"{date} 00:00", "text": text, "images": files, "ad_images": ads,
           "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(folder, "article.json"), "w", encoding="utf-8") as f:
        json.dump(art, f, ensure_ascii=False, indent=2)
    return aid, len(text), len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--article")
    ap.add_argument("--list-only", action="store_true", help="목록만 (check_new.py 용)")
    args = ap.parse_args()

    log(f"[1/3] 게시판 여는 중... {args.url}")
    items = list_articles(args.url, args.author)
    log(f"      {args.author} 분석 글 {len(items)}개")
    for wr, t, d in items[:15]:
        log(f"      - ls{wr}  {d}  {t}")
    if args.list_only:
        return
    pick = [x for x in items if x[0] == args.article] if args.article else items[:args.count]
    if args.article and not pick:
        pick = [(args.article, f"livescore {args.article}", datetime.date.today().isoformat())]
    log(f"[2/3] 글 {len(pick)}개 가져오는 중... (이미지는 두 번 읽어 대조)")
    for wr, t, d in pick:
        try:
            aid, n, k = fetch_one(args.url, wr, t, d)
            log(f"      + [{aid}] {t} (본문 {n}자, 이미지 {k}장)")
        except Exception as e:
            log(f"      ! [ls{wr}] {t}: {e}")
    log(f"[3/3] 완료 → {OUT_DIR}")


if __name__ == "__main__":
    main()
