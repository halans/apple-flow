from __future__ import annotations

import mimetypes
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


@dataclass(slots=True)
class ProcessedAttachment:
    filename: str
    mime_type: str
    source_path: str
    status: str
    extracted_text: str = ""
    detail: str = ""


class AttachmentProcessor:
    """Extract prompt-safe text from inbound attachment metadata."""

    def __init__(
        self,
        *,
        max_attachment_size_mb: int = 10,
        max_files_per_message: int = 6,
        max_text_chars_per_file: int = 6000,
        max_total_text_chars: int = 24000,
        enable_image_ocr: bool = True,
    ) -> None:
        self.max_attachment_size_bytes = max(1, int(max_attachment_size_mb)) * 1024 * 1024
        self.max_files_per_message = max(1, int(max_files_per_message))
        # Honor caller-provided limits; keep only a minimal safety floor.
        self.max_text_chars_per_file = max(1, int(max_text_chars_per_file))
        self.max_total_text_chars = max(1, int(max_total_text_chars))
        self.enable_image_ocr = bool(enable_image_ocr)

    def build_prompt_block(
        self,
        message_id: str,
        attachments: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, str]]]:
        _ = message_id  # reserved for future logging/caching
        if not attachments:
            return "", []

        remaining_chars = self.max_total_text_chars
        processed: list[ProcessedAttachment] = []
        limit_hit = len(attachments) > self.max_files_per_message

        for att in attachments[: self.max_files_per_message]:
            item = self._process_one(att, remaining_chars)
            extracted_len = len(item.extracted_text)
            if extracted_len > 0:
                remaining_chars = max(0, remaining_chars - extracted_len)
            processed.append(item)

        block = self._render_prompt_block(processed, limit_hit=limit_hit, remaining_chars=remaining_chars)
        metadata = [
            {
                "filename": item.filename,
                "mime_type": item.mime_type,
                "source_path": item.source_path,
                "status": item.status,
                "detail": item.detail,
            }
            for item in processed
        ]
        return block, metadata

    def _process_one(self, att: dict[str, Any], remaining_chars: int) -> ProcessedAttachment:
        filename = str(att.get("filename") or "unknown")
        mime = str(att.get("mime_type") or "application/octet-stream")
        path_str = str(att.get("path") or "").strip()
        if not path_str:
            return ProcessedAttachment(filename=filename, mime_type=mime, source_path="", status="missing_path")

        path = Path(path_str)
        if not path.exists() or not path.is_file():
            return ProcessedAttachment(
                filename=filename,
                mime_type=mime,
                source_path=path_str,
                status="missing_file",
            )

        try:
            size_bytes = path.stat().st_size
        except OSError as exc:
            return ProcessedAttachment(
                filename=filename,
                mime_type=mime,
                source_path=path_str,
                status="read_failed",
                detail=str(exc),
            )
        if size_bytes > self.max_attachment_size_bytes:
            return ProcessedAttachment(
                filename=filename,
                mime_type=mime,
                source_path=path_str,
                status="skipped_size_limit",
            )
        if remaining_chars <= 0:
            return ProcessedAttachment(
                filename=filename,
                mime_type=mime,
                source_path=path_str,
                status="skipped_total_text_limit",
            )

        extracted_text, status, detail = self._extract_text(path, mime)
        if not extracted_text:
            return ProcessedAttachment(
                filename=filename,
                mime_type=mime,
                source_path=path_str,
                status=status,
                detail=detail,
            )

        extracted_text = self._sanitize_text(extracted_text)
        allowed = min(self.max_text_chars_per_file, remaining_chars)
        if len(extracted_text) > allowed:
            extracted_text = extracted_text[:allowed].rstrip()
            status = "truncated"
        return ProcessedAttachment(
            filename=filename,
            mime_type=mime,
            source_path=path_str,
            status=status,
            extracted_text=extracted_text,
            detail=detail,
        )

    def _extract_text(self, path: Path, mime: str) -> tuple[str, str, str]:
        ext = path.suffix.lower()
        guess_mime = mimetypes.guess_type(path.name)[0] or ""
        effective_mime = mime if mime != "application/octet-stream" else guess_mime
        effective_mime = effective_mime.lower()

        if effective_mime.startswith("text/") or ext in {
            ".txt",
            ".md",
            ".markdown",
            ".csv",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".ini",
            ".toml",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".rb",
            ".go",
            ".rs",
            ".java",
            ".swift",
            ".c",
            ".cc",
            ".cpp",
            ".h",
            ".hpp",
            ".sh",
            ".sql",
            ".log",
        }:
            return self._extract_text_file(path)

        if effective_mime == "application/pdf" or ext == ".pdf":
            return self._extract_pdf(path)

        if effective_mime.startswith("image/") or ext in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".webp",
            ".tif",
            ".tiff",
            ".heic",
        }:
            return self._extract_image_ocr(path)

        if ext == ".docx":
            return self._extract_docx(path)
        if ext == ".pptx":
            return self._extract_pptx(path)
        if ext == ".xlsx":
            return self._extract_xlsx(path)

        return "", "unsupported_type", ""

    @staticmethod
    def _extract_text_file(path: Path) -> tuple[str, str, str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "ok", ""
        except OSError as exc:
            return "", "read_failed", str(exc)

    @staticmethod
    def _run_command(args: list[str]) -> tuple[str, str]:
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", str(exc)
        if proc.returncode != 0:
            return "", (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
        return proc.stdout or "", ""

    def _extract_pdf(self, path: Path) -> tuple[str, str, str]:
        tool = shutil.which("pdftotext")
        if not tool:
            return "", "pdf_extractor_unavailable", "pdftotext not installed"
        text, err = self._run_command([tool, "-q", str(path), "-"])
        if err:
            return "", "pdf_extract_failed", err
        if not text.strip():
            return "", "no_text_extracted", ""
        return text, "ok", ""

    def _extract_image_ocr(self, path: Path) -> tuple[str, str, str]:
        if not self.enable_image_ocr:
            return "", "ocr_disabled", ""
        tool = shutil.which("tesseract")
        if not tool:
            return "", "ocr_unavailable", "tesseract not installed"
        text, err = self._run_command([tool, str(path), "stdout"])
        if err:
            return "", "ocr_failed", err
        if not text.strip():
            return "", "no_text_extracted", ""
        return text, "ok", ""

    def _extract_docx(self, path: Path) -> tuple[str, str, str]:
        try:
            with zipfile.ZipFile(path) as zf:
                data = zf.read("word/document.xml")
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            return "", "parse_failed", str(exc)
        return self._extract_xml_text(data, tag_suffix="}t")

    def _extract_pptx(self, path: Path) -> tuple[str, str, str]:
        texts: list[str] = []
        try:
            with zipfile.ZipFile(path) as zf:
                slide_names = sorted(
                    name for name in zf.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                )
                for name in slide_names:
                    data = zf.read(name)
                    text, _status, _detail = self._extract_xml_text(data, tag_suffix="}t")
                    if text:
                        texts.append(text)
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            return "", "parse_failed", str(exc)
        joined = "\n\n".join(part for part in texts if part)
        if not joined.strip():
            return "", "no_text_extracted", ""
        return joined, "ok", ""

    def _extract_xlsx(self, path: Path) -> tuple[str, str, str]:
        try:
            with zipfile.ZipFile(path) as zf:
                shared_strings = self._xlsx_shared_strings(zf)
                values: list[str] = []
                worksheet_names = sorted(
                    name for name in zf.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")
                )
                for name in worksheet_names:
                    data = zf.read(name)
                    values.extend(self._xlsx_sheet_values(data, shared_strings))
        except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            return "", "parse_failed", str(exc)
        text = "\n".join(v for v in values if v.strip())
        if not text.strip():
            return "", "no_text_extracted", ""
        return text, "ok", ""

    @staticmethod
    def _extract_xml_text(data: bytes, tag_suffix: str) -> tuple[str, str, str]:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            return "", "parse_failed", str(exc)
        chunks: list[str] = []
        for elem in root.iter():
            if elem.tag.endswith(tag_suffix) and elem.text:
                chunks.append(elem.text)
        text = "\n".join(part.strip() for part in chunks if part and part.strip())
        if not text:
            return "", "no_text_extracted", ""
        return text, "ok", ""

    @staticmethod
    def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in zf.namelist():
            return []
        data = zf.read("xl/sharedStrings.xml")
        root = ET.fromstring(data)
        out: list[str] = []
        for si in root.iter():
            if not si.tag.endswith("}si"):
                continue
            parts: list[str] = []
            for child in si.iter():
                if child.tag.endswith("}t") and child.text:
                    parts.append(child.text)
            out.append("".join(parts))
        return out

    @staticmethod
    def _xlsx_sheet_values(data: bytes, shared_strings: list[str]) -> list[str]:
        root = ET.fromstring(data)
        values: list[str] = []
        for cell in root.iter():
            if not cell.tag.endswith("}c"):
                continue
            cell_type = (cell.attrib.get("t") or "").lower()
            value_text = ""
            if cell_type == "inlineStr":
                for child in cell.iter():
                    if child.tag.endswith("}t") and child.text:
                        value_text += child.text
            else:
                for child in cell:
                    if child.tag.endswith("}v") and child.text:
                        value_text = child.text
                        break
                if cell_type == "s":
                    try:
                        idx = int(value_text)
                        value_text = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                    except ValueError:
                        value_text = ""
            if value_text.strip():
                values.append(value_text.strip())
        return values

    @staticmethod
    def _sanitize_text(text: str) -> str:
        lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        compact_lines = [line for line in lines if line.strip()]
        return "\n".join(compact_lines).strip()

    @staticmethod
    def _render_prompt_block(
        processed: list[ProcessedAttachment],
        *,
        limit_hit: bool,
        remaining_chars: int,
    ) -> str:
        if not processed:
            return ""
        lines: list[str] = ["Attached files (processed):"]
        for item in processed:
            lines.append(f"- {item.filename} ({item.mime_type}) status={item.status}")
            if item.source_path:
                lines.append(f"  path: {item.source_path}")
            if item.detail:
                lines.append(f"  detail: {item.detail[:160]}")
            if item.status == "ocr_unavailable" and item.source_path:
                lines.append("  hint: OCR unavailable locally; analyze this image directly from its file path if multimodal is available.")
            if item.extracted_text:
                lines.append("  extracted_text:")
                lines.append(f"  {item.extracted_text}")
        if limit_hit:
            lines.append("- Additional attachments were skipped due to max-files limit.")
        if remaining_chars <= 0:
            lines.append("- Attachment text truncated due to max-total-text limit.")
        return "\n".join(lines)
