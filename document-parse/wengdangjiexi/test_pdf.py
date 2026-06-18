from paddleocr import PaddleOCRVL
import os

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"


input_file = "/nfsdat1/home/tyxuslm/paddleocr2/input/论文/基于大语言模型的多智能体协同架构及其在车机系统中的应用研究_王伟.pdf"

pipeline = PaddleOCRVL(
    #layout_detection_model_dir='/nfsdat1/home/tyxuslm/paddleocr2/model/PP-DocLayoutV3',
    vl_rec_model_dir='/nfsdat1/home/tyxuslm/PaddleOCR-VL-1.5-hw',
)

output = pipeline.predict(input=input_file)

pages_res = list(output)

# output = pipeline.restructure_pages(pages_res)
# output = pipeline.restructure_pages(pages_res, merge_table=True) # 合并跨页表格
# output = pipeline.restructure_pages(pages_res, merge_table=True, relevel_titles=True) # 合并跨页表格，重建多级标题
output = pipeline.restructure_pages(pages_res, merge_tables=True, relevel_titles=True, concatenate_pages=True) # 合并跨页表格，重建多级标题，合并多页结果为一页

for res in output:
    res.print() ## 打印预测的结构化输出
    #res.save_to_json(save_path="/nfsdat1/home/tyxuslm/paddleocr2/output/论文/基于大语言模型的多智能体协同架构及其在车机系统中的应用研究_王伟") ## 保存当前图像的结构化json结果
    res.save_to_markdown(save_path="/nfsdat1/home/tyxuslm/paddleocr2/output/论文/基于大语言模型的多智能体协同架构及其在车机系统中的应用研究_王伟") ## 保存当前图像的markdown格式的结果
