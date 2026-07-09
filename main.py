#!/usr/bin/env python3
"""
금융감독원 비조치의견서·법령해석 신규 알림 메인 스크립트.

실행:
  python main.py

환경변수 (GitHub Secrets):
  FSS_EMAIL_SENDER      발신 Gmail 주소
  FSS_EMAIL_PASSWORD    Gmail 앱 비밀번호
  FSS_EMAIL_RECIPIENTS  수신자 이메일 (쉼표 구분)
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

from scraper import fetch_new_items, fetch_detail_content
from emailer import send_email
from summarizer import summarize_item
from db import init_db, save_items, export_excel_bytes

SEEN_FILE = Path("seen_items.json")


def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data)
        except Exception:
            pass
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _is_legacy_seen(seen: set) -> bool:
    """seen_ids가 구버전(fss.or.kr URL) 형식이면 True."""
    return any("http" in s for s in seen)


def _init_seen_from_portal() -> set:
    """
    현재 포털의 최신 항목 id를 모두 seen_ids에 추가.
    첫 실행 또는 seen_items.json 형식 전환 시 호출.
    발송 없이 현재 상태를 기준점으로 저장한다.
    """
    print("seen_items.json 초기화: 현재 포털 항목을 기준점으로 설정합니다...")
    all_items = fetch_new_items(set(), days_back=365)
    new_seen: set = set()
    for item in all_items:
        new_seen.add(item["id"])
        if item.get("legacy_id") and item["legacy_id"] != item["id"]:
            new_seen.add(item["legacy_id"])
    print(f"초기화 완료: {len(new_seen)}건을 seen_ids에 등록 (발송 없음)")
    return new_seen


def main() -> None:
    init_db()
    seen = load_seen()
    print(f"기존 발송 이력: {len(seen)}건")

    # 구버전 seen_ids(fss.or.kr URL 형식) 감지 → 자동 재초기화
    if _is_legacy_seen(seen):
        print("구버전 seen_items.json 감지 — 현재 포털 기준으로 재초기화합니다.")
        seen = _init_seen_from_portal()
        save_seen(seen)
        print("재초기화 완료. 다음 실행부터 신규 항목을 알림합니다.")
        return

    # 최근 3일치 항목 확인 (주말·공휴일 대비)
    new_items = fetch_new_items(seen, days_back=3)
    print(f"신규 항목: {len(new_items)}건")

    if new_items:
        for item in new_items:
            print(f"  상세 내용 로딩: {item['title'][:40]}…")
            item["detail"] = fetch_detail_content(item["url"])
            print(f"  AI 요약 중: {item['title'][:40]}…")
            item["summary"] = summarize_item(item)

        # DB 저장
        save_items(new_items)
        print("DB 저장 완료")

        # 당일 발송 항목을 엑셀로 생성해 이메일 첨부
        today = date.today().isoformat()
        excel_bytes = export_excel_bytes(today, today)

        send_email(new_items, excel_bytes=excel_bytes)

        # 발송 완료 항목을 이력에 추가 (새 형식 + 구 형식 모두 저장)
        for item in new_items:
            seen.add(item["id"])
            if item.get("legacy_id") and item["legacy_id"] != item["id"]:
                seen.add(item["legacy_id"])
        save_seen(seen)
        print("seen_items.json 업데이트 완료")
    else:
        print("신규 항목 없음")


if __name__ == "__main__":
    # 환경변수 필수값 점검
    required_vars = ["FSS_EMAIL_SENDER", "FSS_EMAIL_PASSWORD", "FSS_EMAIL_RECIPIENTS"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"오류: 다음 환경변수가 설정되지 않았습니다 → {missing}", file=sys.stderr)
        sys.exit(1)

    main()
