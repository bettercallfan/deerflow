import re
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from transformers import AutoModelForCausalLM, AutoTokenizer

from base.base import LLMClient
import os

# =========================
# 1. ReaderLM 本地模型（延迟加载）
# =========================
# 不在 import 阶段加载模型，否则容器启动时若模型不存在会导致 FastAPI 崩溃。
# 仅在首次调用 html_to_markdown() 时加载，通过 _ensure_readerlm_loaded() 触发。
_device = "cpu"
_tokenizer = None
_model = None


def _ensure_readerlm_loaded():
    """延迟加载 ReaderLM-v2 tokenizer 和 model。首次调用时根据环境变量加载。"""
    global _tokenizer, _model

    if _tokenizer is not None and _model is not None:
        return

    model_path = os.getenv("READERLM_MODEL_PATH", "").strip()
    if not model_path:
        raise RuntimeError(
            "READERLM_MODEL_PATH 环境变量未设置，无法使用 markdown 输出模式。\n"
            "请先在 Docker Compose 中挂载 ReaderLM-v2 模型目录，并设置 READERLM_MODEL_PATH=/models/ReaderLM-v2。"
        )

    if not Path(model_path).exists():
        raise RuntimeError(
            f"ReaderLM-v2 模型路径不存在: {model_path}\n"
            "请确认已正确挂载模型目录。当前任务不能使用 markdown 输出模式，"
            "可选择 html 或 json 输出模式。"
        )

    _tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
        local_files_only=True,
    )
    _model = AutoModelForCausalLM.from_pretrained(
        model_path,
        trust_remote_code=True,
        local_files_only=True,
    ).to(_device)


# =========================
# 2. HTML 清洗
# =========================
def clean_html(html_content: str, base_url: str = None) -> str:
    """
    清洗 HTML：移除脚本、样式、注释、部分无关标签和行内样式。
    """
    soup = BeautifulSoup(html_content, "html.parser")

    useless_tags = [
        "style", "script", "noscript", "svg",
        "meta", "link", "iframe", "head"
    ]
    for tag in soup(useless_tags):
        tag.decompose()

    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    for comment in comments:
        comment.extract()

    for tag in soup.find_all(True):
        if tag.has_attr("style"):
            del tag["style"]

        # 去掉常见事件属性
        attrs_to_remove = [attr for attr in tag.attrs if attr.lower().startswith("on")]
        for attr in attrs_to_remove:
            del tag[attr]

    if base_url:
        for img_tag in soup.find_all("img"):
            src = img_tag.get("src")
            if not src:
                continue
            img_tag["src"] = urljoin(base_url, src)

    return str(soup)


