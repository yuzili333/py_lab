from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from py_lab.data_pipeline import basic_clean, load_csv, save_numeric_hist, summarize
from py_lab.logging_utils import RequestIdFilter, log_exception, log_json, setup_logging
from py_lab.model_store import reload_iforest
from py_lab.schemas import (
    AnalyzeAcceptedResponse,
    AnalyzeExcelResponse,
    AnalyzeStatusResponse,
    CleanupResponse,
    ErrorResponse,
    ReloadModelResponse,
    SummaryModel,
)
from py_lab.settings import settings
from py_lab.signing import constant_time_eq, sign
from py_lab.storage import save_upload_file_streaming, validate_file_type_strict

_job_sem = threading.BoundedSemaphore(value=settings.max_concurrent_jobs)

app = FastAPI(title="py-lab API", version="0.1.0")

RESULTS_DIR = Path(settings.out_dir) / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/results",
    StaticFiles(directory=str(RESULTS_DIR)),
    name="results")

class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None)
        return True

logging.basicConfig(level=logging.INFO)
logging.getLogger().addFilter(RequestIDFilter())
setup_logging(settings.log_level)
logger = logging.getLogger("py_lab.api")

BASE_OUT_DIR = Path(settings.out_dir) / "requests"
MAX_BYTES = settings.max_bytes  # 10 MB
RESULT_TTL_SECONDS = settings.result_ttl_seconds  # 24 hours

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

def status_path(request_id:str) -> Path:
    return RESULTS_DIR / request_id / "status.json"

def write_status(request_id:str, payload:dict) -> None:
    p = status_path(request_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **payload,
        "request_id": request_id,
        "updated_at": _now_iso(),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def read_status(request_id:str) -> dict:
    p = status_path(request_id)
    if not p.exists():
        raise None
    return json.loads(p.read_text(encoding="utf-8"))

def absolute_url(path:str) -> str:
    if not settings.base_url:
        return path
    return settings.base_url.rstrip("/") + path

def _required_valid_signature(request_id:str, filename:str, exp:int,signature:str) -> None:
    if not settings.download_signing_key:
        return # 未启用签名，开发模式

    now = int(time.time())
    if exp < now:
        raise HTTPException(status_code=403, detail="URL has expired")

    message = f"{request_id}:{filename}:{exp}"
    expected = sign(settings.download_signing_key, message)
    if not constant_time_eq(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

def make_download_url(req_id:str, filename:str) -> str:
    exp = int(time.time()) + settings.download_url_ttl_seconds
    if not settings.download_signing_key:
        # 开发模式返回静态连接
        return absolute_url(f"/results/{req_id}/{filename}")

    message = f"{req_id}:{filename}:{exp}"
    sig = sign(settings.download_signing_key, message)
    return absolute_url(f"/download/{req_id}/{filename}?exp={exp}&sig={sig}")

@app.get("/requests/{request_id}/events")
async def request_event(request_id:str) -> StreamingResponse:
    async def event_generator():
        last = None

        while True:
            st = read_status(request_id)

            if st is None:
                yield "event: error\ndata: {\"detail\":\"Not found\"}\n\n"
                return

            cur = json.dumps(st,ensure_ascii=False, separators=(",", ":"))
            if cur != last:
                last = cur
                yield f"event: status\ndata: {cur}\n\n"

                if st.get("status") in ("done", "failed"):
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get(
    "/requests/{request_id}/status",
    response_model=AnalyzeStatusResponse,
    responses={404: {"model": ErrorResponse, "description": "Status Not Found"}})
def get_status(request_id:str) -> AnalyzeStatusResponse:
    st = read_status(request_id)
    if st is None:
        raise HTTPException(status_code=404, detail="Status not found")
    return AnalyzeStatusResponse(**st)

@app.api_route(
    "/download/{request_id}/{filename}",
    methods=["GET", "HEAD"],
    responses={
        200: {"content": {"image/png": {}}, "description": "File Download"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "File Not Found"}
    },
)
def download_file(request_id:str, filename:str, exp: int = Query(...), sig: str = Query(...)):
    if filename not in ('hist.png', 'summary.json'):
        raise HTTPException(status_code=404, detail="File not found with suffix")

    _required_valid_signature(request_id, filename, exp, sig)

    p = BASE_OUT_DIR / request_id / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {p}")

    media_type = "image/png" if filename.endswith(".png") else "application/json"
    return FileResponse(path=str(p), media_type=media_type, filename=filename)

@app.get(
    "/results/{request_id}/summary.json",
    response_model=SummaryModel,
    responses={404: {"model": ErrorResponse, "description": "Result Not Found"}},)
def get_summary(request_id:str) -> JSONResponse:
    p = BASE_OUT_DIR / request_id / "summary.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return JSONResponse(content=json.loads(p.read_text(encoding="utf-8")))

@app.get(
    "/results/{request_id}/hist.png",
    responses={
        200: {"content": {"image/png": {}}, "description": "Histogram PNG"},
        404: {"model": ErrorResponse, "description": "Histogram Not Found"}},)
def get_hist(request_id:str) -> FileResponse:
    p = BASE_OUT_DIR / request_id / "hist.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Histogram not found")
    return FileResponse(path=str(p), media_type="image/png", filename="hist.png")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}



