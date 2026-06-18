import os
import sys
import subprocess
from pathlib import Path


# =========================
# 1. 代理配置
# =========================
PROXY = "http://172.16.40.22:7890"

os.environ["http_proxy"] = PROXY
os.environ["https_proxy"] = PROXY
os.environ["HTTP_PROXY"] = PROXY
os.environ["HTTPS_PROXY"] = PROXY


# =========================
# 2. 下载目录
# =========================
MODEL_ROOT = Path("/home/chenruofan/imiss-deer-flow/document-parse/model")
MODEL_ROOT.mkdir(parents=True, exist_ok=True)


# =========================
# 3. 自动安装 huggingface_hub
# =========================
def ensure_package():
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("huggingface_hub 未安装，正在安装...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-U", "huggingface_hub", "hf_xet"]
        )


ensure_package()

from huggingface_hub import snapshot_download


# =========================
# 4. 下载函数
# =========================
def download_model(repo_id: str, local_name: str):
    local_dir = MODEL_ROOT / local_name
    local_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"开始下载: {repo_id}")
    print(f"保存到: {local_dir}")
    print("=" * 80)

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        proxies={
            "http": PROXY,
            "https": PROXY,
        },
    )

    print(f"下载完成: {repo_id}")
    print(f"本地目录: {local_dir}")


def main():
    # PaddleOCR-VL 文档理解模型
    download_model(
        repo_id="PaddlePaddle/PaddleOCR-VL-1.5",
        local_name="PaddleOCR-VL-1.5",
    )

    # 版面分析模型
    download_model(
        repo_id="PaddlePaddle/PP-DocLayoutV3",
        local_name="PP-DocLayoutV3",
    )

    print("\n全部模型下载完成。当前 model 目录结构：")
    for item in MODEL_ROOT.iterdir():
        print(" -", item)

    print("\n关键文件检查：")

    vl_weight = MODEL_ROOT / "PaddleOCR-VL-1.5" / "model.safetensors"
    if vl_weight.exists():
        print(f"[OK] 找到 VL 权重文件: {vl_weight}")
        print(f"     大小: {vl_weight.stat().st_size / 1024 / 1024 / 1024:.2f} GB")
    else:
        print(f"[WARN] 没找到: {vl_weight}")

    layout_dir = MODEL_ROOT / "PP-DocLayoutV3"
    if layout_dir.exists() and any(layout_dir.iterdir()):
        print(f"[OK] 找到版面模型目录: {layout_dir}")
    else:
        print(f"[WARN] PP-DocLayoutV3 目录为空或不存在: {layout_dir}")


if __name__ == "__main__":
    main()