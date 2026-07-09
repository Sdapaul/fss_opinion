import smtplib
import os
import re
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from datetime import date

PRIORITY_LAWS = {
    "금융회사의 지배구조에 관한 법률",
    "상법",
    "형법",
    "개인금융채권의 관리 및 개인금융채무자의 보호에 관한 법률",
    "공중 등 협박목적 및 대량살상무기확산을 위한 자금조달행위의 금지에 관한 법률",
    "금융거래지표의 관리에 관한 법률",
    "금융산업의 구조개선에 관한 법률",
    "금융소비자 보호에 관한 법률",
    "금융위원회의 설치 등에 관한 법률",
    "금융혁신지원 특별법",
    "기업구조조정 촉진법",
    "기업구조조정투자회사법",
    "대부업 등의 등록 및 금융이용자 보호에 관한 법률",
    "보험사기방지 특별법",
    "보험업법",
    "감정평가 및 감정평가사에 관한 법률",
    "서민의 금융생활 지원에 관한 법률",
    "신용정보의 이용 및 보호에 관한 법률",
    "예금자보호법",
    "외국인투자 촉진법",
    "외국환거래법",
    "자본시장과 금융투자업에 관한 법률",
    "전자금융거래법",
    "주식ㆍ사채 등의 전자등록에 관한 법률",
    "주식회사 등의 외부감사에 관한 법률",
    "채권의 공정한 추심에 관한 법률",
    "특정 금융거래정보의 보고 및 이용 등에 관한 법률",
    "한국주택금융공사법",
    "개인정보 보호법",
    "공익신고자 보호법",
    "독점규제 및 공정거래에 관한 법률",
    "마약류 불법거래 방지에 관한 특례법",
    "범죄수익은닉의 규제 및 처벌 등에 관한 법률",
    "약관의 규제에 관한 법률",
    "전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법",
    "특정경제범죄 가중처벌 등에 관한 법률",
    "근로자퇴직급여 보장법",
    "금융지주회사법",
    "산업안전보건법",
    "유사수신행위의 규제에 관한 법률",
    "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
    "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "중대재해 처벌 등에 관한 법률",
}

# 긴 법률명이 먼저 매칭되도록 길이 내림차순 정렬, 시행령/시행규칙/규정/시행세칙도 포함
_LAWS_PATTERN = re.compile(
    "(?:" + "|".join(re.escape(law) for law in sorted(PRIORITY_LAWS, key=len, reverse=True)) + ")"
    + r"(?:\s*(?:시행령|시행규칙|시행세칙|규정))?"
)


def _highlight_laws(text: str) -> str:
    """제목 내 우선순위 법률명을 노란 배경으로 하이라이트."""
    return _LAWS_PATTERN.sub(
        lambda m: (
            f'<mark style="background:#fef08a;color:#713f12;'
            f'padding:1px 3px;border-radius:3px;font-weight:600;">'
            f'{m.group()}</mark>'
        ),
        text,
    )


def _build_detail_html(detail: dict) -> str:
    """질의요지·회답·이유·첨부파일·회신일을 테이블로 렌더링."""
    if not detail:
        return ""

    rows = ""
    label_keys = [
        ("회신일", "reply_date"),
        ("첨부파일", "attachment"),
        ("질의요지", "query"),
        ("회답", "answer"),
        ("이유", "reason"),
    ]
    for label, key in label_keys:
        value = detail.get(key, "").strip()
        if not value:
            continue
        # 줄바꿈을 <br>로 변환
        value_html = value.replace("\n", "<br>")
        rows += f"""
        <tr>
          <th style="padding:5px 10px;background:#f8fafc;color:#374151;font-size:12px;
                     font-weight:600;white-space:nowrap;vertical-align:top;
                     border:1px solid #e5e7eb;width:70px;">{label}</th>
          <td style="padding:5px 10px;font-size:12px;color:#374151;line-height:1.7;
                     border:1px solid #e5e7eb;">{value_html}</td>
        </tr>"""

    if not rows:
        return ""

    return f"""
    <div style="margin-top:8px;">
      <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:4px;">
        {rows}
      </table>
    </div>"""


