from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()


def ensure_storage_dirs() -> None:
    (settings.storage_root / settings.upload_dir).mkdir(parents=True, exist_ok=True)
    (settings.storage_root / settings.artifacts_dir).mkdir(parents=True, exist_ok=True)


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name)


def save_upload_file(upload_file: UploadFile, tenant_id: UUID, scan_id: UUID) -> tuple[str, int]:
    ensure_storage_dirs()
    tenant_dir = settings.storage_root / settings.upload_dir / str(tenant_id) / str(scan_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)

    file_name = _safe_name(upload_file.filename or "upload.bin")
    dest = tenant_dir / file_name

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)

    upload_file.file.seek(0)
    return str(dest), size


def write_artifact(subdir: str, filename: str, content: str) -> str:
    ensure_storage_dirs()
    artifact_dir = settings.storage_root / settings.artifacts_dir / subdir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def read_artifact(path: str) -> bytes:
    return Path(path).read_bytes()