@app.post(
    "/analyze",
    response_model=AnalyzeAcceptedResponse,
    status_code=202,
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        413: {"model": ErrorResponse, "description": "Payload Too Large"}},)
async def analyze_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(..., description="CSV file to analyze"),
        hist: str | None = Form(None, description="Numeric column for histogram"),
        top_k: int = Form(5, ge=1, le=50,description="Top-K anomalies")
) -> AnalyzeAcceptedResponse:
        req_logger = logging.getLogger("py_lab.job")
        

        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=404, detail="Only CSV files are supported")

        req_id = secrets.token_urlsafe(24)
        req_logger.addFilter(RequestIdFilter(req_id))

        work_dir = BASE_OUT_DIR / req_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # 读文件（带 MAX_BYTES 限制）
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File too large(max 10MB)")

        (work_dir / "input.csv").write_bytes(content)

        write_status(req_id, {"status": "queued"})

        def run_analyze_job(req_id: str, hist:str | None, top_k:int) -> None:
            with _job_sem:
                write_status(req_id, {"status": "running",})

                t0 = time.perf_counter()
                marks:dict[str, float] = {}
                def mark(name:str) -> None:
                    marks[name] = round((time.perf_counter() - t0) * 1000, 2)  # ms

                try:
                    work_dir = BASE_OUT_DIR/ req_id
                    work_dir.mkdir(parents=True, exist_ok=True)

                    csv_path = work_dir / "input.csv"

                    # 1) 读取输入 + 清洗
                    df = basic_clean(load_csv(csv_path))
                    mark("data_load_clean")

                    # 2) summary
                    summary = summarize(df)
                    (work_dir / "summary.json").write_text(
                        json.dumps(
                            {
                                "rows": summary.rows,
                                "cols": summary.cols,
                                "columns": summary.columns},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        encoding="utf-8",
                    )
                    mark("save_summary")

                    # 3) anomaly（加载模型推理）
                    # bundle = load_iforest(settings.model_path)
                    # anom = score_anomalies_with_model(df, bundle=bundle, top_k=top_k)
                    # 你若要把 anomaly 也落盘，可写 anomaly.json（可选）
                    mark("anomaly_score")

                    # 4) hist（可选）
                    if hist:
                        png_path = work_dir / "hist.png"
                        save_numeric_hist(df, hist, png_path)
                        # result["hist_url"] = make_download_url(req_id, "hist.png")
                    mark('hist')

                    # 5) 生成下载/静态 URL
                    hist_url = make_download_url(req_id, "hist.png") if hist else None
                    summary_url = make_download_url(req_id, "summary.json")

                    mark("complete")

                    write_status(
                        req_id,
                        {
                            "status": "done",
                            "summary_url": summary_url,
                            "hist_url": hist_url,
                            "timing_ms": marks,
                        },
                    )

                    # 结构化日志（你已有 log_json）
                    log_json(
                        req_logger,
                        logging.INFO,
                        "analyze_completed",
                        request_id=req_id,
                        time_ms=marks)

                except Exception as e:
                    write_status(req_id, {
                        "status": "failed",
                        "error": f"{type(e).__name__}: {e}",})
                    log_exception(req_logger, e, "analyze_job_failure", request_id=req_id)
        
        background_tasks.add_task(run_analyze_job,req_id, hist, top_k)

        return AnalyzeAcceptedResponse(request_id=req_id, status_url=f"/requests/{req_id}/status")

def cleanup_expired_requests(base_dir:Path,ttl_seconds:int) -> int:
    now = time.time()
    removed = 0

    if not base_dir.exists():
        return 0

    for subdir in base_dir.iterdir():
        if not subdir.is_dir():
            continue
        try:
            mtime = subdir.stat().st_mtime
        except FileNotFoundError:
            continue

        if now - mtime > ttl_seconds:
            shutil.rmtree(subdir, ignore_errors=True)
            removed += 1

    return removed

@app.post(
    "/admin/cleanup",
    response_model=CleanupResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },)
