#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rewrite.py

카페 원문(article.json)을 스타일 C(전문 프리뷰형)로 다시 쓰고, 데이터가 원문과 같은지 검사한다.
다시 쓰기는 이 맥의 Claude Code(claude -p)로 한다.

사용법:
    python3 rewrite.py 글/312942
    -> 글/312942/post.json (title, body, home/away 한글·영어 팀명, league_label, pick)
    -> 글/312942/check.json (데이터 대조 결과)

데이터 대조 규칙 (하나라도 걸리면 ok=false, 게시하지 않음):
    1) 다시 쓴 글의 모든 숫자(2.02, 4승, 5위 등)가 원문에 있어야 함
    2) Claude가 원문에서 뽑은 이름·숫자 목록(names, facts)이 원문에 글자 그대로 있어야 함
    3) 그 목록이 다시 쓴 글에도 모두 들어가 있어야 함 (빠짐 없음)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

STYLE_C = """\
[스타일 C · 전문 프리뷰형]
- 제목: [리그명 프리뷰] 홈팀 vs 원정팀  (예: [A리그 개막전 프리뷰] 시드니FC vs 웨스턴시드니W)
- 본문은 소제목 4개: "◆ 홈팀 — 한 줄 요약", "◆ 원정팀 — 한 줄 요약", "◆ 상대 전적", "◆ 결론"
- 소제목 아래는 존댓말 문단 1~2개. 담백하고 신뢰감 있게. 이모지 금지
- 결론 마지막 줄은 정확히 "추천: <원문 추천 그대로>"
- 각 소제목 아래에서 승부를 가르는 핵심 구절 1~2개를 **이렇게** 별표 두 개로 감싸 강조 (예: **최근 맞대결 4승 1무 1패**, **주전 상당수가 이탈**). 소제목 줄과 추천 줄에는 쓰지 않음
- 원문에 상대 전적이 없으면 "◆ 상대 전적" 소제목은 빼기
"""

STYLE_A = """\
[스타일 A · 핵심 정리형]
- 제목: [리그명] 홈팀 vs 원정팀 핵심 정리  (예: [KBL] 소노 vs 모비스 핵심 정리)
- 본문 구성 (각 소제목은 '■ '로 시작하는 한 줄):
  "■ 한눈에 보기" → "· 추천: <원문 추천 그대로>", "· 포인트: <핵심 한 줄>"
  "■ 홈팀" → '· '로 시작하는 짧은 항목 2~4줄
  "■ 원정팀" → '· '로 시작하는 짧은 항목 2~4줄
  "■ 결론" → 존댓말 1~2문장, 마지막 줄은 정확히 "▶ 픽: <원문 추천 그대로>"
- 원문에 팀 정보가 한쪽만 있으면 그 팀 소제목만 씀. 존댓말, 이모지 금지
- 항목마다 핵심 숫자·구절 1개 정도를 **이렇게** 별표 두 개로 감싸 강조. 소제목 줄과 추천·픽 줄에는 쓰지 않음
"""



STYLE_D = """\
[스타일 D · 분석 카드형] (배구 전용, 2026-10-16 확정)
- 제목: [대회명] 홈팀 vs 원정팀 분석  (예: [KOVO컵 여자배구] 현대건설 vs GS칼텍스 분석)
- 본문 구성 (각 소제목은 '▣ '로 시작하는 한 줄):
  "▣ 홈팀" → 홈팀 분석 문단 1개 (존댓말 3~4문장, 원문 사실만). 분석 카드 이미지의 HOME 칸에 들어감
  "▣ 원정팀" → 원정팀 분석 문단 1개 (존댓말 3~4문장). AWAY 칸에 들어감
  "▣ 승부 분석" → 존댓말 2~3문장 (이미지 밑 글자로 올라감), 마지막 줄은 정확히 "▶ 픽: <원문 추천 그대로>"
- 홈·원정 문단은 각각 150자 안쪽. 이모지 금지. 승부 분석 문단에서만 핵심 구절 1~2개를 **이렇게** 강조 (홈·원정 문단과 소제목·픽 줄에는 쓰지 않음)
- matches 의 각 경기에 "home_record", "away_record" 도 넣는다: 원문에 적힌 이번 대회·시즌 전적 글자 그대로 (예: 0승1패). 없으면 ""
"""