# =========================
# 3. Selenium 抓取网页 HTML
# =========================
def fetch_html(url: str, wait_seconds: int = 3) -> str:
    """
    使用 Selenium 抓取网页完整 HTML，并进行清洗。
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        time.sleep(wait_seconds)
        html = driver.page_source
    finally:
        driver.quit()

    return clean_html(html, base_url=url)


# =========================
# 4. 构造 ReaderLM Prompt
# =========================
def create_prompt(
    html_text: str,
    tokenizer,
    instruction: str = None,
    schema: str = None
) -> str:
    if not instruction:
        instruction = """
        "Extract the main content from the given HTML and convert it to Markdown format. "
        "Preserve all image links in Markdown using their full absolute URLs exactly as they appear in the HTML. "
        "Do not omit images."
        """

    if schema:
        instruction = (
            "Extract the specified information from a list of news threads "
            "and present it in a structured JSON format."
        )
        prompt = (
            f"{instruction}\n"
            f"```html\n{html_text}\n```\n"
            f"The JSON schema is as follows:\n```json\n{schema}\n```"
        )
    else:
        prompt = f"{instruction}\n```html\n{html_text}\n```"

    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )


# =========================
# 5. ReaderLM: HTML -> Markdown
# =========================
def html_to_markdown(html_text: str, max_length: int = 100000) -> str:
    """
    使用本地 ReaderLM 将 HTML 转成 Markdown。
    首次调用时延迟加载模型。
    """
    _ensure_readerlm_loaded()

    input_prompt = create_prompt(html_text, tokenizer=_tokenizer)
    inputs = _tokenizer.encode(input_prompt, return_tensors="pt").to(_device)

    outputs = _model.generate(
        inputs,
        temperature=0,
        max_length=max_length,
        do_sample=False,
        repetition_penalty=1.08
    )

    generated_text = _tokenizer.decode(
        outputs[0][inputs.shape[1]:],
        skip_special_tokens=True
    )
    return generated_text.strip()


# =========================
# 6. 提取 Markdown 中的图片
# =========================
def extract_markdown_images(markdown_text: str, base_url: str):
    """
    提取 Markdown 中的图片：
    匹配形式：![alt](url)
    返回列表：[(full_match, alt_text, resolved_url), ...]
    """
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    matches = re.findall(pattern, markdown_text)

    results = []
    for alt_text, img_url in matches:
        img_url = img_url.strip()

        # 去掉 title 的情况：![alt](url "title")
        if " " in img_url and not img_url.startswith("http"):
            img_url = img_url.split(" ")[0]

        resolved_url = urljoin(base_url, img_url)
        full_match = f"![{alt_text}]({img_url})"
        results.append((full_match, alt_text, resolved_url))

    return results


# =========================
# 7. Qwen-VL-OCR 远程 OCR
# =========================
def ocr_image_with_qwen(
    llm_client: LLMClient,
    image_url: str,
    model_name: str = "qwen-vl-ocr",
    max_retries: int = 3
) -> str:
    """
    使用 OpenAI 兼容接口调用 qwen-vl-ocr，对图片做 OCR。
    注意：这里直接使用 llm_client.client 发送多模态消息。
    """
    system_prompt = "You are an OCR assistant. Extract all visible text from the image accurately."
    user_content = [
        {
            "type": "text",
            "text": (
                "请对这张图片做 OCR，输出图片中所有可识别文字。"
                "要求：\n"
                "1. 尽量完整保留原文\n"
                "2. 按自然阅读顺序输出\n"
                "3. 不要解释，不要总结\n"
                "4. 如果没有文字，返回：<NO_TEXT>"
            )
        },
        {
            "type": "image_url",
            "image_url": {
                "url": image_url
            }
        }
    ]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    for attempt in range(max_retries):
        try:
            response = llm_client.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0,
                timeout=llm_client.time_out,
            )

            if response.choices and response.choices[0].message:
                content = response.choices[0].message.content
                return content.strip() if content else ""
            return ""
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[OCR] 第 {attempt + 1} 次失败：{e}，{wait_time}s 后重试...")
                time.sleep(wait_time)
            else:
                print(f"[OCR] 最终失败，image_url={image_url}，错误：{e}")
                return ""


# =========================
# 8. 把 OCR 结果插入 Markdown
# =========================
def enrich_markdown_with_ocr(
    markdown_text: str,
    page_url: str,
    llm_client: LLMClient,
    ocr_model_name: str = "qwen-vl-ocr"
) -> str:
    """
    找到 Markdown 中的图片，对每张图片做 OCR，并将结果插入到对应图片下方。
    """
    images = extract_markdown_images(markdown_text, base_url=page_url)
    if not images:
        return markdown_text

    enriched_markdown = markdown_text

    for idx, (full_match, alt_text, image_url) in enumerate(images, start=1):
        # print(f"[OCR] 正在识别第 {idx}/{len(images)} 张图片: {image_url}")

        ocr_text = ocr_image_with_qwen(
            llm_client=llm_client,
            image_url=image_url,
            model_name=ocr_model_name
        )

        if not ocr_text:
            ocr_text = "<OCR_FAILED>"

        insertion = (
            f"{full_match}\n\n"
            f"> [图片OCR结果]\n"
            f"> {ocr_text.replace(chr(10), chr(10) + '> ')}"
        )

        # 只替换当前这一处
        enriched_markdown = enriched_markdown.replace(full_match, insertion, 1)

    return enriched_markdown


# =========================
# 9. 主函数：网页 -> Markdown -> 图片OCR增强
# =========================
def convert_webpage_to_markdown_with_ocr(
    url: str,
    wait_seconds: int = 3
) -> dict:
    """
    输入网页 URL，输出：
    {
        "url": ...,
        "html": ...,
        "markdown": ...,
        "markdown_with_ocr": ...
    }
    """
    ocr_model_name = "qwen-vl-ocr"
    llm_client = LLMClient(
        api_key=os.environ.get("WCODE_API_KEY"),
        model_name="qwen-vl-ocr",
        url="https://wcode.net/api/gpt/v1"
    )
    html = fetch_html(url, wait_seconds=wait_seconds)
    markdown = html_to_markdown(html)
    markdown_with_ocr = enrich_markdown_with_ocr(
        markdown_text=markdown,
        page_url=url,
        llm_client=llm_client,
        ocr_model_name=ocr_model_name
    )

    result = {
        "url": url,
        "html": html,
        "markdown": markdown,
        "markdown_with_ocr": markdown_with_ocr,
    }

    with open("output_markdown.md", "w", encoding="utf-8") as f:
        f.write(result["markdown"])

    with open("output_markdown_with_ocr.md", "w", encoding="utf-8") as f:
        f.write(result["markdown_with_ocr"])

    return result


def convert_html_to_markdown_with_ocr(
    url: str,
    html: str
) -> dict:
    """
    输入网页 URL 与当前页面 HTML，输出：
    {
        "url": ...,
        "html": ...,
        "markdown": ...,
        "markdown_with_ocr": ...
    }
    """
    ocr_model_name = "qwen-vl-ocr"
    llm_client = LLMClient(
        api_key=os.environ.get("WCODE_API_KEY"),
        model_name="qwen-vl-ocr",
        url="https://wcode.net/api/gpt/v1"
    )

    cleaned_html = clean_html(html, base_url=url)
    markdown = html_to_markdown(cleaned_html)
    markdown_with_ocr = enrich_markdown_with_ocr(
        markdown_text=markdown,
        page_url=url,
        llm_client=llm_client,
        ocr_model_name=ocr_model_name
    )

    result = {
        "url": url,
        "html": cleaned_html,
        "markdown": markdown,
        "markdown_with_ocr": markdown_with_ocr,
    }

    with open("output_markdown.md", "w", encoding="utf-8") as f:
        f.write(result["markdown"])

    with open("output_markdown_with_ocr.md", "w", encoding="utf-8") as f:
        f.write(result["markdown_with_ocr"])

    return result


if __name__ == "__main__":
    test_url = "https://tjj.shaanxi.gov.cn/tjsj/tjxx/qs/202603/t20260318_3622564.html"

    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(CURRENT_DIR, "page_source.html")

    with open(html_path, "r") as f:
        html_text = f.read()
    result = convert_html_to_markdown_with_ocr(
        url=test_url,
        html=html_text
    )

    print("=" * 80)
    print("原始网页 URL：")
    print(result["url"])

    print("=" * 80)
    print("Markdown：")
    print(result["markdown"])

    print("=" * 80)
    print("带 OCR 的 Markdown：")
    print(result["markdown_with_ocr"])

    # 可选：保存到文件
    with open("output_markdown.md", "w", encoding="utf-8") as f:
        f.write(result["markdown"])

    with open("output_markdown_with_ocr.md", "w", encoding="utf-8") as f:
        f.write(result["markdown_with_ocr"])

    print("=" * 80)
    print("已保存：output_markdown.md")
    print("已保存：output_markdown_with_ocr.md")
