"""
Парсинг документов: PDF, DOCX, XLSX, TXT, изображения (OCR).
Возвращает унифицированный объект ParsedDocument.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedDocument:
    """Результат парсинга любого документа."""
    filename: str
    content_type: str
    text: str                          # весь извлечённый текст
    pages: list[str] = field(default_factory=list)   # текст по страницам
    tables: list[list[list[str]]] = field(default_factory=list)  # таблицы как 2D массивы
    meta: dict = field(default_factory=dict)          # доп. метаданные
    error: str | None = None


class DocumentParser:
    """
    Единая точка входа для парсинга любого поддерживаемого формата.
    """

    async def parse(self, content: bytes, filename: str, content_type: str) -> ParsedDocument:
        ext = Path(filename).suffix.lower()
        logger.info("document_parse_start", filename=filename, ext=ext, size=len(content))

        try:
            if ext == ".pdf":
                return await self._parse_pdf(content, filename, content_type)
            elif ext in (".doc", ".docx"):
                return await self._parse_docx(content, filename, content_type)
            elif ext in (".xls", ".xlsx"):
                return await self._parse_xlsx(content, filename, content_type)
            elif ext == ".txt":
                return await self._parse_txt(content, filename, content_type)
            elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
                return await self._parse_image(content, filename, content_type)
            else:
                return ParsedDocument(
                    filename=filename,
                    content_type=content_type,
                    text="",
                    error=f"Неподдерживаемый формат: {ext}",
                )
        except Exception as exc:
            logger.error("document_parse_error", filename=filename, error=str(exc))
            return ParsedDocument(
                filename=filename,
                content_type=content_type,
                text="",
                error=f"Ошибка при обработке файла: {exc}",
            )

    # ── PDF ───────────────────────────────────────────────────────────────────

    async def _parse_pdf(
        self, content: bytes, filename: str, content_type: str
    ) -> ParsedDocument:
        import pymupdf  # fitz

        doc = pymupdf.open(stream=content, filetype="pdf")
        pages: list[str] = []
        tables: list[list[list[str]]] = []

        for page in doc:
            page_text = page.get_text("text")
            pages.append(page_text)

            # Извлечение таблиц (если есть)
            try:
                for table in page.find_tables():
                    tables.append(table.extract())
            except Exception:
                pass  # таблицы не критичны

        doc.close()

        full_text = "\n\n".join(pages)
        return ParsedDocument(
            filename=filename,
            content_type=content_type,
            text=full_text,
            pages=pages,
            tables=tables,
            meta={"page_count": len(pages), "table_count": len(tables)},
        )

    # ── DOCX ──────────────────────────────────────────────────────────────────

    async def _parse_docx(
        self, content: bytes, filename: str, content_type: str
    ) -> ParsedDocument:
        from docx import Document

        doc = Document(io.BytesIO(content))
        paragraphs: list[str] = []
        tables: list[list[list[str]]] = []

        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text)

        for table in doc.tables:
            rows = []
            for row in table.rows:
                rows.append([cell.text.strip() for cell in row.cells])
            tables.append(rows)

        full_text = "\n".join(paragraphs)
        return ParsedDocument(
            filename=filename,
            content_type=content_type,
            text=full_text,
            pages=[full_text],   # DOCX не делится на страницы логически
            tables=tables,
            meta={
                "paragraph_count": len(paragraphs),
                "table_count": len(tables),
            },
        )

    # ── XLSX ──────────────────────────────────────────────────────────────────

    async def _parse_xlsx(
        self, content: bytes, filename: str, content_type: str
    ) -> ParsedDocument:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets_text: list[str] = []
        tables: list[list[list[str]]] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                row_values = [str(v) if v is not None else "" for v in row]
                if any(v.strip() for v in row_values):
                    rows.append(row_values)

            if rows:
                tables.append(rows)
                # Текстовое представление листа
                sheet_text = f"=== Лист: {sheet_name} ===\n"
                sheet_text += "\n".join("\t".join(r) for r in rows)
                sheets_text.append(sheet_text)

        wb.close()
        full_text = "\n\n".join(sheets_text)
        return ParsedDocument(
            filename=filename,
            content_type=content_type,
            text=full_text,
            pages=sheets_text,
            tables=tables,
            meta={"sheet_count": len(wb.sheetnames)},
        )

    # ── TXT ───────────────────────────────────────────────────────────────────

    async def _parse_txt(
        self, content: bytes, filename: str, content_type: str
    ) -> ParsedDocument:
        # Пробуем UTF-8, потом cp1251 (частый кодек в корп. среде)
        for encoding in ("utf-8", "cp1251", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = content.decode("utf-8", errors="replace")

        return ParsedDocument(
            filename=filename,
            content_type=content_type,
            text=text,
            pages=[text],
            meta={"encoding": encoding, "char_count": len(text)},
        )

    # ── Изображения (OCR) ────────────────────────────────────────────────────

    async def _parse_image(
        self, content: bytes, filename: str, content_type: str
    ) -> ParsedDocument:
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(io.BytesIO(content))
            # Русский + английский OCR
            text = pytesseract.image_to_string(image, lang="rus+eng")
            return ParsedDocument(
                filename=filename,
                content_type=content_type,
                text=text.strip(),
                pages=[text.strip()],
                meta={
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "ocr": True,
                },
            )
        except ImportError:
            return ParsedDocument(
                filename=filename,
                content_type=content_type,
                text="",
                error="OCR недоступен: pytesseract не установлен",
            )


# Синглтон
_parser: DocumentParser | None = None


def get_document_parser() -> DocumentParser:
    global _parser
    if _parser is None:
        _parser = DocumentParser()
    return _parser