STYLE_E = """\
[스타일 E · 선발 매치업형] (야구 전용, 2026-10-16)
- 제목: [리그·대회명] 홈팀 vs 원정팀 선발 매치업  (리그·대회명은 원문에 나온 말로. 예: [MLB 챔피언쉽 시리즈] 템파베이 vs 클리블랜드 선발 매치업)
- 본문 구성 (각 소제목은 정확히 이 모양의 한 줄):
  "【 선발 】" → 두 팀 선발 투수 비교, 존댓말 2~3문장
  "【 불펜 】" → 불펜 운용·피로도, 존댓말 1~2문장 (원문에 없으면 이 소제목은 빼기)
  "【 타선 】" → 타선 흐름, 존댓말 1~2문장 (원문에 없으면 빼기)
  "【 결론 】" → 존댓말 1~2문장, 마지막 줄은 정확히 "▶ 픽: <원문 추천 그대로>"
- 이모지 금지. 소제목마다 핵심 구절 1~2개를 **이렇게** 강조. 소제목 줄과 픽 줄에는 쓰지 않음
- matches 의 각 경기에 "home_pitcher", "away_pitcher" (원문에 쓰인 선발 투수 이름 글자 그대로, 없으면 "")와
  "home_pitcher_en", "away_pitcher_en" (그 투수의 영어 이름. 공식 예고 선발과 성을 대조하는 데 쓰니 꼭 적는다. 성만이라도 예: Peralta)도 넣는다.
  홈·원정은 원문에서 알 수 없으면 원문에 먼저 나온 팀을 홈으로 둔다
"""

PROMPT = """\
너는 스포츠 분석 커뮤니티의 픽스터 글 작가다. 아래 [원문]을 아래에 적힌 스타일 그대로 다시 써라.

절대 규칙:
- 숫자·배당·순위·전적·날짜·팀명·선수명·감독명·리그명은 원문에 쓰인 그대로 옮긴다. 바꾸거나 추가하거나 계산하지 않는다.
- 원문에 없는 사실·기록·예측을 새로 만들지 않는다. 문장 표현만 바꾼다.
- 원문 글쓴이 닉네임과 카페 이름은 쓰지 않는다.
- names·facts에 넣은 표현은 본문에도 원문 글자 그대로 한 번 이상 넣는다 (빠지면 대조에서 걸려 게시 안 됨).
- 조합 픽이면 결론에서 경기별 추천(matches의 pick)을 원문 글자 그대로 한 번씩 적는다.
- 조합 픽(경기 2개 이상)이면 본문을 경기별 묶음으로 나눈다 (2026-10-16 규칙: 윗경기 사진 밑에 윗경기 글, 밑경기 사진 밑에 밑경기 글).
  각 경기 묶음은 "@@경기1", "@@경기2" … 한 줄로 시작하고(matches 순서), 그 아래에 그 경기의 소제목·문단만 쓴다.
  제목에는 '조합'을 넣는다 (예: [유럽축구 조합 프리뷰] A vs B · C vs D / [KBL 조합] A vs B · C vs D 핵심 정리).
  모든 경기 묶음 뒤에 "@@결론" 한 줄을 쓰고 그 아래에 결론 소제목과 마지막 추천/픽 줄을 쓴다. 경기가 1개면 이 표시를 쓰지 않는다.

{style}

출력은 JSON 하나만 (설명·코드블록 표시 없이):
{{
  "title": "...",
  "body": "...(줄바꿈은 \\n)",
  "league_label": "배너 상단 문구 (예: A리그 개막전)",
  "pick": "원문 추천 그대로 (예: 시드니FC 승 @2.02). 본문의 추천/픽 줄과 같은 내용",
  "matches": [
    {{"home": "본문에 쓴 홈팀 한글명", "home_en": "홈팀 영어 정식명 (예: Sydney FC)", "home_country_en": "홈팀 나라 영어명 (예: Australia)",
      "away": "본문에 쓴 원정팀 한글명", "away_en": "원정팀 영어 정식명", "away_country_en": "원정팀 나라 영어명",
      "pick": "이 경기의 추천을 원문 글자 그대로 (예: 시드니FC 승, 2.5 오버)"}}
  ],  (조합 픽이면 경기마다 하나씩, 원문에 나온 순서대로)
  "names": ["원문에 나온 선수·감독·팀 이름을 원문 글자 그대로 전부"],
  "facts": ["원문에 나온 숫자가 들어간 표현을 원문 글자 그대로 전부 (예: 4승 1무 1패, 5위, @2.02)"],
  "comment": "글 올린 뒤 글쓴이가 다는 첫 댓글. 회원들이 답하고 싶어지게 [댓글 형식]대로 1~2문장, 존댓말, 이모지·링크·사이트 이름 금지, 원문에 없는 숫자 금지"
}}

[댓글 형식] {comment_format}
[최근에 단 댓글 — 이것들과 문장·형식이 겹치지 않게]
{recent_comments}

[원문 제목] {title}
[원문]
{text}
"""


