from paddleocr import PaddleOCRVL
import os

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"


input_file = "/nfsdat1/home/tyxuslm/paddleocr3/预处理增强/output/input图片/模糊图片_processed.png"

pipeline = PaddleOCRVL(
    #layout_detection_model_dir='/nfsdat1/home/tyxuslm/paddleocr2/model/PP-DocLayoutV3',
    #vl_rec_model_dir='/nfsdat1/home/tyxuslm/PaddleOCR-VL-1.5-hw',
    vl_rec_backend='vllm-server',
    vl_rec_server_url='http://219.245.186.44:8000/v1'
)

output = pipeline.predict(input=input_file)

for res in output:
    res.print() ## 打印预测的结构化输出
    #res.save_to_json(save_path="/nfsdat1/home/tyxuslm/paddleocr2/output/论文/基于大语言模型的多智能体协同架构及其在车机系统中的应用研究_王伟") ## 保存当前图像的结构化json结果
    res.save_to_markdown(save_path="/nfsdat1/home/tyxuslm/paddleocr3/output/模糊图片2_processed") ## 保存当前图像的markdown格式的结果
