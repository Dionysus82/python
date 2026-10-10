"""Upload checks. Document text cannot change these rules."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.domain.banner import SYNTHETIC_BANNER

ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
}
BLOCKED = {".exe", ".xlsm", ".docm", ".js", ".bat", ".cmd", ".ps1", ".dll", ".sh", ".msi", ".com"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class ValidationResult:
    accepted: bool
    mime_type: str | None
    reason: str | None
    checksum: str | None
    safe_filename: str | None
    quarantine: bool = False


def safe_filename(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", PathName(name))
    return cleaned[:180] or "document.bin"


def PathName(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


def _signature_ok(extension: str, data: bytes) -> bool:
    if extension == ".pdf":
        return data.startswith(b"%PDF")
    if extension in {".docx", ".xlsx"}:
        return data.startswith(b"PK")
    if extension in {".csv", ".txt"}:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in data[:200]
    return False


def validate_upload(
    filename: str,
    data: bytes,
    *,
    max_bytes: int,
    allow_macros: bool,
    demo_mode: bool,
    extracted_text: str | None = None,
) -> ValidationResult:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in BLOCKED and not (allow_macros and extension == ".xlsm"):
        return ValidationResult(False, None, "The file type is not permitted.", None, None, True)
    if extension not in ALLOWED:
        return ValidationResult(False, None, "The file format is not supported.", None, None, True)
    if len(data) > max_bytes:
        return ValidationResult(False, None, "The file exceeds the configured size limit.", None, None, True)
    if not data:
        return ValidationResult(False, None, "The file is empty.", None, None, True)
    if data.startswith(b"MZ"):
        return ValidationResult(False, None, "Executable content is not permitted.", None, None, True)
    if not _signature_ok(extension, data):
        return ValidationResult(
            False,
            None,
            "The file extension does not match the file signature, or the file is corrupted.",
            None,
            None,
            True,
        )
    text = extracted_text or ""
    if "SYNTHETIC" not in text and SYNTHETIC_BANNER not in text:
        if not demo_mode:
            return ValidationResult(
                False,
                None,
                "The document has no synthetic-data declaration. Production-looking uploads are refused "
                "unless a hackathon administrator has enabled controlled demonstration mode.",
                None,
                None,
                True,
            )
    checksum = hashlib.sha256(data).hexdigest()
    return ValidationResult(True, ALLOWED[extension], None, checksum, safe_filename(filename), False)