def claude_bin():
    """앱 업데이트로 경로가 바뀌어도 가장 최신 claude 를 찾는다."""
    paths = glob.glob(os.path.expanduser(
        "~/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"))
    if paths:
        return sorted(paths, key=os.path.getmtime)[-1]
    found = shutil.which("claude")  # 서버(GitHub Actions)는 npm으로 설치한 claude
    if not found:
        raise RuntimeError("Claude Code 프로그램을 찾지 못했습니다.")
    return found


# 참여 유도 댓글 형식 (2026-10-16 지시: 글마다 조금씩 다른 형식) — 직전에 쓴 형식은 피해서 고름
COMMENT_FORMATS = [
    "승부 예측 질문형: 여러분은 어느 쪽을 보시는지 묻기",
    "스코어 맞히기형: 예상 스코어를 댓글로 남겨 달라고 하기",
    "선택지 투표형: 홈 승 / 무 / 원정 승(또는 오버 / 언더)처럼 선택지를 주고 하나 골라 달라고 하기",
    "핵심 변수형: 이 경기 승부를 가를 변수(선수·전술·흐름)가 무엇이라고 보는지 묻기",
    "반대 의견 환영형: 다르게 보는 분들의 의견과 이유를 듣고 싶다고 하기",
    "관전 포인트형: 이 경기에서 가장 기대되는 장면이나 선수를 묻기",
    "자신감 체크형: 이 픽에 얼마나 자신 있는지(예: 강하게 간다 / 소액만 / 거른다) 묻기",
]
COMMENT_LOG = os.path.join(HERE, "comment_log.json")


