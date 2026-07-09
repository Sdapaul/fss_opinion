"""
금융규제·법령해석포털 (better.fsc.go.kr) 스크래퍼.

수집 전략:
  1순위 — 법령해석·비조치의견서 개별 API (일련번호·분야 포함)
  2순위 — 통합조회 API (날짜 필터 적용, 개별 API 미지원 항목 보완)
중복 제거 — 일련번호(lawreqNumber / opinionNumber) 기준
"""

import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

BASE_URL = "https://better.fsc.go.kr"
ST_NO = "11"

_HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
}

# 개별 소스 정의: (소스명, API경로, Referer경로, 구분, 상세idx필드, 일련번호필드)
_INDIVIDUAL_SOURCES = [
    (
        "비조치의견서",
        "/fsc_new/replyCase/selectReplyCaseOpinionList.do",
        "/fsc_new/replyCase/OpinionList.do?stNo=11&muNo=86&muGpNo=75",
        "비조치의견서",
        "opinionIdx",
        "opinionNumber",
    ),
    (
        "법령해석",
        "/fsc_new/replyCase/selectReplyCaseLawreqList.do",
        "/fsc_new/replyCase/LawreqList.do?stNo=11&muNo=85&muGpNo=75",
        "법령해석",
        "lawreqIdx",
        "lawreqNumber",
    ),
]

_TOTAL_API = "/fsc_new/replyCase/selectReplyCaseTotalReplyList.do"
_TOTAL_REFERER = "/fsc_new/replyCase/TotalReplyList.do?stNo=11&muNo=117&muGpNo=75"

_DETAIL_URL_MAP = {
    "법령해석": {
        "path": "/fsc_new/replyCase/LawreqDetail.do",
        "idx_param": "lawreqIdx",
    },
    "비조치의견서": {
        "path": "/fsc_new/replyCase/OpinionDetail.do",
        "idx_param": "opinionIdx",
    },
}


def _build_detail_url(item_type: str, data_idx: int) -> str:
    mapping = _DETAIL_URL_MAP.get(item_type)
    if not mapping:
        return (
            f"{BASE_URL}/fsc_new/replyCase/TotalReplyList.do"
            f"?stNo={ST_NO}&muNo=117&muGpNo=75"
        )
    return (
        f"{BASE_URL}{mapping['path']}"
        f"?stNo={ST_NO}&muNo=117&{mapping['idx_param']}={data_idx}&actCd=R"
    )


def _fetch_source(api_path: str, referer_path: str, length: int = 100) -> list[dict]:
    headers = {**_HEADERS_BASE, "Referer": f"{BASE_URL}{referer_path}"}
    payload = {
        "draw": "1",
        "start": "0",
        "length": str(length),
        "searchKeyword": "",
        "searchCondition": "",
        "searchType": "",
    }
    resp = requests.post(f"{BASE_URL}{api_path}", headers=headers, data=payload, timeout=20)
    resp.raise_for_status()
    return resp.json().get("data", [])


# validator.py 하위 호환용
def _fetch_page(start: int = 0, length: int = 50) -> list[dict]:
    return _fetch_source(_TOTAL_API, _TOTAL_REFERER, length=length)


def _build_detail_url_compat(item_type: str, data_idx: int) -> str:
    return _build_detail_url(item_type, data_idx)


def fetch_new_items(seen_ids: set, days_back: int = 3) -> list[dict]:
    """
    법령해석·비조치의견서 개별 API → 통합조회 API 순으로 수집.
    일련번호 기준 중복 제거 후 seen_ids에 없는 신규 항목 반환.

    반환 구조:
      id        : str  — 분야:일련번호 (통합조회 fallback 시 category:dataIdx)
      legacy_id : str  — category:dataIdx (구 형식 호환)
      title     : str
      date      : str  — YYYY-MM-DD (개별 API는 "")
      url       : str
      category  : str  — 법령해석 / 비조치의견서 / 기타
      field     : str  — 분야
      serial_no : str  — 일련번호 원본
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    collected: dict[str, dict] = {}   # dedup_key → item
    # 개별 API에서 처리된 dataIdx — 통합조회 중복 방지용
    processed_indices: dict[str, set] = {"법령해석": set(), "비조치의견서": set()}

    # ── 1단계: 개별 API (일련번호·분야 포함) ─────────────────────────────
    for source_name, api_path, referer_path, item_type, idx_field, serial_field in _INDIVIDUAL_SOURCES:
        try:
            raw_items = _fetch_source(api_path, referer_path)
            print(f"[{source_name}] 수신: {len(raw_items)}건")
        except Exception as e:
            print(f"[{source_name}] API 실패: {e}")
            continue

        for raw in raw_items:
            data_idx = int(raw.get(idx_field, 0))
            serial_no = str(raw.get(serial_field, "") or "").strip()
            field = str(raw.get("category", "") or "").strip()
            title = str(raw.get("title", "") or "").strip()

            # 일련번호 있으면 "분야:일련번호", 없으면 "구분:dataIdx"
            dedup_key = f"{item_type}:{serial_no}" if serial_no else f"{item_type}:{data_idx}"
            legacy_id = f"{item_type}:{data_idx}"

            processed_indices[item_type].add(data_idx)

            if dedup_key in collected:
                continue
            if dedup_key in seen_ids or legacy_id in seen_ids:
                continue

            collected[dedup_key] = {
                "id": dedup_key,
                "legacy_id": legacy_id,
                "title": title,
                "date": "",            # 개별 API에는 날짜 필드 없음
                "url": _build_detail_url(item_type, data_idx),
                "category": item_type,
                "field": field,
                "serial_no": serial_no,
            }

    # ── 2단계: 통합조회 API (날짜 필터, 기타 항목 보완) ──────────────────
    try:
        total_items = _fetch_source(_TOTAL_API, _TOTAL_REFERER)
        print(f"[통합조회] 수신: {len(total_items)}건")
    except Exception as e:
        print(f"[통합조회] API 실패: {e}")
        total_items = []

    for raw in total_items:
        item_date = str(raw.get("replyRegDate", "") or "")[:10]
        if not item_date or item_date < cutoff:
            continue

        item_type = str(raw.get("pastreqType", "") or "기타").strip()
        data_idx = int(raw.get("dataIdx", 0))
        title = str(raw.get("title", "") or "").strip()
        legacy_id = f"{item_type}:{data_idx}"

        # 개별 API에서 이미 처리된 항목 건너뜀
        if data_idx in processed_indices.get(item_type, set()):
            continue

        if legacy_id in collected or legacy_id in seen_ids:
            continue

        collected[legacy_id] = {
            "id": legacy_id,
            "legacy_id": legacy_id,
            "title": title,
            "date": item_date,
            "url": _build_detail_url(item_type, data_idx),
            "category": item_type,
            "field": "",
            "serial_no": "",
        }

    return list(collected.values())


def fetch_detail_content(url: str) -> dict:
    """상세 페이지에서 첨부파일·회신일·질의요지·회답·이유 추출."""
    headers = {**_HEADERS_BASE}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[detail] 페이지 로드 실패 ({url}): {e}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    label_map = {
        "첨부파일": "attachment",
        "회신일": "reply_date",
        "질의요지": "query",
        "회답": "answer",
        "이유": "reason",
    }

    result = {}
    for th in soup.find_all("th"):
        label = th.get_text(strip=True)
        if label not in label_map:
            continue
        # td는 같은 tr의 형제 또는 바로 다음 형제 td
        tr = th.parent
        td = tr.find("td") if tr else th.find_next_sibling("td")
        if td:
            result[label_map[label]] = td.get_text(separator="\n", strip=True)

    return result
