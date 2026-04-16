"""
금융규제·법령해석포털 (better.fsc.go.kr) 스크래퍼.

회신사례 통합조회 API를 호출해 신규 항목을 가져옵니다.
"""

import json
import requests
from datetime import date, timedelta

BASE_URL = "https://better.fsc.go.kr"

# 회신사례 통합조회 AJAX 엔드포인트
LIST_API = f"{BASE_URL}/fsc_new/replyCase/selectReplyCaseTotalReplyList.do"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": (
        f"{BASE_URL}/fsc_new/replyCase/TotalReplyList.do"
        "?stNo=11&muNo=117&muGpNo=75"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

# pastreqType 값 → 상세 페이지 URL 매핑
#   gubun=1: 법령해석  → LawreqDetail.do  (파라미터: lawreqIdx)
#   gubun=2: 비조치의견서 → OpinionDetail.do (파라미터: opinionIdx)
DETAIL_URL_MAP = {
    "법령해석": {
        "path": "/fsc_new/replyCase/LawreqDetail.do",
        "idx_param": "lawreqIdx",
    },
    "비조치의견서": {
        "path": "/fsc_new/replyCase/OpinionDetail.do",
        "idx_param": "opinionIdx",
    },
}

# stNo / muNo 고정값 (포털 공통)
ST_NO = "11"
MU_NO = "117"


def _build_detail_url(item_type: str, data_idx: int) -> str:
    """상세 페이지 URL 생성."""
    mapping = DETAIL_URL_MAP.get(item_type)
    if not mapping:
        # 알 수 없는 타입은 목록 페이지로
        return (
            f"{BASE_URL}/fsc_new/replyCase/TotalReplyList.do"
            f"?stNo={ST_NO}&muNo={MU_NO}&muGpNo=75"
        )
    path = mapping["path"]
    idx_param = mapping["idx_param"]
    return (
        f"{BASE_URL}{path}"
        f"?stNo={ST_NO}&muNo={MU_NO}&{idx_param}={data_idx}&actCd=R"
    )


def _fetch_page(start: int = 0, length: int = 50) -> list[dict]:
    """API 한 페이지 호출 후 raw item 리스트 반환."""
    payload = {
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "searchKeyword": "",
        "searchCondition": "",
        "searchType": "",
    }
    resp = requests.post(LIST_API, headers=HEADERS, data=payload, timeout=20)
    resp.raise_for_status()
    result = resp.json()
    return result.get("data", [])


def fetch_new_items(seen_ids: set, days_back: int = 3) -> list[dict]:
    """
    최근 days_back 일 이내 항목 중 seen_ids 에 없는 신규 항목 반환.

    반환 구조:
      {
        "id":       str,   # 고유 키 (API의 dataIdx 기반)
        "title":    str,
        "date":     str,   # YYYY-MM-DD
        "url":      str,   # 상세 페이지 URL
        "category": str,   # 법령해석 / 비조치의견서
      }
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    new_items: list[dict] = []

    try:
        raw_items = _fetch_page(start=0, length=100)
    except Exception as e:
        print(f"[better.fsc.go.kr] API 호출 실패: {e}")
        return []

    print(f"[better.fsc.go.kr] 수신 항목 수: {len(raw_items)}")

    for raw in raw_items:
        item_date: str = raw.get("replyRegDate", "")[:10]
        # 날짜 필터
        if item_date < cutoff:
            continue

        item_type: str = raw.get("pastreqType", "")
        data_idx: int = raw.get("dataIdx", 0)
        unique_id = f"{item_type}:{data_idx}"

        # 이미 발송한 항목 제외
        if unique_id in seen_ids:
            continue

        new_items.append(
            {
                "id": unique_id,
                "title": raw.get("title", "").strip(),
                "date": item_date,
                "url": _build_detail_url(item_type, data_idx),
                "category": item_type or "기타",
            }
        )

    return new_items