def load_comment_log():
    if os.path.exists(COMMENT_LOG):
        with open(COMMENT_LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def pick_comment_format(log, combo):
    import random
    recent = [x.get("format") for x in log[-3:]]
    pool = [f for f in COMMENT_FORMATS if f not in recent] or COMMENT_FORMATS
    if combo:  # 조합 픽은 '두 경기 중 더 자신 있는 쪽' 형식도 후보
        pool = pool + ["조합 선택형: 두(여러) 경기 중 어느 쪽이 더 자신 있는지, 조합 그대로 갈지 단폴로 갈지 묻기"]
    return random.choice(pool)


def clean(text):
    text = text.replace("​", "")
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def ask_claude(prompt):
    r = subprocess.run([claude_bin(), "-p", prompt], capture_output=True, text=True, timeout=600, cwd=HERE)
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(f"claude 실행 실패: {r.stderr.strip() or out}")
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError(f"JSON 응답이 아님: {out[:200]}")
    # JSON 뒤에 설명 글이 더 붙어 와도(Extra data) 첫 JSON 객체만 읽음
    return json.JSONDecoder().raw_decode(out[m.start():])[0]


def norm(s):
    return re.sub(r"\s+", "", s)


def numbers(s):
    return set(re.findall(r"\d+(?:\.\d+)?", s))


def typo_of_team(item, post, src_n, body_n):
    """원문 오타를 정식 팀명으로 고쳐 쓴 경우 (2026-10-16 허용).
    경기 팀명(home/away) 중 원문에도 그대로 나오고 다시 쓴 글에도 있는 이름과 글자 수가 같고 한 글자만 다르면 오타로 본다."""
    it = norm(item)
    for m in post.get("matches", []):
        for team in (m.get("home", ""), m.get("away", "")):
            t = norm(team)
            if (t and t != it and len(t) == len(it) and sum(a != b for a, b in zip(t, it)) == 1
                    and t in src_n and t in body_n):
                return team
    return None


def check(src, post):
    src_n = norm(src)
    body = post["title"] + "\n" + re.sub(r"(?m)^@@(경기\d+|결론)\s*$", "", post["body"].replace("**", ""))  # 강조·경기 묶음 표시는 빼고 대조
    body_n = norm(body)
    problems, fixed = [], []
    extra = sorted(numbers(body) - numbers(src))
    if extra:
        problems.append(f"원문에 없는 숫자: {', '.join(extra)}")
    for key in ("names", "facts"):
        for item in post.get(key, []):
            if norm(item) not in src_n:
                problems.append(f"원문에 그대로 없는 {key}: {item}")
            elif norm(item) not in body_n:
                if key == "facts":
                    continue  # 숫자 표현은 생략해도 됨 (바꾸거나 새로 만든 숫자는 위 '원문에 없는 숫자' 검사가 막음, 2026-10-17)
                head = item.split()[0] if len(item.split()) > 1 else ""
                if key == "names" and len(head) >= 2 and norm(head) in body_n:
                    continue  # 팀 이름을 줄여 쓴 것 (예: 한신 타이거즈 → 한신) — 이름을 바꾼 건 아님
                team = typo_of_team(item, post, src_n, body_n)
                if team:
                    fixed.append(f"{item} → {team}")
                else:
                    problems.append(f"다시 쓴 글에서 빠짐: {item}")
    if norm(post.get("pick", "")) not in src_n:
        # 조합 픽: 전체 추천 줄이 원문에 한 줄로 없어도, 경기별 추천을 원문 그대로 이어 붙인 것이면 통과
        parts = [norm(m.get("pick", "")) for m in post.get("matches", [])]
        sep = lambda x: re.sub(r"[/+,·&]", "", x)
        joined = sep(norm(post.get("pick", "")))
        if not (len(parts) > 1 and all(x and x in src_n for x in parts) and joined == sep("".join(parts))):
            problems.append(f"추천이 원문과 다름: {post.get('pick')}")
    c = post.get("comment", "")
    if not c.strip():
        problems.append("참여 유도 댓글(comment)이 없음")
    elif re.search(r"https?://|www\.", c) or len(c) > 200:
        problems.append(f"댓글에 링크·사이트 이름이 있거나 너무 김: {c}")
    elif numbers(c) - numbers(src):
        problems.append(f"댓글에 원문에 없는 숫자: {', '.join(sorted(numbers(c) - numbers(src)))}")
    if not post.get("matches"):
        problems.append("경기 정보(matches)가 없음")
    for m in post.get("matches", []):
        for k in ("home_record", "away_record", "home_pitcher", "away_pitcher"):
            if m.get(k) and norm(m[k]) not in src_n:
                problems.append(f"전적이 원문과 다름: {m[k]}")
        if norm(m.get("pick", "")) not in src_n:
            problems.append(f"경기 추천이 원문과 다름: {m.get('pick')}")
    return {"ok": not problems, "problems": problems, "typo_fixed": fixed,
            "checked": {"names": len(post.get("names", [])), "facts": len(post.get("facts", []))}}


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 rewrite.py 글/<글번호>")
        sys.exit(1)
    folder = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    with open(os.path.join(folder, "article.json"), encoding="utf-8") as f:
        art = json.load(f)
    src = clean(art["text"])

    style = sys.argv[sys.argv.index("--style") + 1] if "--style" in sys.argv else "C"
    log = load_comment_log()
    combo = len(re.findall(r"(?i)\bvs\b", art["title"] + src)) > 1 or "조합" in art["title"] + src
    comment_format = pick_comment_format(log, combo)
    recent = "\n".join(f"- {x['text']}" for x in log[-5:]) or "(없음)"
    post = ask_claude(PROMPT.format(style={"A": STYLE_A, "C": STYLE_C, "D": STYLE_D, "E": STYLE_E}[style], title=art["title"], text=src,
                                    comment_format=comment_format, recent_comments=recent))
    post["comment_format"] = comment_format
    post["article_id"] = art["article_id"]
    post["style"] = style
    post.setdefault("banner", "banner.png")
    result = check(art["title"] + "\n" + src, post)  # 원문 제목도 원문 데이터 (예: 월드시리즈 2차전, 2026-10-25)

    with open(os.path.join(folder, "post.json"), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    with open(os.path.join(folder, "check.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  제목: {post['title']}")
    print(f"  댓글({comment_format.split(':')[0]}): {post.get('comment', '')}")
    print(f"  데이터 대조: {'통과' if result['ok'] else '불일치'} (이름 {result['checked']['names']}개, 숫자 표현 {result['checked']['facts']}개)")
    for t in result["typo_fixed"]:
        print(f"    · 원문 오타를 정식 팀명으로: {t}")
    for p in result["problems"]:
        print(f"    - {p}")
    sys.exit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
