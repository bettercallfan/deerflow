from paddleocr import PaddleOCRVL
import os

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"


input_file = "/nfsdat1/home/tyxuslm/paddleocr3/预处理增强/input/模糊图片.png"

pipeline = PaddleOCRVL(
    #layout_detection_model_dir='/nfsdat1/home/tyxuslm/.paddlex/official_models/PP-DocLayoutV3',
    #vl_rec_model_dir='/nfsdat1/home/tyxuslm/PaddleOCR-VL-1.5-hw',
)

output = pipeline.predict(input=input_file)


for res in output:
    res.print() ## 打印预测的结构化输出
    #res.save_to_json(save_path="/nfsdat1/home/tyxuslm/paddleocr2/output/倾斜图片") ## 保存当前图像的结构化json结果
    res.save_to_markdown(save_path="/nfsdat1/home/tyxuslm/paddleocr3/output/模糊图片") ## 保存当前图像的markdown格式的结果
