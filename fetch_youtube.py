#!/usr/bin/env python3
"""
한국 유튜브 인기 영상 수집기 (카테고리별)

- YouTube Data API v3 의 mostPopular 차트(regionCode=KR)를 카테고리별로 가져온다.
- '전체'는 카테고리 지정 없이, 나머지는 videoCategoryId 로 필터링.
- 결과를 data/youtube.json 에 카테고리별로 묶어 저장한다 (최신 상태만).
- API 키는 환경변수 YOUTUBE_API_KEY 에서 읽는다 → GitHub Secrets에 넣어두면 노출 안 됨.

할당량: videos.list 호출당 1유닛. 카테고리 6개를 1시간마다 불러도 하루 144유닛
→ 무료 한도(10,000) 대비 무시 가능.
표준 라이브러리만 사용.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
YOUTUBE_PATH = os.path.join(DATA_DIR, "youtube.json")

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

# 카테고리당 가져올 영상 수
TOP_N = 10
API_URL = "https://www.googleapis.com/youtube/v3/videos"

# 화면 탭 순서대로. key=화면에 쓸 id, label=탭 이름, cat=유튜브 카테고리ID(None=전체)
# 유튜브 표준 카테고리ID: 뉴스/정치=25, 엔터테인먼트=24, 스포츠=17, 음악=10, 게임=20
CATEGORIES = [
    {"key": "all",    "label": "전체",   "cat": None},
    {"key": "news",   "label": "뉴스",   "cat": "25"},
    {"key": "enter",  "label": "엔터",   "cat": "24"},
    {"key": "sports", "label": "스포츠", "cat": "17"},
    {"key": "music",  "label": "음악",   "cat": "10"},
    {"key": "game",   "label": "게임",   "cat": "20"},
]


def fetch_popular(category_id=None):
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": "KR",
        "maxResults": str(TOP_N),
        "key": API_KEY,
    }
    if category_id:
        params["videoCategoryId"] = category_id
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_views(n: int) -> str:
    """조회수를 '12만', '1.3억' 같은 한국식 축약으로."""
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}".rstrip("0").rstrip(".") + "억"
    if n >= 10_000:
        return f"{n/10_000:.0f}만"
    if n >= 1_000:
        return f"{n/1_000:.0f}천"
    return str(n)


def parse(data):
    items = []
    for v in data.get("items", []):
        sn = v.get("snippet", {})
        st = v.get("statistics", {})
        vid = v.get("id", "")
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        views = int(st.get("viewCount", 0)) if st.get("viewCount") else 0
        items.append({
            "title": sn.get("title", "").strip(),
            "channel": sn.get("channelTitle", "").strip(),
            "views": views,
            "views_text": format_views(views),
            "thumbnail": thumb,
            "url": f"https://www.youtube.com/watch?v={vid}" if vid else "",
        })
    return items


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(KST)

    if not API_KEY:
        print("[fetch_youtube] YOUTUBE_API_KEY 없음 — 건너뜀 "
              "(Secrets 미설정 시 정상). 영상 카드는 비표시됩니다.", file=sys.stderr)
        return 0

    categories_out = []
    total = 0
    for c in CATEGORIES:
        try:
            data = fetch_popular(c["cat"])
            items = parse(data)
        except Exception as e:  # noqa: BLE001
            # 특정 카테고리가 실패해도 나머지는 계속 진행
            print(f"[fetch_youtube] '{c['label']}' 수집 실패: {e}", file=sys.stderr)
            items = []
        categories_out.append({
            "key": c["key"],
            "label": c["label"],
            "items": items,
        })
        total += len(items)
        print(f"[fetch_youtube]   {c['label']}: {len(items)}건")

    if total == 0:
        print("[fetch_youtube] 전체 0건 — 키 또는 응답 확인 필요. 기존 파일 보존.", file=sys.stderr)
        return 0

    payload = {
        "timestamp": now.isoformat(),
        "label": now.strftime("%H:%M"),
        "categories": categories_out,
    }
    with open(YOUTUBE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[fetch_youtube] {now.strftime('%Y-%m-%d %H:%M')} KST · "
          f"카테고리 {len(categories_out)}개 · 총 {total}건 수집")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
