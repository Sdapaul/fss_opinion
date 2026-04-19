"""
항목 상세 페이지를 가져와 Gemini API로 요약.
GEMINI_API_KEY 환경변수가 없으면 조용히 빈 문자열 반환.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_client = None

_SYSTEM_PROMPT = (
    "당신은 금융 규제 전문가입니다. "
    "금융감독원 비조치의견서·법령해석 문서를 읽고 핵심 내용을 "
    "3~4문장으로 간결하게 요약합니다. "
    "전문 용어는 유지하고, 질의 배경·회신 결론·주요 근거를 포함하세요."
)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _fetch_detail_text(url: str) -> str:
    """상세 페이지 본문 텍스트 추출 (최대 4,000자)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup.select("nav, header, footer, script, style, .gnb, .lnb, .snb"):
            tag.decompose()

        main = (
            soup.select_one(".cont_wrap")
            or soup.select_one(".view_wrap")
            or soup.select_one(".board_view")
            or soup.select_one("#content")
            or soup.select_one("main")
            or soup.body
        )
        if main is None:
            return ""

        text = main.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:4000]
    except Exception as e:
        print(f"[summarizer] 페이지 로드 실패 ({url}): {e}")
        return ""


def summarize_item(item: dict) -> str:
    """항목 URL 본문을 Gemini로 요약. API 키 미설정이거나 실패하면 빈 문자열 반환."""
    if not os.environ.get("GEMINI_API_KEY"):
        return ""

    body = _fetch_detail_text(item["url"])
    if not body:
        return ""

    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"[{item['category']}] {item['title']}\n\n{body}",
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=400,
            ),
        )
        return response.text.strip()
    except Exception as e:
        print(f"[summarizer] AI 요약 실패 ({item['title']}): {e}")
        return ""
