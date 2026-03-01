from __future__ import annotations

import os
from dataclasses import dataclass


def _get_init(name:str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return int(v)

def _parse_csv_set(value: str) -> frozenset[str]:
    return frozenset(item.strip() for item in value.split(",") if item.strip())

@dataclass(frozen=True)
class Settings:
    out_dir: str = os.getenv("OUTDIR", "out")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    max_bytes: int = _get_init("MAX_BYTES", 10 * 1024 * 1024)
    result_ttl_seconds: int = _get_init("RESULT_TTL_SECONDS", 24 * 60 * 60)
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    base_url: str = os.getenv("BASE_URL", "")
    download_signing_key: str = os.getenv("DOWNLOAD_SIGNING_KEY", "")
    download_url_ttl_seconds: int = _get_init("DOWNLOAD_URL_TTL_SECONDS", 60 * 60)
    model_path: str = os.getenv("MODEL_PATH", "models/iforest.pkl")
    max_concurrent_jobs = os.getenv("MAX_CONCURRENT_JOBS", 2)

    max_upload_size: int = _get_init("MAX_UPLOAD_SIZE", 10 * 1024 * 1024) # 10 MB
    allowed_mime_types: frozenset[str] = _parse_csv_set(os.getenv(
        "ALLOWED_MIME_TYPES",
        "image/png,image/jpeg,application/pdf,text/plain"
        ))
    allowed_extensions: frozenset[str] = _parse_csv_set(os.getenv(
        "ALLOWED_EXTENSIONS",
        ".png,.jpg,.jpeg,.pdf,.txt"
        ))
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")

settings = Settings()
