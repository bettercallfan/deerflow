import argparse
import json
from pathlib import Path

from adaptive_preprocess import AdaptiveDocumentPreprocessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = "/nfsdat1/home/tyxuslm/paddleocr3/预处理增强/input"
DEFAULT_OUTPUT_DIR = "/nfsdat1/home/tyxuslm/paddleocr3/预处理增强/output/input图片"


def process_input_folder(input_dir, output_dir, debug=False):
    processor = AdaptiveDocumentPreprocessor(debug=debug)
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.is_dir():
        raise ValueError(f"输入文件夹不存在: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    skipped = []

    for file_path in sorted(input_dir.rglob("*")):
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()
        if suffix not in processor.image_exts:
            skipped.append(
                {
                    "input_file": str(file_path),
                    "reason": f"暂不支持的文件类型: {suffix or '无扩展名'}",
                }
            )
            continue

        relative_parent = file_path.relative_to(input_dir).parent
        target_dir = output_dir / relative_parent
        target_dir.mkdir(parents=True, exist_ok=True)

        print(f"正在预处理: {file_path}")
        try:
            report = processor.process_file(file_path, target_dir)
            reports.append(report)
            print(f"完成: {report['output_file']}")
        except Exception as exc:
            skipped.append(
                {
                    "input_file": str(file_path),
                    "reason": str(exc),
                }
            )
            print(f"失败: {file_path}, 原因: {exc}")

    summary = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "processed_count": len(reports),
        "skipped_count": len(skipped),
        "processed": reports,
        "skipped": skipped,
    }

    summary_path = output_dir / "summary_report.json"
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    print(f"全部完成，成功 {len(reports)} 个，跳过/失败 {len(skipped)} 个")
    print(f"汇总报告: {summary_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="批量预处理 input 文件夹中的图片，并输出到 output/input图片。"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_DIR),
        help=f"输入文件夹，默认: {DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"输出文件夹，默认: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="是否打印每一步预处理算子",
    )

    args = parser.parse_args()
    process_input_folder(args.input, args.output, debug=args.debug)


if __name__ == "__main__":
    main()
