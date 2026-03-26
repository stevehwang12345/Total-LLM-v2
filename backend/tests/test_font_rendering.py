import os
import tempfile
import pytest
from pathlib import Path


def test_font_registration():
    """NanumGothic 폰트 등록 함수 동작 확인."""
    from total_llm.services.report_service import register_korean_fonts
    font_name = register_korean_fonts()
    # 환경에 따라 NanumGothic 또는 Helvetica(폴백)
    assert font_name in ("NanumGothic", "Helvetica")


def test_korean_styles():
    """get_korean_styles 반환 구조 확인."""
    from total_llm.services.report_service import register_korean_fonts, get_korean_styles
    font = register_korean_fonts()
    styles = get_korean_styles(font)
    for key in ("title", "heading1", "heading2", "body", "table_header", "table_cell", "footer"):
        assert key in styles


@pytest.mark.skipif(
    not os.path.exists("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    reason="NanumGothic font not installed (Docker only)"
)
def test_korean_pdf_rendering():
    """한글 텍스트가 PDF에 정상 렌더링되는지 확인 (pypdf 텍스트 추출)."""
    from reportlab.pdfgen import canvas
    from total_llm.services.report_service import register_korean_fonts
    from pypdf import PdfReader
    
    font = register_korean_fonts()
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    
    try:
        c = canvas.Canvas(pdf_path)
        c.setFont(font, 12)
        c.drawString(50, 750, "관제일지 테스트")
        c.drawString(50, 730, "보안 사건보고서")
        c.save()
        
        reader = PdfReader(pdf_path)
        text = reader.pages[0].extract_text()
        assert "관제일지" in text or "보안" in text, f"Korean text not found in PDF. Got: {text[:200]}"
    finally:
        os.unlink(pdf_path)
