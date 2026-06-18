# adaptive_preprocess.py
import os
import cv2
import json
import math
import argparse
import numpy as np
from pathlib import Path


class AdaptiveDocumentPreprocessor:
    """
    文档解析预处理自适应路由模块 V1
    当前支持：png / jpg / jpeg / bmp / tif / tiff
    暂不支持 PDF，但预留接口
    """

    def __init__(self, debug=False):
        self.debug = debug

        self.image_exts = {
            ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"
        }

    # =========================
    # 入口函数
    # =========================
    def process_file(self, input_path, output_dir):
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        suffix = input_path.suffix.lower()

        if suffix in self.image_exts:
            return self.process_image(input_path, output_dir)

        elif suffix == ".pdf":
            raise NotImplementedError(
                "PDF 处理接口已预留，当前版本先不支持。后续可接 PyMuPDF/pdf2image。"
            )

        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

    # =========================
    # 图片处理主流程
    # =========================
    def process_image(self, image_path, output_dir):
        image = cv2.imread(str(image_path))

        if image is None:
            raise ValueError(f"图片读取失败: {image_path}")

        features = self.extract_features(image)

        route = self.route(features)

        processed = self.execute_pipeline(image, route, features)

        output_path = output_dir / f"{image_path.stem}_processed.png"
        report_path = output_dir / f"{image_path.stem}_route_report.json"

        cv2.imwrite(str(output_path), processed)

        report = {
            "input_file": str(image_path),
            "output_file": str(output_path),
            "features": features,
            "route": route
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # =========================
    # 特征提取
    # =========================
    def extract_features(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape[:2]

        blur_score = self.estimate_blur(gray)
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        skew_angle = self.estimate_skew_angle_by_text_boxes(gray)
        edge_density = self.estimate_edge_density(gray)
        table_score, horizontal_score, vertical_score = self.estimate_table_score(gray)
        shadow_score = self.estimate_shadow_score(gray)

        features = {
            "width": int(w),
            "height": int(h),
            "blur_score": round(float(blur_score), 4),
            "brightness": round(float(brightness), 4),
            "contrast": round(float(contrast), 4),
            "skew_angle": round(float(skew_angle), 4),
            "edge_density": round(float(edge_density), 4),
            "table_score": round(float(table_score), 4),
            "horizontal_score": round(float(horizontal_score), 4),
            "vertical_score": round(float(vertical_score), 4),
            "shadow_score": round(float(shadow_score), 4),

            # 简单规则标签
            "is_blurry": bool(
                blur_score < 80 
            ),
            "is_dark": bool(brightness < 90),
            "is_low_contrast": bool(contrast < 45),
            "is_skewed": bool(abs(skew_angle) > 4.0),
            "is_low_res_dense_text": bool(edge_density > 0.10),
            "maybe_table": bool(table_score > 0.06
                                and horizontal_score > 0.050
                                and vertical_score > 0.004
                                and h > 150),
            "maybe_shadow": bool(shadow_score > 35),
            "small_image": bool((w+h) < 1600)
        }

        return features

    # =========================
    # 自适应路由规则
    # =========================
    def route(self, features):
        pipeline = []

        # 1. 基础灰度化一般都需要
        pipeline.append("to_gray")

        # 2. 阴影处理
        if features["maybe_shadow"]:
            pipeline.append("remove_shadow")
            pipeline.append("recheck_deskew")
        else:
            if features["is_skewed"]:
                pipeline.append("deskew")
        # 4. 亮度过低
        if features["is_dark"]:
            pipeline.append("gamma_correct")

        # 5. 对比度低
        if features["is_low_contrast"]:
            pipeline.append("clahe")

        # 6. 模糊
        if features["is_blurry"]:
            pipeline.append("sharpen")

        # 7. 表格页尽量保护线条
        if features["maybe_table"]:
            pipeline.append("table_line_enhance")
            pipeline.append("light_denoise")
        #else:
         #   pipeline.append("denoise")

        if features["small_image"]:
            pipeline.append("upscale")
        
        pipeline.append("sharpen")

        # # 8. 二值化策略
        # # 阴影明显或光照不均，优先自适应阈值
        # if features["maybe_shadow"] or features["is_low_contrast"]:
        #     pipeline.append("adaptive_binarize")
        # else:
        #     pipeline.append("otsu_binarize")

        # 9. 小噪声清理
        #if not features["maybe_table"]:
        #    pipeline.append("morph_clean")

        return pipeline

    # =========================
    # 执行处理链
    # =========================
    def execute_pipeline(self, image, pipeline, features):
        current = image.copy()

        for op in pipeline:
            if self.debug:
                print(f"执行算子: {op}")

            if op == "to_gray":
                current = self.to_gray(current)

            elif op == "deskew":
                current = self.deskew(current, features["skew_angle"])

            elif op == "remove_shadow":
                current = self.remove_shadow(current)
            
            elif op == "recheck_deskew":
                gray = self.to_gray(current)
                new_angle = self.estimate_skew_angle(gray)

                if self.debug:
                    print(f"去阴影后重新估计角度: {new_angle}")

                if 2.0 < abs(new_angle) < 15:
                    current = self.deskew(current, new_angle)

            elif op == "gamma_correct":
                current = self.gamma_correct(current, gamma=1.5)

            elif op == "clahe":
                current = self.clahe(current)
                current = self.sharpen(current)

            elif op == "sharpen":
                current = self.sharpen(current)

            elif op == "denoise":
                current = self.denoise(current)

            elif op == "light_denoise":
                current = self.light_denoise(current)

            elif op == "table_line_enhance":
                current = self.table_line_enhance(current)

            elif op == "adaptive_binarize":
                current = self.adaptive_binarize(current)

            elif op == "otsu_binarize":
                current = self.otsu_binarize(current)

            elif op == "morph_clean":
                current = self.morph_clean(current)

            elif op == "upscale":
                current = self.upscale(current, scale=2)

            else:
                raise ValueError(f"未知算子: {op}")

        return current

    # =========================
    # 特征函数
    # =========================
    def estimate_blur(self, gray):
        """
        Laplacian 方差越小，越模糊。
        """
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def estimate_edge_density(self, gray):
        edges = cv2.Canny(gray, 80, 160)
        return np.count_nonzero(edges) / edges.size

    def estimate_shadow_score(self, gray):
        """
        简单阴影估计：
        用大尺度模糊估计背景，如果背景亮度变化大，说明可能有阴影。
        """
        background = cv2.GaussianBlur(gray, (51, 51), 0)
        return np.std(background)

    def estimate_table_score(self, gray):
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            35,
            15
        )

        h, w = binary.shape

        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(20, w // 25), 1)
        )
        vertical_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (1, max(20, h // 20))
        )

        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

        horizontal_score = np.count_nonzero(horizontal) / binary.size
        vertical_score = np.count_nonzero(vertical) / binary.size
        table_score = horizontal_score + vertical_score

        return float(table_score), float(horizontal_score), float(vertical_score)

    def estimate_skew_angle(self, gray):
        """
        估计倾斜角。
        注意：这里只适合印刷文档/扫描文档，复杂拍照图可能不稳定。
        """
        blur = cv2.GaussianBlur(gray, (3, 3), 0)

        binary = cv2.threshold(
            blur,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )[1]

        coords = np.column_stack(np.where(binary > 0))

        if len(coords) < 100:
            return 0.0

        angle = cv2.minAreaRect(coords)[-1]

        if angle < -45:
            angle = 90 + angle

        # 限制异常角度
        if abs(angle) > 20:
            return 0.0

        return float(angle)
    
    def estimate_skew_angle_by_text_boxes(self, gray):
        """
        基于文本框估计倾斜角：
        1. 二值化
        2. 膨胀，把字符连接成文本行/文本块
        3. 提取文本框
        4. 对文本框中心点拟合直线
        5. 得到倾斜角
        """
        gray = self.to_gray(gray)

        # 1. 二值化：文字为白，背景为黑
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        binary = cv2.threshold(
            blur, 0, 255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )[1]

        h, w = binary.shape

        # 2. 横向膨胀：把一行文字连起来
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(20, w // 40), 3)
        )
        dilated = cv2.dilate(binary, kernel, iterations=1)

        # 3. 找轮廓，得到文本框
        contours, _ = cv2.findContours(
            dilated,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        boxes = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)

            area = bw * bh

            # 过滤噪声、小块、太大的背景块
            if area < 300:
                continue
            if bw < 30 or bh < 8:
                continue
            if area > gray.size * 0.5:
                continue

            boxes.append((x, y, bw, bh))

        if len(boxes) < 3:
            return 0.0

        # 4. 用文本框中心点拟合直线
        centers = []
        for x, y, bw, bh in boxes:
            cx = x + bw / 2
            cy = y + bh / 2
            centers.append([cx, cy])

        centers = np.array(centers, dtype=np.float32)

        # 按 y 分组：避免多行中心点直接拟合成一条很奇怪的线
        boxes_sorted = sorted(boxes, key=lambda b: b[1])

        line_angles = []

        for x, y, bw, bh in boxes_sorted:
            # 用每个文本块自身的最小外接矩形角度，比全图稳定
            roi = binary[y:y+bh, x:x+bw]
            coords = np.column_stack(np.where(roi > 0))

            if len(coords) < 50:
                continue

            angle = cv2.minAreaRect(coords)[-1]

            if angle < -45:
                angle = 90 + angle

            if abs(angle) <= 20:
                line_angles.append(angle)

        if len(line_angles) == 0:
            return 0.0

        # 5. 取中位数，比平均值抗异常值更强
        final_angle = float(np.median(line_angles))

        return final_angle
    # =========================
    # OpenCV 算子
    # =========================
    def to_gray(self, img):
        if len(img.shape) == 2:
            return img
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def deskew(self, img, angle):
        h, w = img.shape[:2]
        center = (w // 2, h // 2)

        matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)

        rotated = cv2.warpAffine(
            img,
            matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        return rotated

    def remove_shadow(self, img):
        """
        简单阴影去除：
        用大尺度模糊估计背景，再进行归一化。
        """
        gray = self.to_gray(img)

        background = cv2.GaussianBlur(gray, (51, 51), 0)

        normalized = cv2.divide(gray, background, scale=240)

        return normalized

    def gamma_correct(self, img, gamma=1.5):
        """
        gamma > 1 会提升暗部。
        """
        gray = self.to_gray(img)

        inv_gamma = 1.0 / gamma
        table = np.array([
            ((i / 255.0) ** inv_gamma) * 255
            for i in np.arange(256)
        ]).astype("uint8")

        return cv2.LUT(gray, table)

    def clahe(self, img):
        gray = self.to_gray(img)

        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )

        return clahe.apply(gray)

    def sharpen(self, img):
        gray = self.to_gray(img)

        kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ])

        return cv2.filter2D(gray, -1, kernel)

    def denoise(self, img):
        gray = self.to_gray(img)

        return cv2.fastNlMeansDenoising(
            gray,
            None,
            h=6,
            templateWindowSize=7,
            searchWindowSize=21
        )

    def light_denoise(self, img):
        gray = self.to_gray(img)

        return cv2.medianBlur(gray, 3)

    def adaptive_binarize(self, img):
        gray = self.to_gray(img)

        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            15
        )

    def otsu_binarize(self, img):
        gray = self.to_gray(img)

        _, binary = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        return binary

    def morph_clean(self, img):
        gray = self.to_gray(img)

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (2, 2)
        )

        cleaned = cv2.morphologyEx(
            gray,
            cv2.MORPH_OPEN,
            kernel,
            iterations=1
        )

        return cleaned

    def table_line_enhance(self, img):
        """
        表格线增强：
        主要增强横线和竖线结构。
        """
        gray = self.to_gray(img)

        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            35,
            15
        )

        h, w = binary.shape

        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(10, w // 40), 1)
        )
        vertical_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (1, max(10, h // 40))
        )

        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

        lines = cv2.add(horizontal, vertical)

        # 把线条叠回原图
        enhanced = gray.copy()
        enhanced[lines > 0] = 0

        return enhanced
    
    def sharpen(self, img):

        blurred = cv2.GaussianBlur(img, (0, 0), 1.0)
        sharp = cv2.addWeighted(img, 1.5, blurred, -0.5, 0)

        return sharp

    def upscale(self, img, scale=2):

        h, w = img.shape[:2]

        return cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)


def process_folder(input_dir, output_dir, debug=False):
    processor = AdaptiveDocumentPreprocessor(debug=debug)

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_exts = processor.image_exts

    reports = []

    for file in input_dir.iterdir():
        if file.suffix.lower() in image_exts:
            print(f"正在处理: {file}")
            try:
                report = processor.process_file(file, output_dir)
                reports.append(report)
                print(f"完成: {report['output_file']}")
                print(f"路由: {' -> '.join(report['route'])}")
            except Exception as e:
                print(f"处理失败: {file}, 原因: {e}")

    summary_path = output_dir / "summary_report.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    print(f"全部完成，汇总报告: {summary_path}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
        help="输入图片路径或图片文件夹"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="输出文件夹"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="是否打印每一步算子"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)

    processor = AdaptiveDocumentPreprocessor(debug=args.debug)

    if input_path.is_file():
        report = processor.process_file(input_path, output_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))

    elif input_path.is_dir():
        process_folder(input_path, output_dir, debug=args.debug)

    else:
        raise ValueError(f"输入路径不存在: {input_path}")


if __name__ == "__main__":
    main()