from pathlib import Path
from adaptive_preprocess import AdaptiveDocumentPreprocessor

processor = AdaptiveDocumentPreprocessor(debug=True)

report = processor.process_file(
    "/nfsdat1/home/tyxuslm/paddleocr3/预处理增强/input/倾斜照片.png",
    "/nfsdat1/home/tyxuslm/paddleocr3/预处理增强/output/"
)

print(report["output_file"])
print(report["features"])
print(report["route"])