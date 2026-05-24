#!/usr/bin/env python3
"""
한국 유튜브 인기 영상 수집기 (2단계)

- YouTube Data API v3 의 mostPopular 차트(regionCode=KR)에서 인기 영상 상위 N개를 가져온다.
- 결과를 data/youtube.json 에 저장한다 (최신 상태만, 누적 아님).
- API 키는 환경변수 YOUTUBE_API_KEY 에서 읽는다 → GitHub Secrets에 넣어두면 코드/화면에 노출되지 않음.

할당량: videos.list 한 번 호출 = 1유닛. 1시간마다 호출해도 하루 24유닛 → 무료 한도(10,000) 대비 무시 가능.
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

# 가져올 영상 수
TOP_N = 10
# 한국 인기 영상 차트
API_URL = "https://www.googleapis.com/youtube/v3/videos"


def fetch_popular():
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": "KR",
        "maxResults": str(TOP_N),
        "key": API_KEY,
    }
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
        # 중간 화질 썸네일 우선, 없으면 기본
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
        # 키가 없어도 전체 워크플로우가 죽지 않도록 0으로 정상 종료
        return 0

    try:
        data = fetch_popular()
        items = parse(data)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_youtube] 수집 실패: {e}", file=sys.stderr)
        # 실패해도 기존 youtube.json 보존하고 종료 (워크플로우는 통과)
        return 0

    if not items:
        print("[fetch_youtube] 영상 0건 — 응답 구조 확인 필요", file=sys.stderr)
        return 0

    payload = {
        "timestamp": now.isoformat(),
        "label": now.strftime("%H:%M"),
        "items": items,
    }
    with open(YOUTUBE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[fetch_youtube] {now.strftime('%Y-%m-%d %H:%M')} KST · 인기 영상 {len(items)}건 수집")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
