"""Format-specific document parsers."""

from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.parsers.text_parser import parse_csv, parse_txt
from app.parsers.xlsx_parser import parse_xlsx

PARSERS = {
    "application/pdf": parse_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": parse_docx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": parse_xlsx,
    "text/csv": parse_csv,
    "text/plain": parse_txt,
}
