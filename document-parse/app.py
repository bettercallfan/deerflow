import importlib.util
import os
import shutil
import uuid
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parent / "model"
os.environ.setdefault("PADDLEOCR_LAYOUT_MODEL_DIR", str(MODEL_ROOT / "PP-DocLayoutV3"))
os.environ.setdefault("PADDLEOCR_VL_REC_MODEL_DIR", str(MODEL_ROOT / "PaddleOCR-VL-1.5"))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


ROOT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT_DIR / "uploads"
RESULT_DIR = ROOT_DIR / "output" / "frontend"
PREPROCESS_PATH = ROOT_DIR / "pre" / "adaptive_preprocess.py"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
ALLOWED_EXTS = IMAGE_EXTS | PDF_EXTS

os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

app = FastAPI(title="PaddleOCR3 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ocr_pipeline = None
_preprocessor_cls = None


def load_preprocessor_cls():
    global _preprocessor_cls
    if _preprocessor_cls is not None:
        return _preprocessor_cls

    spec = importlib.util.spec_from_file_location("adaptive_preprocess", PREPROCESS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载预处理脚本")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _preprocessor_cls = module.AdaptiveDocumentPreprocessor
    return _preprocessor_cls


def get_ocr_pipeline():
    global _ocr_pipeline
    if _ocr_pipeline is not None:
        return _ocr_pipeline

    from paddleocr import PaddleOCRVL

    kwargs = {}
    layout_model_dir = os.getenv("PADDLEOCR_LAYOUT_MODEL_DIR")
    vl_model_dir = os.getenv("PADDLEOCR_VL_REC_MODEL_DIR")
    vl_backend = os.getenv("PADDLEOCR_VL_REC_BACKEND")
    vl_server_url = os.getenv("PADDLEOCR_VL_REC_SERVER_URL")

    if layout_model_dir:
        kwargs["layout_detection_model_dir"] = layout_model_dir
    if vl_model_dir:
        kwargs["vl_rec_model_dir"] = vl_model_dir
    if vl_backend:
        kwargs["vl_rec_backend"] = vl_backend
    if vl_server_url:
        kwargs["vl_rec_server_url"] = vl_server_url

    _ocr_pipeline = PaddleOCRVL(**kwargs)
    return _ocr_pipeline


def safe_filename(name: str) -> str:
    stem = Path(name).stem.replace(" ", "_") or "upload"
    suffix = Path(name).suffix.lower()
    safe_stem = "".join(ch for ch in stem if ch.isalnum() or ch in ("-", "_"))
    return f"{safe_stem or 'upload'}{suffix}"


def newest_markdown(output_dir: Path) -> Path | None:
    markdown_files = list(output_dir.rglob("*.md"))
    if not markdown_files:
        return None
    return max(markdown_files, key=lambda item: item.stat().st_mtime)


def ensure_job_id(job_id: str) -> None:
    if len(job_id) != 32 or not all(ch in "0123456789abcdef" for ch in job_id):
        raise HTTPException(status_code=404, detail="文件不存在")


def save_markdown_result(pipeline, input_path: Path, output_dir: Path) -> Path:
    output = pipeline.predict(input=str(input_path))
    pages_res = list(output)

    if hasattr(pipeline, "restructure_pages") and pages_res:
        try:
            output = pipeline.restructure_pages(
                pages_res,
                merge_tables=True,
                relevel_titles=True,
                concatenate_pages=True,
            )
        except TypeError:
            output = pipeline.restructure_pages(pages_res)
    else:
        output = pages_res

    for res in output:
        res.save_to_markdown(save_path=str(output_dir))

    md_path = newest_markdown(output_dir)
    if md_path is None:
        raise RuntimeError("解析完成但没有生成 Markdown 文件")
    return md_path


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/parse")
async def parse_document(
    file: UploadFile = File(...),
    preprocess: bool = Form(False),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="仅支持图片和 PDF 文件")

    job_id = uuid.uuid4().hex
    job_upload_dir = UPLOAD_DIR / job_id
    job_output_dir = RESULT_DIR / job_id
    job_preprocess_dir = job_output_dir / "preprocess"
    job_parse_dir = job_output_dir / "parse"

    job_upload_dir.mkdir(parents=True, exist_ok=True)
    job_preprocess_dir.mkdir(parents=True, exist_ok=True)
    job_parse_dir.mkdir(parents=True, exist_ok=True)

    original_name = safe_filename(file.filename or f"upload{suffix}")
    upload_path = job_upload_dir / original_name

    with upload_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)

    parse_input = upload_path
    processed_url = None
    preprocess_report = None
    warnings = []

    if preprocess and suffix in IMAGE_EXTS:
        try:
            preprocessor = load_preprocessor_cls()(debug=False)
            preprocess_report = preprocessor.process_file(upload_path, job_preprocess_dir)
            parse_input = Path(preprocess_report["output_file"])
            processed_url = f"/api/result-file/{job_id}/preprocess/{parse_input.name}"
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"图片预处理失败: {exc}") from exc
    elif preprocess and suffix in PDF_EXTS:
        warnings.append("PDF 暂不支持预处理，已直接进入文档解析。")

    try:
        md_path = save_markdown_result(get_ocr_pipeline(), parse_input, job_parse_dir)
        markdown = md_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档解析失败: {exc}") from exc

    return {
        "jobId": job_id,
        "filename": file.filename,
        "isImage": suffix in IMAGE_EXTS,
        "preprocessed": bool(processed_url),
        "processedImageUrl": processed_url,
        "markdown": markdown,
        "markdownDownloadUrl": f"/api/download-md/{job_id}",
        "preprocessReport": preprocess_report,
        "warnings": warnings,
    }


@app.get("/api/result-file/{job_id}/{section}/{filename}")
def result_file(job_id: str, section: str, filename: str):
    ensure_job_id(job_id)
    if section not in {"preprocess", "parse"}:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = RESULT_DIR / job_id / section / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)


@app.get("/api/download-md/{job_id}")
def download_markdown(job_id: str):
    ensure_job_id(job_id)
    parse_dir = RESULT_DIR / job_id / "parse"
    md_path = newest_markdown(parse_dir)
    if md_path is None:
        raise HTTPException(status_code=404, detail="Markdown 文件不存在")
    return FileResponse(
        md_path,
        media_type="text/markdown; charset=utf-8",
        filename=md_path.name,
    )
