#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cafe_fetch.py

네이버 카페 '전문가집단' 게시판(예: 숏돌이)에서 분석글을 가져와 파일로 저장하는 시험용 스크립트.
맥에서 직접 실행한다 (Claude 브라우저는 네이버 접속이 막혀 있음).

사용법:

    1) 처음 한 번만: 로그인 + 게시판 등록
       python3 cafe_fetch.py --login

       -> 크롬 창이 뜨면 네이버에 직접 로그인 (보안문자 등 전부 직접)
       -> 로그인되면 자동 저장 후 창이 닫힘 (Enter 필요 없음)
       -> naver_session.json(로그인 상태), config.json(게시판 주소) 저장됨
          다른 게시판: python3 cafe_fetch.py --login --board <게시판 주소>
          비밀번호는 저장하지 않음

    2) 글 가져오기 (기본: 가장 최근 글 1개)
       python3 cafe_fetch.py
       python3 cafe_fetch.py --count 3          # 최근 3개
       python3 cafe_fetch.py --article 123456   # 글 번호 지정
       python3 cafe_fetch.py --show             # 브라우저 창을 띄워서 실행

       -> 글/<글번호>/article.json (제목·작성자·날짜·조회수·본문·이미지 목록)
       -> 글/<글번호>/img_01.jpg ... (본문 이미지)
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(HERE, "naver_session.json")
CONFIG_PATH = os.path.join(HERE, "config.json")
OUT_DIR = os.path.join(HERE, "글")

LOGIN_URL = "https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fcafe.naver.com"
API_URL = "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{club}/articles/{aid}?useCafeId=true&requestFrom=A"
ARTICLE_URL = "https://cafe.naver.com/ca-fe/cafes/{club}/articles/{aid}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
DELAY_SEC = 3  # 글 사이 간격 (계정 보호)
DEFAULT_BOARD = "https://cafe.naver.com/f-e/cafes/25720488/menus/96?viewType=L"  # 전문가집단 > 숏돌이


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 로그인

def is_logged_in(context):
    return any(c["name"] == "NID_AUT" for c in context.cookies("https://naver.com"))


def do_login(board_url):
    with sync_playwright() as p:
        # 메인 모니터 왼쪽 위에 창을 띄움
        browser = p.chromium.launch(headless=False, args=["--window-position=0,0"])
        context = browser.new_context(user_agent=UA)
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("=" * 60)
        print("새로 뜬 브라우저 창에서 네이버에 직접 로그인해주세요.")
        print("※ 로그인 화면의 '로그인 상태 유지'를 꼭 체크해주세요. (안 하면 금방 풀림)")
        print("로그인되면 자동으로 저장되고 창이 닫힙니다. (Enter 필요 없음)")
        print("=" * 60)
        ok = False
        for _ in range(900):  # 최대 30분 대기
            if is_logged_in(context):
                ok = True
                break
            page.wait_for_timeout(2000)
        if not ok:
            print("30분 동안 로그인이 확인되지 않아 종료합니다. 다시 실행해주세요.")
            browser.close()
            return
        page.wait_for_timeout(3000)  # 로그인 쿠키가 다 저장되도록 잠깐 대기
        context.storage_state(path=SESSION_PATH)
        os.chmod(SESSION_PATH, 0o600)

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"board_url": board_url, "saved_at": now()}, f, ensure_ascii=False, indent=2)

        print(f"로그인 상태 저장: {SESSION_PATH}")
        print(f"게시판 주소 저장: {board_url}")
        browser.close()


# ---------------------------------------------------------------- 목록

