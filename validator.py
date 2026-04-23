#!/usr/bin/env python3
"""
포털 최신 항목과 발송 이력을 비교해 누락·불일치를 검증.

seen_items.json(항상 커밋됨)을 1차 기준으로 확인하고,
DB에도 있으면 추가로 인정합니다.

실행:
  python validator.py [days_back=7]
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from scraper import _fetch_page, _build_detail_url
from db import _conn

SEEN_FILE = Path("seen_items.json")


def _load_seen_ids() -> set:
    """seen_items.json에서 발송 이력 ID 집합을 반환."""
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def validate_recent(days_back: int = 7) -> dict:
    """최근 days_back일 포털 항목이 seen_items.json 또는 DB에 있는지 검증."""
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    seen_ids = _load_seen_ids()

    try:
        raw_items = _fetch_page(start=0, length=100)
    except Exception as e:
        return {"error": str(e)}

    portal_items: dict[str, dict] = {}
    for raw in raw_items:
        item_date = raw.get("replyRegDate", "")[:10]
        if item_date < cutoff:
            continue
        item_type = raw.get("pastreqType", "")
        data_idx = raw.get("dataIdx", 0)
        uid = f"{item_type}:{data_idx}"
        portal_items[uid] = {
            "id": uid,
            "title": raw.get("title", "").strip(),
            "date": item_date,
            "category": item_type,
            "url": _build_detail_url(item_type, data_idx),
        }

    # seen_items.json 기준으로 확인 (DB 기능 추가 전 항목도 포함)
    existing_ids = {uid for uid in portal_items if uid in seen_ids}

    # DB에만 있는 경우도 인정 (DB가 존재할 때)
    if portal_items and _conn is not None:
        try:
            remaining = set(portal_items.keys()) - existing_ids
            if remaining:
                placeholders = ",".join("?" for _ in remaining)
                with _conn() as conn:
                    db_ids = {
                        row[0]
                        for row in conn.execute(
                            f"SELECT id FROM items WHERE id IN ({placeholders})",
                            list(remaining),
                        )
                    }
                existing_ids |= db_ids
        except Exception:
            pass

    missing_ids = set(portal_items.keys()) - existing_ids
    missing_items = [portal_items[uid] for uid in sorted(missing_ids)]

    return {
        "cutoff": cutoff,
        "portal_count": len(portal_items),
        "seen_count": len(existing_ids),
        "missing_count": len(missing_ids),
        "missing_items": missing_items,
    }


def main() -> None:
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(f"최근 {days_back}일 포털 항목 검증 중...")

    result = validate_recent(days_back)

    if "error" in result:
        print(f"오류: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"포털 항목 수: {result['portal_count']}건")
    print(f"발송 이력 확인: {result['seen_count']}건")
    print(f"누락 항목 수: {result['missing_count']}건")

    if result["missing_items"]:
        print("\n[누락 항목 목록]")
        for item in result["missing_items"]:
            print(f"  [{item['category']}] {item['date']} {item['title']}")
            print(f"    URL: {item['url']}")
        sys.exit(2)
    else:
        print("검증 완료 — 모든 항목 정상 발송됨")


if __name__ == "__main__":
    main()
