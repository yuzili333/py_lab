from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    file_path: Path
    size_bytes: int
    original_filename: str
    content_type: str

def _safe_ext(filename: str) -> str:
    #  取扩展名并转为小写
    return Path(filename).suffix.lower()

def validate_file_type_strict(
        filename:str,
        content_type: str,
        allowed_ext: set[str],
        allowed_mime: set[str],
) -> tuple[str, str]:
    """
    严格策略： 扩展名 & MIME类型都必须在白名单内
    """
    ext = _safe_ext(filename)
    mine = (content_type or "").lower()

    if not ext:
        raise ValueError("File extension is missing.")
    if ext not in allowed_ext:
        raise ValueError(f"File extension '{ext}' is not allowed.")
    if not mine:
        raise ValueError("MIME type is missing.")
    if mine not in allowed_mime:
        raise ValueError(f"MIME type '{mine}' is not allowed.")
    return ext, mine

async def save_upload_file_streaming(
        upload_file: UploadFile,
        upload_dir: str,
        max_bytes: int,
) -> StoredFile:
    """
    chunk 方式写入, 实时累计大小: 超过限制立刻终止并删除残留文件
    """

    Path(upload_dir).mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex
    original = upload_file.filename or "unnamed"
    ext = _safe_ext(original)

    outpath = str(Path(upload_dir) / f"{file_id}{ext}")

    written = 0
    try:
        with open(outpath, "wb") as f:
            while True:
                chunk = await upload_file.read(1024 * 1024)  # 1 MB
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(
                        f"File size exceeds the maximum allowed size of {max_bytes} bytes."
                    )
                f.write(chunk)
    except Exception:
        # 任何异常都需要清理残留文件
        try:
            if os.path.exists(outpath):
                os.remove(outpath)
        except Exception:
            pass
        raise

    return StoredFile(
        file_id=file_id,
        file_path=Path(outpath),
        size_bytes=written,
        original_filename=original,
        content_type=upload_file.content_type or "",
    )