def _build_html(items: list[dict]) -> str:
    today = date.today().strftime("%Y년 %m월 %d일")

    rows_by_category: dict[str, list[dict]] = {}
    for item in items:
        rows_by_category.setdefault(item["category"], []).append(item)

    sections = ""
    for category, cat_items in rows_by_category.items():
        rows_html = ""
        for item in cat_items:
            summary_html = ""
            if item.get("summary"):
                summary_html = (
                    f'<div style="margin-top:6px;font-size:12px;color:#374151;'
                    f'background:#f8fafc;border-left:3px solid #93c5fd;'
                    f'padding:5px 10px;border-radius:0 4px 4px 0;line-height:1.6;">'
                    f'<span style="font-weight:600;color:#1e3a5f;font-size:11px;">[AI요약]</span> '
                    f'{item["summary"]}</div>'
                )
            url_html = (
                f'<div style="margin-top:4px;font-size:11px;color:#9ca3af;">'
                f'&#128279; 원문: <a href="{item["url"]}" style="color:#6b7280;word-break:break-all;">{item["url"]}</a>'
                f'</div>'
            )
            field_badge = ""
            if item.get("field"):
                field_badge = (
                    f'<span style="display:inline-block;font-size:11px;'
                    f'background:#e0f2fe;color:#0369a1;border-radius:3px;'
                    f'padding:1px 6px;margin-right:6px;">{item["field"]}</span>'
                )
            serial_badge = ""
            if item.get("serial_no"):
                serial_badge = (
                    f'<span style="font-size:11px;color:#9ca3af;">#{item["serial_no"]}</span>'
                )
            detail_html = _build_detail_html(item.get("detail") or {})
            rows_html += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">
                <div style="margin-bottom:3px;">{field_badge}{serial_badge}</div>
                <a href="{item['url']}" style="color:#1d4ed8;text-decoration:none;font-weight:500;">{_highlight_laws(item['title'])}</a>
                {url_html}
                {summary_html}
                {detail_html}
              </td>
              <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;white-space:nowrap;color:#6b7280;vertical-align:top;">
                {item['date']}
              </td>
            </tr>"""

        sections += f"""
        <h2 style="font-size:16px;color:#1e3a5f;margin:24px 0 8px;">{category}</h2>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <thead>
            <tr style="background:#f3f4f6;">
              <th style="padding:8px 12px;text-align:left;color:#374151;">제목</th>
              <th style="padding:8px 12px;text-align:left;color:#374151;white-space:nowrap;">등록일</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>"""

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"></head>
<body style="font-family:'Malgun Gothic',Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#111;">
  <div style="background:#1e3a5f;padding:20px 24px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:18px;color:#fff;">금융감독원 비조치의견서·법령해석 신규 알림</h1>
    <p style="margin:4px 0 0;font-size:13px;color:#93c5fd;">{today} 기준</p>
  </div>
  <div style="border:1px solid #e5e7eb;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
    {sections}
    <hr style="margin-top:32px;border:none;border-top:1px solid #e5e7eb;">
    <p style="font-size:12px;color:#9ca3af;margin-top:8px;">
      원문 출처: <a href="https://www.fss.or.kr" style="color:#6b7280;">금융감독원 (fss.or.kr)</a>
    </p>
  </div>
</body>
</html>"""
    return html


def _build_text(items: list[dict]) -> str:
    today = date.today().strftime("%Y-%m-%d")
    lines = [f"금융감독원 신규 알림 ({today})\n" + "=" * 50]
    for item in items:
        field_str = f" [{item['field']}]" if item.get("field") else ""
        serial_str = f" #{item['serial_no']}" if item.get("serial_no") else ""
        block = (
            f"[{item['category']}]{field_str}{serial_str} {item['title']} ({item['date']})\n"
            f"  원문 URL: {item['url']}"
        )
        if item.get("summary"):
            block += f"\n  [AI요약] {item['summary']}"
        detail = item.get("detail") or {}
        for label, key in [("회신일", "reply_date"), ("첨부파일", "attachment"),
                            ("질의요지", "query"), ("회답", "answer"), ("이유", "reason")]:
            val = detail.get(key, "").strip()
            if val:
                block += f"\n  [{label}] {val}"
        lines.append(block)
    return "\n\n".join(lines)


def send_email(items: list[dict], excel_bytes: bytes | None = None) -> None:
    """
    환경변수에서 설정을 읽어 이메일 발송.

    필수 환경변수:
      FSS_EMAIL_SENDER     — 발신 Gmail 주소
      FSS_EMAIL_PASSWORD   — Gmail 앱 비밀번호 (16자리)
      FSS_EMAIL_RECIPIENTS — 수신자 이메일 (쉼표 구분, 여러 명 가능)

    excel_bytes: 첨부할 엑셀 파일 바이트 (None이면 첨부 생략)
    """
    sender = os.environ["FSS_EMAIL_SENDER"]
    password = os.environ["FSS_EMAIL_PASSWORD"]
    recipients_raw = os.environ["FSS_EMAIL_RECIPIENTS"]
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    if not items:
        print("신규 항목 없음 — 이메일 발송 생략")
        return

    today = date.today().strftime("%Y.%m.%d")
    subject = f"[FSS 알림] 비조치의견서·법령해석 신규 {len(items)}건 ({today})"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    # 텍스트·HTML 파트
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(_build_text(items), "plain", "utf-8"))
    alt.attach(MIMEText(_build_html(items), "html", "utf-8"))
    msg.attach(alt)

    # 엑셀 첨부
    if excel_bytes:
        filename = f"fss_items_{date.today().strftime('%Y%m%d')}.xlsx"
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(excel_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    attach_info = f" (엑셀 첨부 {len(excel_bytes):,}bytes)" if excel_bytes else ""
    print(f"이메일 발송 완료 → {recipients} ({len(items)}건){attach_info}")
