from pathlib import Path
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

def extract_text_from_pdf(pdf_path: str) -> dict:
    path = Path(pdf_path)
    if not path.exists(): return {"success": False, "error": "File not found"}
    if not HAS_PDFPLUMBER: return {"success": False, "error": "pdfplumber not installed"}
    try:
        with pdfplumber.open(path) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(pages_text)
            page_count = len(pdf.pages)
            quality = "low" if len(full_text.strip()) < 100 else ("fair" if len(full_text.strip()) / page_count < 50 else "good")
            return {"success": True, "text": full_text, "page_count": page_count, "quality": quality, "method": "pdfplumber"}
    except Exception as e:
        return {"success": False, "error": str(e)}