def find_articles(page):
    """게시판 화면(iframe 포함)에서 글 링크를 모아 [(club, aid, 제목)] 반환."""
    found = {}
    club_hint = None
    for frame in page.frames:
        m = re.search(r"(?:clubid=|/cafes/)(\d+)", frame.url)
        if m:
            club_hint = m.group(1)
        try:
            links = frame.eval_on_selector_all(
                "a[href]", "els => els.map(e => [e.href, (e.innerText || '').trim()])")
        except Exception:
            continue
        for href, text in links:
            am = re.search(r"(?:articleid=|/articles/)(\d+)", href)
            if not am:
                continue
            cm = re.search(r"(?:clubid=|/cafes/)(\d+)", href)
            club = cm.group(1) if cm else club_hint
            aid = am.group(1)
            if aid not in found or (text and not found[aid][2]):
                found[aid] = (club, aid, text)
    rows = [r for r in found.values() if r[0]]
    rows.sort(key=lambda r: int(r[1]), reverse=True)  # 글 번호가 클수록 최신
    return rows


# ---------------------------------------------------------------- 본문

def html_to_text(page, html):
    page.set_content(f"<div id='x'>{html}</div>")
    text = page.inner_text("#x")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_by_api(context, helper, club, aid):
    resp = context.request.get(
        API_URL.format(club=club, aid=aid),
        headers={"Referer": f"https://cafe.naver.com/ca-fe/cafes/{club}/articles/{aid}"})
    if resp.status != 200:
        raise RuntimeError(f"API 응답 {resp.status}")
    data = resp.json()
    art = data.get("result", {}).get("article") or {}
    html = art.get("contentHtml") or ""
    if not html:
        raise RuntimeError("API에 본문 없음 (권한 부족 가능)")
    write_ms = art.get("writeDate")
    return {
        "title": art.get("subject", ""),
        "author": (art.get("writer") or {}).get("nick", ""),
        "date": datetime.datetime.fromtimestamp(write_ms / 1000, datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M") if write_ms else "",  # 한국 시간 (서버는 UTC)
        "views": art.get("readCount"),
        "comments": art.get("commentCount"),
        "html": html,
        "text": html_to_text(helper, html),
        "source": "api",
    }


def fetch_by_page(page, club, aid):
    page.goto(ARTICLE_URL.format(club=club, aid=aid), wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    for frame in page.frames:
        body = frame.query_selector(".se-main-container, .ContentRenderer, #tbody, .article_viewer")
        if not body:
            continue

        def txt(sel):
            el = frame.query_selector(sel)
            return el.inner_text().strip() if el else ""

        return {
            "title": txt(".title_text"),
            "author": txt(".nickname"),
            "date": txt(".article_info .date"),
            "views": txt(".article_info .count"),
            "comments": None,
            "html": body.inner_html(),
            "text": re.sub(r"\n{3,}", "\n\n", body.inner_text()).strip(),
            "source": "page",
        }
    raise RuntimeError("글 본문을 찾지 못함 (권한 없음 또는 화면 구조 변경)")


def image_urls(html):
    urls = []
    for src in re.findall(r"<img[^>]+(?:data-src|src)=\"([^\"]+)\"", html):
        src = src.replace("&amp;", "&")
        if src.startswith("//"):
            src = "https:" + src
        if not src.startswith("http") or "sticker" in src or "emoticon" in src:
            continue
        if src not in urls:
            urls.append(src)
    return urls


def save_images(context, urls, folder, club, aid):
    saved = []
    for i, url in enumerate(urls, 1):
        try:
            r = context.request.get(url, headers={"Referer": ARTICLE_URL.format(club=club, aid=aid)})
            if r.status != 200:
                raise RuntimeError(f"응답 {r.status}")
            ctype = r.headers.get("content-type", "")
            ext = ".png" if "png" in ctype else ".gif" if "gif" in ctype else ".jpg"
            name = f"img_{i:02d}{ext}"
            with open(os.path.join(folder, name), "wb") as f:
                f.write(r.body())
            saved.append({"file": name, "url": url})
        except Exception as e:
            log(f"    [이미지 실패] {url}: {e}")
    return saved


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 실행

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="네이버 로그인 + 게시판 등록 (처음 한 번)")
    ap.add_argument("--count", type=int, default=1, help="가져올 최근 글 개수 (기본 1)")
    ap.add_argument("--article", help="특정 글 번호만 가져오기")
    ap.add_argument("--show", action="store_true", help="브라우저 창 띄워서 실행")
    ap.add_argument("--board", default=DEFAULT_BOARD, help="(--login 용) 게시판 목록 주소 (기본: 숏돌이)")
    ap.add_argument("--url", help="글을 가져올 게시판 주소 (없으면 config.json)")
    args = ap.parse_args()

    if args.login:
        do_login(args.board)
        return

    if not (os.path.exists(SESSION_PATH) and os.path.exists(CONFIG_PATH)):
        log("로그인 정보가 없습니다. 먼저 'python3 cafe_fetch.py --login'을 실행해주세요.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        board_url = args.url or json.load(f)["board_url"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show)
        context = browser.new_context(storage_state=SESSION_PATH, user_agent=UA)
        page = context.new_page()
        helper = context.new_page()

        log(f"[1/3] 게시판 여는 중... {board_url}")
        page.goto(board_url, wait_until="domcontentloaded")
        rows = []
        for _ in range(20):  # 목록이 다 뜰 때까지 최대 20초 대기
            page.wait_for_timeout(1000)
            rows = find_articles(page)
            if rows:
                break
        if "nidlogin" in page.url:
            log("로그인이 풀렸습니다. 'python3 cafe_fetch.py --login'으로 다시 로그인해주세요.")
            sys.exit(1)
        log(f"      글 링크 {len(rows)}개 발견")
        for club, aid, title in rows[:15]:
            log(f"      - {aid}  {title[:50]}")

        if args.article:
            club = rows[0][0] if rows else None
            targets = [(club, args.article)]
        else:
            targets = [(c, a) for c, a, _ in rows[:args.count]]
        if not targets or not targets[0][0]:
            page.screenshot(path=os.path.join(HERE, "debug_board.png"), full_page=True)
            log("글을 찾지 못했습니다. debug_board.png 화면을 확인해주세요.")
            sys.exit(1)

        log(f"[2/3] 글 {len(targets)}개 가져오는 중...")
        os.makedirs(OUT_DIR, exist_ok=True)
        for n, (club, aid) in enumerate(targets, 1):
            try:
                try:
                    art = fetch_by_api(context, helper, club, aid)
                except Exception as e:
                    log(f"      API 실패({e}) → 글 화면에서 읽기")
                    art = fetch_by_page(page, club, aid)

                folder = os.path.join(OUT_DIR, aid)
                os.makedirs(folder, exist_ok=True)
                imgs = save_images(context, image_urls(art["html"]), folder, club, aid)
                out = {
                    "club_id": club,
                    "article_id": aid,
                    "url": ARTICLE_URL.format(club=club, aid=aid),
                    "title": art["title"],
                    "author": art["author"],
                    "date": art["date"],
                    "views": art["views"],
                    "comments": art["comments"],
                    "text": art["text"],
                    "images": imgs,
                    "source": art["source"],
                    "fetched_at": now(),
                }
                with open(os.path.join(folder, "article.json"), "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)
                with open(os.path.join(folder, "content.html"), "w", encoding="utf-8") as f:
                    f.write(art["html"])
                log(f"      + [{aid}] {art['title']} (본문 {len(art['text'])}자, 이미지 {len(imgs)}장)")
            except Exception as e:
                log(f"      [실패] {aid}: {e}")
            if n < len(targets):
                time.sleep(DELAY_SEC)

        if is_logged_in(context):  # 로그인이 살아 있을 때만 갱신 (풀린 상태로 덮어쓰지 않음)
            context.storage_state(path=SESSION_PATH)
        else:
            log("  [경고] 네이버 로그인이 풀려 있습니다. 'python3 cafe_fetch.py --login'으로 다시 로그인해주세요.")
        log(f"[3/3] 완료 → {OUT_DIR}")
        browser.close()


if __name__ == "__main__":
    main()
