#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pick.py

픽스터 글 한 번에 만들기: 가져오기 → 다시 쓰기 → 데이터 대조 → 로고 배너 → 상대 전적 차트 → 게시 미리보기

사용법:
    python3 run_pick.py                    # 숏돌이 최신 글 1개, 미리보기까지 (등록 안 함)
    python3 run_pick.py --count 3          # 최신 글 3개 (이미 처리한 글은 건너뜀)
    python3 run_pick.py --article 312942   # 특정 글
    python3 run_pick.py --submit           # 미리보기 대신 실제 등록
    python3 run_pick.py --article 312735 --reuse   # 다시 쓰기는 이전 결과 재사용(대조 통과한 경우)

데이터 대조에서 하나라도 원문과 다르면 그 글은 배너·게시 단계로 넘어가지 않는다.
처리 기록: done.json (글 번호별 결과)
"""
import argparse
from big_league import is_big_match, star_game
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DONE_PATH = os.path.join(HERE, "done.json")
KST = datetime.timezone(datetime.timedelta(hours=9))  # 기록 시각은 한국 시간 (서버는 UTC)


def run(args, label):
    print(f"\n▶ {label}")
    try:  # 한 단계가 멈춰서 실행 전체가 3시간 걸리는 일 방지 (2026-10-27)
        r = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired:
        print(f"  [시간 초과 1500초] {args[:2]} → 실패 처리")
        return 1, "시간 초과"
    out = (r.stdout + r.stderr).rstrip()
    if out:
        print(out)
    return r.returncode, out


# 실패한 글 자동 재실행 (2026-10-17 버그 나면 다시 돌려서 누락 없이) — 경기 시작 전이면 다음 실행 때 다시, 최대 3번
RETRY = {"대조 불일치", "다시 쓰기 실패", "경기 확인 실패 - 게시 안 함", "게시 실패", "가져오기 실패 - 건너뜀", "중복 경기 일부 - 다시 나눔"}
MAX_TRIES = 24  # 경기 시작 전까지 계속 다시 (2026-10-17 버그 나도 될 때까지). 경기 시작 시각이 지났으면 그때 멈춤, 오늘·어제 글만 봄


def should_skip(v, done=None):
    """처리 기록을 보고 이번 실행에서 건너뛸지. 미리보기만 한 글·재시도할 실패 글은 다시 처리."""
    if not v:
        return False
    if done is not None and v.get("subs") and v.get("status", "").startswith("묶음 나눔"):
        # 나눈 글 중 다시 할 글이 있으면 묶음을 다시 나눠서 처리 (2026-10-18 버그: 나눈 글 실패가 재시도 안 됨)
        return v.get("resplits", 0) >= MAX_TRIES or all(should_skip(done.get(s)) for s in v["subs"])
    if v.get("status") in ("미리보기", "미리보기 실패"):
        return False
    if v.get("status") == "경기 확인 실패 - 게시 안 함" and v.get("tries", 1) >= 8:
        return True  # 경기 시간을 8번(약 4시간) 못 찾으면 그만 (2026-10-29: 21번까지 다시 쓰기를 반복해 Claude 사용량 낭비)
    if v.get("status") in RETRY and v.get("tries", 1) < MAX_TRIES:
        ko = v.get("kickoff_kst")
        if ko and datetime.datetime.fromisoformat(ko) <= datetime.datetime.now(KST):
            return True  # 경기가 이미 시작함 → 더 시도해도 못 올림
        return False
    return True


SEEN_PATH = os.path.join(HERE, "seen.json")


def load_seen():
    if os.path.exists(SEEN_PATH):
        with open(SEEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    keep = dict(sorted(seen.items(), key=lambda x: x[1])[-500:])
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)


def load_done():
    if os.path.exists(DONE_PATH):
        with open(DONE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_done(done):
    with open(DONE_PATH, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=2)


# 종목 ↔ 네이버 스포츠 종목 (2026-10-16 종목이 틀리면 사고). 글쓴이 계정 확인은 비공개 쪽이 함
SPORT_NAVER = {"football": {"wfootball", "kfootball"}, "basketball": {"kbasketball", "wbasketball"},
               "baseball": {"kbaseball", "wbaseball"}, "volleyball": {"kvolleyball", "wvolleyball"}}


# 네이버에 없는 리그는 API-Football (나라, 리그명) → 한글 (2026-10-17 제목에 리그명)
LEAGUE_KO = {("China", "Super League"): "중국 슈퍼리그", ("Germany", "2. Bundesliga"): "2.분데스리가",
             ("England", "Championship"): "잉글랜드 챔피언십", ("England", "Premier League"): "프리미어리그",
             ("England", "League One"): "잉글랜드 리그원", ("Japan", "J1 League"): "J1리그", ("Japan", "J2 League"): "J2리그",
             ("South-Korea", "K League 1"): "K리그1", ("South-Korea", "K League 2"): "K리그2",
             ("Australia", "A-League"): "A리그", ("Netherlands", "Eredivisie"): "에레디비시", ("Spain", "La Liga"): "라리가",
             ("Italy", "Serie A"): "세리에 A", ("France", "Ligue 1"): "리그 1", ("Germany", "Bundesliga"): "분데스리가",
             ("Portugal", "Primeira Liga"): "프리메이라리가", ("Belgium", "Jupiler Pro League"): "벨기에 프로리그",
             ("Turkey", "Süper Lig"): "튀르키예 쉬페르리그", ("Scotland", "Premiership"): "스코틀랜드 프리미어십",
             ("USA", "Major League Soccer"): "MLS", ("Saudi-Arabia", "Pro League"): "사우디 프로리그"}


def official_leagues(folder, post):
    """경기별 공식 리그명 (네이버 한글명 → 없으면 API-Football 리그명 한글로)."""
    out = []
    for i in range(1, len(post.get("matches", [])) + 1):
        mp = os.path.join(HERE, folder, f"match_{i}.json")
        mk = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
        name = None
        if mk.get("source") == "네이버 스포츠" or (mk.get("league_ko") and mk.get("league_ko") != mk.get("league")):
            name = mk.get("league_ko")
        if not name and mk.get("league"):
            name = LEAGUE_KO.get((mk.get("country"), mk["league"]))
        out.append(name)
    return out


# 축구 외 종목 네이버 리그명 → 회원들이 흔히 쓰는 이름
LEAGUE_SHORT = {"프로농구": "KBL", "미국프로농구": "NBA", "메이저리그": "MLB", "일본프로야구": "NPB", "KBO리그": "KBO",
                "여자배구": "V리그 여자부", "남자배구": "V리그 남자부"}
LEAGUE_SEEN = ("KBL", "NBA", "MLB", "NPB", "KBO", "KOVO", "V리그", "프로농구", "WKBL", "준플레이오프", "플레이오프", "한국시리즈")


def fix_title(title, leagues, style, combo, sport="football", group=0):
    """모든 글 제목 앞에 공식 리그명 (2026-10-17 리그명 필수).
    축구는 늘 공식명으로 바꿈(Claude 짐작 대신). 다른 종목은 원래 [ ] 안에 리그명이 이미 있으면(예: MLB 챔피언십 시리즈) 그대로.
    group: 잡리그 묶음 글이면 경기 수 → [리그 N경기 프리뷰]."""
    ls = list(dict.fromkeys(LEAGUE_SHORT.get(x, x) for x in leagues if x))
    m = re.match(r"^\[([^\]]*)\]\s*(.*)$", title)
    head, rest = (m.group(1), m.group(2)) if m else ("", title)
    if not ls:
        return title
    if sport != "football" and not group and any(w in head for w in LEAGUE_SEEN + tuple(ls)):
        return title
    lg = "·".join(ls)
    if group:
        tag = f"[{lg} {group}경기 프리뷰]" if style == "C" else f"[{lg} {group}경기]"
    elif style == "C":
        tag = f"[{lg} 조합 프리뷰]" if combo else f"[{lg} 프리뷰]"
    else:
        tag = f"[{lg} 조합]" if combo else f"[{lg}]"
    return f"{tag} {rest}"


def match_keys(folder, post, only=None):
    """경기 식별값: 네이버 경기 번호 (없으면 경기 시각+팀 이름). only=i 이면 i번째 경기만."""
    keys = set()
    for i, m in enumerate(post.get("matches", []), 1):
        if only and i != only:
            continue
        mp =os.path.join(HERE, folder, f"match_{i}.json")
        mk = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
        if mk.get("naver_game_id"):
            keys.add(f"naver:{mk['naver_game_id']}")
            keys.update(f"naver:{x}" for x in mk.get("naver_replaces", []))  # 연기돼 다시 잡힌 경기 (2026-10-25)
        elif mk.get("espn_game_id"):  # 네이버에 없는 리그는 ESPN 경기 번호 (한글 표기가 글마다 달라도 같은 경기, 2026-10-18)
            keys.add(f"espn:{mk['espn_game_id']}")
        if mk.get("kickoff_kst") and not mk.get("naver_game_id") and not mk.get("espn_game_id"):
            if mk.get("api_ids"):  # 한글 표기가 글마다 달라도 API 팀 번호가 같으면 같은 경기 (2026-10-21)
                keys.add(f"{mk['kickoff_kst'][:16]}|api:{mk['api_ids'][0]}|{mk['api_ids'][1]}")
        if mk.get("kickoff_kst"):  # 번호가 있어도 '시각|팀|팀' 키를 같이 남김 — 한 글은 네이버, 다른 글은 ESPN 번호로만 잡혀 같은 경기 중복 게시 (2026-10-21 버그: 스포르팅 vs 린츠 1369·1387)
            keys.add(f"{mk['kickoff_kst'][:16]}|{'|'.join(sorted(re.sub(r'\s', '', x) for x in (m['home'], m['away'])))}")
    return keys


def dup_keys(keys, posted):
    """이미 올린 경기 키. 네이버·ESPN·API 번호가 없어 '시각|팀|팀' 키뿐이면 같은 시각에 두 팀 이름이 비슷한지로도 봄
    (2026-10-21 버그: 'FC 이마바리'와 '이마바리'처럼 표기만 달라 J2리그 묶음 글 2개가 중복 게시)."""
    hit = set(keys) & posted
    from h2h import name_score
    for k in keys:
        p = k.split("|")
        if len(p) != 3 or p[1].startswith("api:"):
            continue
        for q in posted:
            r = q.split("|")
            if len(r) == 3 and r[0] == p[0] and not r[1].startswith("api:"):
                a, b = p[1:], r[1:]
                if (name_score(a[0], b[0]) >= 0.6 and name_score(a[1], b[1]) >= 0.6) or \
                   (name_score(a[0], b[1]) >= 0.6 and name_score(a[1], b[0]) >= 0.6):
                    hit.add(k)
    return hit


def latest_posted_keys(done):
    """이미 올린 경기: 이번 실행 기록 + 저장소의 최신 처리 기록(다른 실행·맥에서 방금 올린 것까지).
    2026-10-17 버그: 서버 실행이 시작 때 기록만 봐서, 그사이 맥에서 올린 경기를 다른 제목으로 또 올림."""
    keys = {k for v in done.values() if v.get("status") == "전달 완료" for k in v.get("match_keys", [])}
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=HERE, timeout=60, capture_output=True)
        r = subprocess.run(["git", "show", "origin/main:done.json"], cwd=HERE, timeout=30, capture_output=True, text=True)
        if r.returncode == 0:
            remote = json.loads(r.stdout)
            keys |= {k for v in remote.values() if v.get("status") == "전달 완료" for k in v.get("match_keys", [])}
    except Exception as e:
        print(f"  [최신 기록 확인 실패] {e}")
    return keys


def is_group(folder):
    """잡리그 묶음 글(split_bundle 이 만든 리그별 묶음)인지."""
    ap = os.path.join(HERE, folder, "article.json")
    return os.path.exists(ap) and bool(json.load(open(ap, encoding="utf-8")).get("group"))


def is_bundle(aid):
    """3경기 이상 묶인 분석 글인지 (제목 'N경기' 또는 본문의 HOME 칸 수)."""
    ap = os.path.join(HERE, "글", aid, "article.json")
    if not os.path.exists(ap):
        return False
    art = json.load(open(ap, encoding="utf-8"))
    n_title = max([int(x) for x in re.findall(r"(\d+)\s*경기", art.get("title", ""))] or [0])
    n_home = len(re.findall(r"(?m)^\s*HOME\s*[:：]", art.get("text", "")))
    # 카페 글은 경기마다 'SK vs 소노' 한 줄로 시작 (2026-10-18 버그: 농구달인 KBL 3경기 글이 조합 글로 처리돼 막힘)
    n_vs = 0 if aid.startswith("ls") else len(set(re.findall(r"(?mi)^\s*(\S[^\n]{0,20}?\s+vs\.?\s+\S[^\n]{0,20}?)\s*$", art.get("text", ""))))
    return n_title > 2 or n_home > 2 or n_vs > 2


def split_bundle(aid, board, done):
    """묶음 글을 경기별 글로 나눔 (이미 시작·이미 올린 경기는 미리 뺌). 나눈 글 번호 목록."""
    posted = sorted(latest_posted_keys(done))
    pk = os.path.join(HERE, "글", aid, "posted_keys.json")
    with open(pk, "w", encoding="utf-8") as f:
        json.dump(posted, f)
    prev = done.get(aid, {})
    exclude = sorted({x for s in prev.get("subs", []) for x in done.get(s, {}).get("no_kickoff", [])})
    ex = os.path.join(HERE, "글", aid, "exclude.json")  # 경기 시간을 못 찾은 경기는 빼고 나눔
    with open(ex, "w", encoding="utf-8") as f:
        json.dump(exclude, f, ensure_ascii=False)
    resplits = prev.get("resplits", 0) + (1 if prev.get("subs") else 0)
    extra = ["--suffix", f"r{resplits}"] if resplits else []  # 다시 나누면 새 번호 (이전 번호와 겹치면 '전달 완료'로 보고 건너뜀)
    code, out = run(["split_bundle.py", os.path.join("글", aid), "--sport", board.get("sport", "football"), "--posted", pk, "--exclude", ex] + extra,
                    f"[{aid}] 묶음 글 경기별로 나누기")
    subs = re.findall(r"\+ \[([\w-]+-g?\d+)\]", out)  # 잡리그 묶음(-g1)도 (2026-10-18 버그: 묶음 글이 안 올라감)
    if code == 0:
        for s in prev.get("subs", []):  # 이전에 나눈 실패 글은 새로 나눈 글로 대신함
            if not should_skip(done.get(s)):  # 기록 없는 나눈 글도 (2026-10-18 버그: 기록 없는 글 때문에 묶음을 계속 다시 나눔)
                done.setdefault(s, {"board": board["key"]})["status"] = "다시 나눔 - 새 글로 대신"
    done[aid] = {"at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "board": board["key"],
                 "status": f"묶음 나눔 - 경기 {len(subs)}개" if code == 0 else "가져오기 실패 - 건너뜀",
                 "tries": prev.get("tries", 0) + (0 if code == 0 else 1),
                 "subs": (prev.get("subs", []) + subs) if code == 0 else prev.get("subs", []), "resplits": resplits}
    save_done(done)
    return subs


QUEUE = os.path.join(HERE, "queue")  # 완성된 글을 비공개 쪽으로 넘기는 폴더 (워크플로가 queue 가지에 올림)


def stage_out(aid, folder, post, board, result):
    """완성된 글(post.json + 이미지)과 안내 정보(meta.json)를 queue/<글번호>/ 에 넣는다."""
    import shutil
    dst = os.path.join(QUEUE, aid)
    os.makedirs(dst, exist_ok=True)
    for name in post.get("images", []):
        shutil.copy(os.path.join(HERE, folder, name), os.path.join(dst, name))
    with open(os.path.join(dst, "post.json"), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    meta = {"aid": aid, "board": board["key"], "sport": board.get("sport"), "title": post["title"],
            "kickoff": result.get("kickoff"), "kickoff_kst": result.get("kickoff_kst"),
            "match_keys": result.get("match_keys", []), "staged_at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(dst, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  [전달 폴더에 넣음] queue/{aid} (이미지 {len(post.get('images', []))}장)")


def process(aid, submit, done, board, reuse=False):
    folder = os.path.join("글", aid)
    prev = done.get(aid, {})
    result = {"at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "board": board["key"],
              "tries": prev.get("tries", 0) + 1}
    if board.get("sport") not in SPORT_NAVER:
        print(f"\n[{aid}] [설정 오류] {board['name']}: 알 수 없는 종목 {board.get('sport')} → 게시 안 함")
        result["status"] = "설정 오류 - 게시 안 함"
        done[aid] = result
        return result
    post_path = os.path.join(HERE, folder, "post.json")
    check_path = os.path.join(HERE, folder, "check.json")

    reused = False
    if reuse and os.path.exists(post_path) and os.path.exists(check_path):
        with open(check_path, encoding="utf-8") as f:
            reused = json.load(f).get("ok", False)
    if reused:
        print(f"\n▶ [{aid}] 다시 쓰기: 이전 결과(대조 통과) 재사용")
    else:
        for attempt in range(1, 4):  # 다시 쓰기는 매번 결과가 조금씩 달라서, 대조에서 걸리면 같은 실행 안에서 바로 다시 (2026-10-17 )
            code, _ = run(["rewrite.py", folder, "--style", board.get("style", "C")],
                          f"[{aid}] 다시 쓰기 + 데이터 대조" + (f" (다시 {attempt}/3)" if attempt > 1 else ""))
            if code == 0:
                break
            try:
                if board.get("source") == "livescore" and not is_group(folder) and len(json.load(open(post_path, encoding="utf-8")).get("matches", [])) > 2:
                    break  # 묶음 글은 다시 해도 안 됨
            except Exception:
                pass
        if code != 0:
            result["status"] = "대조 불일치" if code == 2 else "다시 쓰기 실패"
            try:  # 라이브스코어 묶음 글(경기 3개 이상)이면 재시도하지 않음
                if board.get("source") == "livescore" and not is_group(folder) and len(json.load(open(post_path, encoding="utf-8")).get("matches", [])) > 2:
                    result["status"] = "경기 수 많음 - 게시 안 함"
            except Exception:
                pass
            done[aid] = result
            return result

    with open(post_path, encoding="utf-8") as f:
        post = json.load(f)
    if board.get("source") == "livescore" and not is_group(folder) and len(post.get("matches", [])) > 2:  # 라이브스코어 글은 경기 2개 이하만 (수십 경기 묶음 제외)
        result.update(status="경기 수 많음 - 게시 안 함", title=post.get("title", ""))
        done[aid] = result
        print(f"\n[{aid}] 경기가 {len(post['matches'])}개라 대체 글로 쓰지 않습니다")
        return result

    # 상대 전적·경기 시간·로고 먼저 (배너가 여기서 받은 로고를 씀)
    run(["h2h.py", folder, "--sport", board.get("sport", "football")], f"[{aid}] 상대 전적 + 경기 시간 + 로고")

    # 축구는 유럽 빅리그 + 손흥민·메시 경기만 (2026-10-23 GitHub 실행 시간 줄이기)
    if board.get("sport", "football") == "football":
        for i, m in enumerate(post.get("matches", []), 1):
            mp = os.path.join(HERE, folder, f"match_{i}.json")
            mk = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
            if not (is_big_match(mk) or star_game(m.get("home"), m.get("away"), m.get("home_en"), m.get("away_en"))):
                result.update(status="빅리그 아님 - 게시 안 함", title=post.get("title", ""))
                done[aid] = result
                print(f"\n[{aid}] {m.get('home')} vs {m.get('away')} ({mk.get('league_ko') or mk.get('league') or '리그 모름'}): "
                      f"유럽 빅리그·손흥민·메시 경기가 아니라 게시하지 않습니다")
                return result

    # 같은 경기 중복 막기 (2026-10-17 ): 카페·라이브스코어 어디서든 이미 올린 경기면 게시 안 함 → 먼저 올라온 글만 올라감
    keys = match_keys(folder, post)
    posted = latest_posted_keys(done)
    if dup_keys(keys, posted) and is_group(folder):
        # 잡리그 묶음: 이미 올린 경기만 빼고 다시 나눠 나머지는 올림 (2026-10-23 버그: 6경기 중 3경기가 다른 글로 올라가 나머지 3경기가 막힘)
        dups = [f"{m['home']} vs {m['away']}" for i, m in enumerate(post.get("matches", []), 1)
                if dup_keys(match_keys(folder, post, only=i), posted)]
        if len(dups) < len(post.get("matches", [])):
            result.update(status="중복 경기 일부 - 다시 나눔", title=post["title"], no_kickoff=dups)
            done[aid] = result
            print(f"\n[{aid}] 이미 올린 경기({', '.join(dups)})만 빼고 다시 나눕니다")
            return result
    if dup_keys(keys, posted):
        result.update(status="중복 경기 - 게시 안 함", title=post["title"], match_keys=sorted(keys))
        done[aid] = result
        print(f"\n[{aid}] 이미 올린 경기라 게시하지 않습니다 ({', '.join(sorted(dup_keys(keys, posted)))})")
        return result
    result["match_keys"] = sorted(keys)

    if board.get("chart") == "kbl":  # KBL 공식 기록 + 공식 엠블럼 (두 번째 아이디 차트)
        run(["kbl_data.py", folder], f"[{aid}] KBL 공식 기록 + 엠블럼")
    else:  # 축구·야구·배구도 농구와 같은 팀 흐름 차트 (네이버 스포츠 결과, 2026-10-17 )
        run(["team_flow.py", folder, "--sport", board.get("sport", "football")], f"[{aid}] 팀 흐름 (최근 경기)")
    no_card = set()
    if board.get("chart") == "pitcher":  # 야구: MLB 공식 기록 선발 투수·맞대결
        run(["mlb_data.py", folder], f"[{aid}] MLB 공식 기록 선발 투수 + 맞대결")
        # 선발은 언제든 바뀔 수 있으니 글은 그대로 올림 (2026-10-17 ). 다만 원문 선발과 공식 예고 선발이 다르거나
        # 공식 기록이 없으면(NPB·KBO, 예고 전) 다른 투수 기록이 글과 섞이지 않게 선발 카드만 뺌
        for i in range(1, len(post.get("matches", [])) + 1):
            pp = os.path.join(HERE, folder, f"pitcher_{i}.json")
            mism = json.load(open(pp, encoding="utf-8")).get("mismatch") if os.path.exists(pp) else ["공식 선발 기록 없음"]
            if mism:
                no_card.add(i)
                print(f"\n[{aid}] 경기 {i} 선발 카드 뺌 (글은 올림): {', '.join(mism)}")

    combo = len(post.get("matches", [])) > 1
    art_ = json.load(open(os.path.join(HERE, folder, "article.json"), encoding="utf-8"))
    group = len(post.get("matches", [])) if art_.get("group") else 0
    if True:  # 모든 종목 제목·배너에 공식 리그명 (2026-10-17 리그명 필수)
        leagues = official_leagues(folder, post)
        if group and not any(leagues) and art_.get("group_league") not in (None, "기타"):
            leagues = [art_["group_league"]]
        if not any(leagues):  # 네이버·API에 없는 리그: 원문 경기 머리줄의 리그명 (1374 '[기타 조합]' 제목, 2026-10-22)
            src = re.findall(r"^\s*([가-힣A-Za-z][^\n]{1,18}?)\s+(?:20\d\d\.\d{1,2}\.\d{1,2}|\d{1,2}월\s*\d{1,2}일)", art_.get("text", ""), re.M)
            if len(src) == len(post.get("matches", [])):
                leagues = [s.strip() for s in src]
        new_title = fix_title(post["title"], leagues, board.get("style", "C"), combo, board.get("sport", "football"), group)
        if new_title != post["title"]:
            print(f"  제목 리그명: {post['title']} → {new_title}")
            post["title"] = new_title
        if not combo and leagues and leagues[0]:
            post["league_label"] = leagues[0]
    images, kickoffs, missing = [], [], []
    for i, m in enumerate(post.get("matches", []), 1):
        league = post.get("league_label", "")
        mp = os.path.join(HERE, folder, f"match_{i}.json")
        if combo and os.path.exists(mp):  # 조합 픽: 배너 위 문구 = 그 경기 리그명 (2026-10-16 지시)
            with open(mp, encoding="utf-8") as f:
                league = json.load(f).get("league_ko") or league
        if board.get("layout") == "card":  # 배구: 배너 대신 분석 카드 이미지 (본문은 픽 줄만, 2026-10-16 )
            code, _ = run(["make_card.py", "--post", folder, "--match", str(i), "--league", league,
                           "--out", os.path.join(folder, f"card_{i}.png")], f"[{aid}] 경기 {i} 분석 카드")
            if code == 0:
                images.append(f"card_{i}.png")
                post["layout"] = "card"
        else:
            code, _ = run(["make_banner.py", "--home", m["home"], "--home-en", m["home_en"],
                           "--away", m["away"], "--away-en", m["away_en"],
                           "--league", league,
                           "--pick", post["pick"] if len(post.get("matches", [])) == 1 else m["pick"],
                           "--out", os.path.join(folder, f"banner_{i}.png")], f"[{aid}] 경기 {i} 로고 배너")
            if code == 0:
                images.append(f"banner_{i}.png")
        if board.get("chart") == "pitcher" and i not in no_card and os.path.exists(os.path.join(HERE, folder, f"pitcher_{i}.json")):
            code, _ = run(["make_pitcher_card.py", "--data", os.path.join(folder, f"pitcher_{i}.json"),
                           "--home-en", m["home_en"], "--away-en", m["away_en"],
                           "--out", os.path.join(folder, f"pitcher_{i}.png")], f"[{aid}] 경기 {i} 선발 투수 카드")
            if code == 0:
                images.append(f"pitcher_{i}.png")
        stats_json = os.path.join(folder, f"stats_{i}.json")
        kbl_json = os.path.join(folder, f"kbl_{i}.json")
        flow_json = os.path.join(folder, f"flow_{i}.json")
        if board.get("chart") != "kbl" and os.path.exists(os.path.join(HERE, flow_json)):
            kbl_json = flow_json  # 같은 그림(make_stats_b)으로
        if os.path.exists(os.path.join(HERE, kbl_json)):
            code, _ = run(["make_stats_b.py", "--data", kbl_json, "--h2h", stats_json,
                           "--out", os.path.join(folder, f"stats_{i}.png")], f"[{aid}] 경기 {i} 팀 흐름 차트")
            if code == 0:
                images.append(f"stats_{i}.png")
        elif board.get("chart") == "pitcher" and not (json.load(open(os.path.join(HERE, stats_json), encoding="utf-8")).get("h2h_matches")
                                                     if os.path.exists(os.path.join(HERE, stats_json)) else None):
            pass  # 야구: 공식 맞대결 기록이 없으면(NPB·KBO 등) 빈 차트는 안 넣음
        elif os.path.exists(os.path.join(HERE, stats_json)):
            code, _ = run(["make_stats.py", "--data", stats_json, "--out", os.path.join(folder, f"stats_{i}.png")],
                          f"[{aid}] 경기 {i} 상대 전적 차트")
            if code == 0:
                images.append(f"stats_{i}.png")
        match_path = os.path.join(HERE, folder, f"match_{i}.json")
        # 경기 시간·종료 여부를 못 확인하면 게시 안 함 — 파일이 있어도 시작 시각이 없으면 막음
        # (2026-10-18 버그: 상대 전적만 찾고 경기는 못 찾은 중국 슈퍼리그 글이 시작 31분 뒤에 올라감)
        if not os.path.exists(match_path) or not json.load(open(match_path, encoding="utf-8")).get("kickoff_kst"):
            if group:  # 잡리그 묶음: 못 찾은 경기만 빼고 다시 나눠 나머지는 올림 (2026-10-20 버그: 6경기 중 3경기 때문에 전체가 막힘)
                missing.append(f"{m['home']} vs {m['away']}")
                print(f"\n[{aid}] {m['home']} vs {m['away']} 경기 시간을 확인하지 못해 이 경기는 빼고 다시 나눕니다")
                continue
            result["status"] = "경기 확인 실패 - 게시 안 함"
            result["title"] = post["title"]
            done[aid] = result
            print(f"\n[{aid}] {m['home']} vs {m['away']} 경기 시간을 API-Sports·네이버 모두에서 확인하지 못해 게시하지 않습니다")
            return result
        if os.path.exists(match_path):
            with open(match_path, encoding="utf-8") as f:
                mk = json.load(f)
            if mk.get("naver_upper") and mk["naver_upper"] not in SPORT_NAVER[board["sport"]]:
                result["status"] = "종목 불일치 - 게시 안 함"
                result["title"] = post["title"]
                done[aid] = result
                print(f"\n[{aid}] 게시판은 {board['sport']} 인데 네이버에서 찾은 경기는 {mk.get('naver_game')} "
                      f"({mk['naver_upper']}) → 게시하지 않습니다")
                return result
            if mk.get("finished") and group:  # 잡리그 묶음: 이미 시작한 경기만 빼고 다시 나눔 (2026-10-23)
                missing.append(f"{m['home']} vs {m['away']}")
                print(f"\n[{aid}] {m['home']} vs {m['away']} 이미 시작한 경기라 이 경기는 빼고 다시 나눕니다 ({mk['label']})")
                continue
            if mk.get("kickoff_kst"):
                kickoffs.append((mk["kickoff_kst"], mk["label"]))
            if mk.get("finished"):
                result["status"] = "경기 종료 - 게시 안 함"
                result["kickoff"] = mk["label"]
                result["title"] = post["title"]
                done[aid] = result
                print(f"\n[{aid}] {m['home']} vs {m['away']} 경기가 이미 끝나서 게시하지 않습니다 ({mk['label']})")
                return result
    if kickoffs:
        result["kickoff"] = min(kickoffs)[1]  # 조합 픽은 가장 빠른 경기 기준
        result["kickoff_kst"] = min(kickoffs)[0]
    if missing:
        result.update(status="경기 확인 실패 - 게시 안 함", title=post["title"], no_kickoff=missing)
        done[aid] = result
        return result

    post["images"] = images
    with open(os.path.join(HERE, folder, "post.json"), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)

    # 공개 쪽은 여기까지 (2026-10-28 공개/비공개 분리): 완성된 글(post.json + 이미지)을 전달 폴더에 넣고 끝.
    # 등록·댓글·로그인·같은 글 중복 확인은 비공개 쪽이 한다.
    if submit and dup_keys(keys, latest_posted_keys(done)):  # 전달 직전 다시 확인 (그사이 다른 실행이 같은 경기를 전달했을 수 있음)
        result.update(status="중복 경기 - 게시 안 함", title=post["title"])
        done[aid] = result
        print(f"\n[{aid}] 전달 직전 확인: 방금 같은 경기를 전달해서 게시하지 않습니다")
        return result

    if submit:
        stage_out(aid, folder, post, board, result)
        result["status"] = "전달 완료"
    else:
        result["status"] = "미리보기"
    result["title"] = post["title"]
    if not submit and done.get(aid, {}).get("status") == "전달 완료":
        return result  # 미리보기가 '전달 완료' 기록을 덮지 않게 (중복 방지)
    done[aid] = result
    return result


# ---------------------------------------------------------------- 대체 글 (2026-10-16 지시)
# 오늘(한국 날짜) 그 종목 글을 하나도 못 올렸으면 (시간 상관없이), 라이브스코어 종목 게시판 맨 위의
# 픽스터 글(배지 있는 글쓴이, 경기 2개 이하)을 그 종목 아이디·스타일 그대로 올린다. 막히면(경기 종료 등) 다음 글, 최대 3개.


def posted_today(done, boards, sport):
    today = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    keys = {b["key"] for b in boards if b.get("sport") == sport}
    return any(v.get("status") == "전달 완료" and v.get("board") in keys and str(v.get("at", "")).startswith(today)
               for v in done.values())


def fallback_needed(done, boards):
    """대체 글이 필요한 (게시판, 후보 글번호들) — check_new.py 도 씀."""
    sys.path.insert(0, HERE)
    import livescore_fetch
    out = []
    for fb in boards:
        if not fb.get("fallback") or fb.get("paused") or posted_today(done, boards, fb["sport"]):
            continue
        # 시간 제한 없음: 그날 그 종목 글이 아직 없으면 바로 (2026-10-17 카페에 글이 없어도 라이브스코어 글 있으면 올려)
        now = datetime.datetime.now(KST)
        days = {now.strftime("%Y-%m-%d"), (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")}
        cands = [w for w, _, d in livescore_fetch.list_articles(fb["board_url"], "*")
                 if f"ls{w}" not in done and d in days]  # 오늘·어제 글만 (어제 밤 올라온 오늘 경기 글 포함, 지난 경기는 자동으로 걸러짐)
        if cands:
            out.append((fb, cands[:3]))
    return out


def fallback(boards, done, summary, submit):
    for fb, cands in fallback_needed(done, boards):
        print(f"\n######## [대체 글] {fb['sport']}: 오늘 카페 글이 없어 {fb['name']} 맨 위 픽스터 글로")
        for w in cands:
            code, out = run(["livescore_fetch.py", "--url", fb["board_url"], "--author", "*", "--article", w],
                            f"{fb['name']} 글 가져오기 (ls{w})")
            ids = re.findall(r"\+ \[([a-z]*\d+)\]", out)
            if not ids:
                done[f"ls{w}"] = {"at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "board": fb["key"],
                                  "status": "가져오기 실패 - 건너뜀"}
                save_done(done)
                continue
            r = process(ids[0], submit, done, fb)
            summary.append((ids[0], r))
            save_done(done)
            if r.get("status") in ("전달 완료", "미리보기"):
                break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1, help="가져올 최신 글 개수 (기본 1)")
    ap.add_argument("--article", help="특정 글 번호")
    ap.add_argument("--submit", action="store_true", help="실제 등록 (없으면 미리보기)")
    ap.add_argument("--reuse", action="store_true", help="대조 통과한 이전 다시 쓰기 결과 재사용")
    ap.add_argument("--board", help="한 게시판만 (boards.json 의 key, 예: shotdol / nongdal)")
    args = ap.parse_args()

    with open(os.path.join(HERE, "boards.json"), encoding="utf-8") as f:
        boards = json.load(f)
    all_boards = boards
    if args.board:
        boards = [b for b in boards if b["key"] == args.board]
    else:
        boards = [b for b in boards if not b.get("paused") and not b.get("fallback")]  # 대체 글 게시판은 따로

    done = load_done()
    summary = []
    if args.article:  # 특정 글: 예전처럼 게시판마다
        for board in boards:
            print(f"\n######## {board['name']} 게시판 (스타일 {board.get('style', 'C')})")
            if board.get("source") == "livescore":
                code, out = run(["livescore_fetch.py", "--url", board["board_url"], "--author", board["author"],
                                 "--article", args.article.removeprefix("ls")], f"{board['name']} 글 가져오기")
            else:
                code, out = run(["cafe_fetch.py", "--url", board["board_url"], "--article", args.article],
                                f"{board['name']} 글 가져오기")
            for aid in re.findall(r"\+ \[([a-z]*\d+)\]", out):
                summary.append((aid, process(aid, args.submit, done, board, args.reuse)))
                save_done(done)
    else:
        # 카페·라이브스코어 새 글을 모아 '올라온 시각' 순으로 처리 → 같은 경기면 먼저 올라온 글이 올라감 (2026-10-17 )
        # 카페 = 글 작성 시각, 라이브스코어 = 사이트에 시각이 없어 처음 발견한 시각(seen.json, 1시간 단위)
        sys.path.insert(0, HERE)
        import livescore_fetch
        seen = load_seen()
        now = datetime.datetime.now(KST)
        stamp = now.strftime("%Y-%m-%d %H:%M")
        days = {now.strftime("%Y-%m-%d"), (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")}
        queue = []
        only_keys = None  # 서버: check_new 가 새 글을 찾은 카페 게시판만 읽음 (게시판마다 브라우저를 띄워 약 20초씩, 2026-10-25 )
        nb = os.path.join(HERE, "new_boards.json")
        if os.environ.get("GITHUB_ACTIONS") and not args.board and os.path.exists(nb):
            try:
                only_keys = set(json.load(open(nb, encoding="utf-8")).get("keys", []))
            except Exception:
                only_keys = None
        for board in boards:
            if only_keys is not None and board.get("source") != "livescore" and board["key"] not in only_keys:
                print(f"\n######## {board['name']} 게시판: 새 글 없음 → 읽지 않음")
                continue
            print(f"\n######## {board['name']} 게시판 확인")
            if board.get("source") == "livescore":
                try:
                    items = livescore_fetch.list_articles(board["board_url"], board["author"])
                except Exception as e:
                    print(f"  [목록 실패] {e}")
                    continue
                for w, title, d in sorted(items, key=lambda x: int(x[0])):
                    aid = f"ls{w}"
                    if d not in days or should_skip(done.get(aid), done):
                        continue
                    seen.setdefault(aid, stamp)
                    queue.append((seen[aid], 1, board, aid))
                    print(f"  새 글 {aid} (처음 발견 {seen[aid]}) {title[:40]}")
            else:
                code, out = run(["cafe_fetch.py", "--url", board["board_url"], "--count", str(args.count)],
                                f"{board['name']} 글 가져오기")
                for aid in re.findall(r"\+ \[(\d+)\]", out):
                    if should_skip(done.get(aid), done):
                        print(f"  [{aid}] 이미 처리한 글이라 건너뜀 ({done[aid].get('status')})")
                        continue
                    ap_ = os.path.join(HERE, "글", aid, "article.json")
                    t = json.load(open(ap_, encoding="utf-8")).get("date", stamp) if os.path.exists(ap_) else stamp
                    queue.append((t, 0, board, aid))
                    print(f"  새 글 {aid} (작성 {t})")
        save_seen(seen)
        queue.sort(key=lambda x: (x[0], x[1]))  # 시각이 같으면 카페 먼저
        for t, _, board, aid in queue[:12]:
            print(f"\n######## [{t}] {aid} → {board['name']} (스타일 {board.get('style', 'C')})")
            if aid.startswith("ls"):
                for attempt in range(1, 3):  # 이미지 읽기가 어긋나면 바로 한 번 더
                    o = run(["livescore_fetch.py", "--url", board["board_url"], "--author", board["author"],
                             "--article", aid[2:]], f"{board['name']} 글 가져오기 ({aid})" + (" (다시)" if attempt > 1 else ""))[1]
                    if f"+ [{aid}]" in o:
                        break
                if f"+ [{aid}]" not in o:  # 가져오기 실패도 기록해서 다음 실행 때 다시 (최대 3번)
                    prev = done.get(aid, {})
                    done[aid] = {"at": stamp, "board": board["key"], "status": "가져오기 실패 - 건너뜀",
                                 "tries": prev.get("tries", 0) + 1}
                    save_done(done)
                    continue
            if is_bundle(aid):  # 3경기 이상 묶음 글 → 경기별로 나눠서 하나씩 (2026-10-17 무조건 게시)
                for sub in split_bundle(aid, board, done):
                    if should_skip(done.get(sub)):
                        continue
                    summary.append((sub, process(sub, args.submit, done, board, args.reuse)))
                    save_done(done)
                continue
            summary.append((aid, process(aid, args.submit, done, board, args.reuse)))
            save_done(done)

    print("\n" + "=" * 60)
    for aid, r in summary:
        print(f"[{aid}] {r.get('status')} | {r.get('title', '')} | 경기 {r.get('kickoff', '-')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
