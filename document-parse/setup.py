#!/usr/bin/env python3
"""PaddleOCR 模型安装脚本 — 自动安装依赖 + 下载官方模型到 model/ 目录。"""

import os
import subprocess
import sys
from pathlib import Path

# 代理配置（按需修改或注释掉）
os.environ.setdefault("http_proxy", "http://172.16.40.150:7890")
os.environ.setdefault("https_proxy", "http://172.16.40.150:7890")

MODEL_ROOT = Path(__file__).resolve().parent / "model"
MODEL_ROOT.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], desc: str, env_extra: dict | None = None) -> None:
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    print(f"  $ {' '.join(cmd)}")
    sys.stdout.flush()
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(cmd, cwd=MODEL_ROOT.parent, env=env)
    if result.returncode != 0:
        print(f"\n❌ 失败: {desc}")
        sys.exit(1)
    print(f"✅ 完成: {desc}")


def main():
    # ── 1. 创建虚拟环境 + 安装依赖 ──
    venv_dir = MODEL_ROOT.parent / ".venv"
    if not (venv_dir / "bin" / "python").exists():
        run([sys.executable, "-m", "venv", str(venv_dir)], "创建虚拟环境")

    pip_bin = str(venv_dir / "bin" / "pip")
    run([pip_bin, "install", "--upgrade", "pip"], "升级 pip")
    run([pip_bin, "install", "paddlepaddle", "paddleocr", "paddlex[ocr]"], "安装 PaddleOCR + PaddleX")

    # 后续用 venv 里的 python
    sys.executable = str(venv_dir / "bin" / "python")

    # ── 2. 首次运行 PaddleOCR，自动下载全部模型（PP-DocLayoutV3 + PaddleOCR-VL-1.5）──
    print(f"\n{'='*60}")
    print(f"  下载模型 PP-DocLayoutV3 + PaddleOCR-VL-1.5")
    print(f"{'='*60}")
    print(f"  (首次运行会自动下载，请耐心等待)")
    sys.stdout.flush()

    run(
        [sys.executable, "-c",
         "from paddleocr import PaddleOCRVL;"
         "p = PaddleOCRVL();"
         "print('OK')"],
        "下载 PaddleOCR 全部模型",
        env_extra={"PADDLEX_HOME": str(MODEL_ROOT)},
    )

    # ── 4. 打印结果 ──
    print(f"\n{'='*60}")
    print(f"  安装完成!")
    print(f"{'='*60}")
    print(f"  模型目录: {MODEL_ROOT}")
    if MODEL_ROOT.exists():
        for item in sorted(MODEL_ROOT.rglob("*")):
            if item.is_file():
                size_mb = item.stat().st_size / (1024 * 1024)
                print(f"    {item.relative_to(MODEL_ROOT)}  ({size_mb:.1f} MB)")

    print(f"\n  app.py 中请将模型路径改为:")
    print(f'  os.environ["PADDLEOCR_LAYOUT_MODEL_DIR"] = "{MODEL_ROOT}/PP-DocLayoutV3"')
    print(f'  os.environ["PADDLEOCR_VL_REC_MODEL_DIR"] = "{MODEL_ROOT}/PaddleOCR-VL-1.5"')


if __name__ == "__main__":
    main()
