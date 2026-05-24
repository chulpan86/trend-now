#!/usr/bin/env python3
"""
한국 급상승 트렌드 수집기 (1단계: 구글 트렌드 RSS만 사용)

- 구글 트렌드 RSS(geo=KR)에서 현재 급상승 키워드 + 트래픽 + 관련 뉴스를 가져온다.
- 매 실행 시점의 스냅샷을 data/history.json 에 누적한다.
- GitHub Actions가 1시간마다 이 스크립트를 실행 → 24시간 흐름이 자동으로 쌓인다.

키 발급/비용 없음. 표준 라이브러리만 사용한다.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

# 한국 시간(KST)
KST = timezone(timedelta(hours=9))

RSS_URL = "https://trends.google.com/trending/rss?geo=KR"

# 구글 트렌드 RSS의 뉴스 항목이 들어있는 커스텀 네임스페이스
NS = {"ht": "https://trends.google.com/trending/rss"}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")

# 흐름/누적 계산을 위해 최근 기록을 보관한다.
# '오늘' 탭이 자정 직후에도 끊기지 않도록 하루보다 넉넉하게 36시간 유지.
RETENTION_HOURS = 36
# 한 스냅샷에서 보관할 상위 키워드 수
TOP_N = 10


def fetch_rss(url: str) -> str:
    """RSS 원문을 가져온다. 구글이 봇 차단을 하지 않도록 일반 브라우저 UA를 붙인다."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_traffic(text: str) -> int:
    """'20,000+' / '2만+' 같은 트래픽 표기를 정렬용 정수로 바꾼다."""
    if not text:
        return 0
    t = text.replace(",", "").replace("+", "").strip()
    # '2만', '20천' 같은 한글 단위 처리
    m = re.match(r"(\d+(?:\.\d+)?)\s*만", t)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.match(r"(\d+(?:\.\d+)?)\s*천", t)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.match(r"(\d+)", t)
    return int(m.group(1)) if m else 0


def parse_items(xml_text: str):
    """RSS XML에서 키워드 목록을 뽑아낸다."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue

        traffic_raw = item.findtext("ht:approx_traffic", default="", namespaces=NS) or ""

        # 관련 뉴스 1건만 대표로 (제목 + 출처 + 링크)
        news = None
        news_el = item.find("ht:news_item", NS)
        if news_el is not None:
            news = {
                "title": (news_el.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip(),
                "source": (news_el.findtext("ht:news_item_source", default="", namespaces=NS) or "").strip(),
                "url": (news_el.findtext("ht:news_item_url", default="", namespaces=NS) or "").strip(),
            }

        items.append({
            "keyword": title,
            "traffic_raw": traffic_raw.strip(),
            "traffic": parse_traffic(traffic_raw),
            "news": news,
        })

    # 트래픽 큰 순으로 정렬 후 상위 N개
    items.sort(key=lambda x: x["traffic"], reverse=True)
    return items[:TOP_N]


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def prune(history):
    """보관 기간을 넘긴 오래된 스냅샷 제거."""
    cutoff = datetime.now(KST) - timedelta(hours=RETENTION_HOURS)
    kept = []
    for snap in history:
        try:
            ts = datetime.fromisoformat(snap["timestamp"])
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            kept.append(snap)
    return kept


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(KST)

    try:
        xml_text = fetch_rss(RSS_URL)
        items = parse_items(xml_text)
    except Exception as e:  # noqa: BLE001 - 자동화에서는 죽지 않고 로그만 남긴다
        print(f"[fetch_trends] 수집 실패: {e}", file=sys.stderr)
        # 실패해도 기존 데이터는 보존하고 그냥 종료
        return 1

    if not items:
        print("[fetch_trends] 키워드 0건 — RSS 구조가 바뀌었을 수 있음", file=sys.stderr)
        return 1

    snapshot = {
        "timestamp": now.isoformat(),
        "label": now.strftime("%H:%M"),
        "items": items,
    }

    # 누적 기록 갱신
    history = load_history()
    history.append(snapshot)
    history = prune(history)

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # 화면이 빠르게 읽는 용도의 '최신 스냅샷'도 따로 저장
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"[fetch_trends] {now.strftime('%Y-%m-%d %H:%M')} KST · "
          f"{len(items)}건 수집 · 누적 스냅샷 {len(history)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