def admin_cleanup(x_admin_token: str | None = Header(default = None)) -> dict[str, int]:
    if settings.admin_token:
        if not x_admin_token or x_admin_token != settings.admin_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

    removed = cleanup_expired_requests(BASE_OUT_DIR, RESULT_TTL_SECONDS)
    return {"removed": removed}

@app.post(
    "/admin/reload-model",
    response_model=ReloadModelResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Model Load Failed"},
    }
)
def admin_reload_model(x_admin_token: str | None = Header(default = None)) -> ReloadModelResponse:
    if settings.admin_token:
        if not x_admin_token or x_admin_token != settings.admin_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        bundle = reload_iforest(settings.model_path)
    except Exception as e:
        logger.error("Failed to load model: %s", e)
        raise HTTPException(status_code=500, detail="Model load failed")

    return ReloadModelResponse(
        model_path=settings.model_path,
        feature_columns=bundle.feature_columns)

@app.post(
    "/analyze_excel",
    response_model=AnalyzeExcelResponse,
    status_code=202,
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        413: {"model": ErrorResponse, "description": "Payload Too Large"}},)
async def analyze_excel_upload(
        file: UploadFile = File(..., description="Excel file to analyze"),
) -> AnalyzeExcelResponse:
        if not file.filename or not (file.filename.lower()
                                     .endswith(".xls") or file.filename.lower().endswith(".xlsx")):
            raise HTTPException(status_code=404, detail="Only Excel files are supported")

        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File too large(max 10MB)")

        temp_path = Path("/tmp") / f"{secrets.token_urlsafe(16)}_{file.filename}"
        temp_path.write_bytes(content)

        try:
            from py_lab.analyze_excel import analyze_excel
            sheets = analyze_excel(str(temp_path))
            logger.info(f"Successfully analyzed excel file: {sheets}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to analyze excel file: {e}")
        finally:
            if temp_path.exists():
                temp_path.unlink()

        return AnalyzeExcelResponse(sheets=sheets)


@app.post("files/upload")
async def upload_file(file: UploadFile = File(...)):
    # 1、严格校验 扩展名 + MIME
    try:
        validate_file_type_strict(
            filename=file.filename or "",
            content_type=file.content_type,
            allowed_ext=settings.allowed_upload_extensions,
            allowed_mime=settings.allowed_upload_mimes,
        )
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))

    # 2、保存文件（流式写入 + 大小限制）
    try:
        stored = await save_upload_file_streaming(
            upload = file,
            upload_dir=settings.upload_dir,
            max_bytes=settings.max_upload_size_bytes,
        )
    except OverflowError:
        raise HTTPException(
            status_code=413,
            detail=f"file_too_large:max={settings.max_upload_size_bytes} bytes"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed_to_save_file:{type(e).__name__}")

    return JSONResponse({
        "file_id": stored.file_id,
        "original_filename": stored.original_filename,
        "content_type": stored.content_type,
        "size_bytes": stored.size_bytes,
        "saved_path": stored.saved_path,
        "max_allowed_size": settings.max_upload_size_bytes,
    })
