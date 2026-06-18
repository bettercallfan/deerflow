"""The main entry point of the browser agent example."""
import asyncio
import glob
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

from base.base import LLMClient
from browser_use_agent.browser_agent import BrowserAgent
from browser_use_agent.tool import (
    get_collected_pages,
    append_url_only_page,
    register_browser_tools,
    reset_browser_tool_state,
    set_browser_toolkit,
    save_url,
    _browser_evaluate_json,
    _store_page_record,
)
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit
from agentscope.mcp import StdIOStatefulClient
from agentscope.message import Msg
from web_info_extract.recursive_acquisition import HTMLRecursiveExtractor
from html_to_markdown.readerlm import (
    convert_html_to_markdown_with_ocr,
    convert_webpage_to_markdown_with_ocr,
)


def _build_browser_model_config(model_config: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    runtime_cfg = model_config or {}
    return {
        "api_key": runtime_cfg.get("api_key") or os.environ.get("WCODE_API_KEY", ""),
        "base_url": runtime_cfg.get("base_url") or os.environ.get("WCODE_BASE_URL", ""),
        "model_name": runtime_cfg.get("model_name") or os.environ.get("WCODE_MODEL_NAME", ""),
    }


async def browse_page(query: str, url: str, model_config: Optional[Dict[str, str]] = None, max_iters: int = 10) -> List[Dict[str, Any]]:
    """
    用户提供初始URL和想要获取的信息，BrowserAgent导航到目标页面并返回URL

    :param query: 用户查询，描述想要获取的信息
    :param url: 初始URL
    :return: 目标页面（包含 URL + HTML）
    """
    reset_browser_tool_state()

    # Setup toolkit with browser tools from MCP server
    toolkit = Toolkit()
    register_browser_tools(toolkit)
    # 动态查找最新版 Chromium，避免硬编码版本号导致容器重建后路径失效
    _browsers_root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright"))
    _chromium_dirs = sorted(
        [p for p in _browsers_root.glob("chromium-*") if (p / "chrome-linux64" / "chrome").exists()],
        reverse=True,
    )
    _chromium_path = str(_chromium_dirs[0] / "chrome-linux64" / "chrome") if _chromium_dirs else ""

    browser_client = StdIOStatefulClient(
        name="playwright-mcp",
        command="npx",
        args=[
            "@playwright/mcp@latest",
            "--browser", "chrome",
            "--executable-path", _chromium_path,
            "--no-sandbox",
            "--isolated",
        ],

    )

    # 自定义系统提示词，确保最终返回包含URL
    custom_sys_prompt = (
        f"""
            你是一个智能的网页导航助手（Web Navigation Agent）。

            【目标】
            从给定的初始 URL 开始，在“不离开该站点”的前提下，通过浏览/点击/站内搜索等方式，
            找到“包含用户所需信息”的目标页面，并保存这些页面 URL，一定要按照【任务要求】中的步骤对任务进行执行，**同时重视分页遍历规则**！

            【硬性约束（必须遵守）】
            1) 站内限制：整个导航过程不得离开初始 URL 所属网站（同域/同站点范围内），初始 URL：{url}
            2) **Snapshot 约束（极其重要）**：所有点击操作必须使用 snapshot 中的 ref（形如 e15、e22），把 ref 填入 browser_click 的 element 参数。绝对禁止使用 CSS 选择器（如 .class、#id、a[href] 等）。当你需要点击时：先调用 browser_snapshot 获取最新快照 → 在快照中找到目标元素的 ref → 调用 browser_click(element=\"ref值\")
            3) 工具调用：凡是需要操作页面（点击、输入、翻页、回退、切换标签、保存 URL 等）必须调用对应工具；
               如果某一步不调用工具，必须解释“为什么不需要/无法调用”。

            【任务要求（按步骤执行）】
            A. 需求理解
            - 先根据用户 query 明确要找的信息类型与范围（例如：评论、参数、价格、下载链接、作者信息等）。
            - 若用户 query 包含“寻找所有信息 / 全部结果 / 完整收集 / all / all results / everything”等含义：
              你必须进行“充分探索”，并优先执行分页遍历规则（见 C）。

            B. 导航与探索
            - 允许的动作：点击链接、站内搜索、筛选、展开折叠、切换 Tab/Section、回退等。
            - 重要：描述你在页面中“看到的关键内容”，并说明“下一步要做什么以及原因”。
            - 可视范围：你会被给予当前页面的 DOM 树以及截图，综合这两部分信息进行判断。

            C. **分页遍历规则（强制）**
            当用户要求“寻找所有信息 / 全部结果 / 完整收集 / 所有 / all / all results / everything”时：
            1) 如果当前页面底部存在分页导航且你认为这里应该存在所需信息时（例如：1,2,3… 或 下一页/Next/›/>> 等），你必须：
               - 调用函数 auto_save_paginated_pages 对分页列表进行全量保存
               - 如果函数调用失败，自己进行分页探索，一次一次点击下一页或点击数字跳转链接，直到将所有所需网页都使用 save_url 保存下来
            2) 在完成分页遍历之前，不得跳去探索网站其它区域（除非该页无法继续翻页且你已说明原因）。
            3) 当没有出现强制要求时，完成用户要求即可。

            D. 保存 URL 规则（强制，且要“严格匹配”）
            - **只有当某页面“严格包含用户所需信息”时，才允许保存该页面 URL，只是相关时不允许保存，在调用 save_url 方法前，必须先根据用户查询判断该网页存在所需信息并将信息输出一下再保存url！**。
            - **保存时必须保存“当前页面DOM HTML”而不是二次请求：调用 `save_url(url=当前页面URL)`，该工具会自动读取当前浏览页的 `document.documentElement.outerHTML` 并与URL一同保存。**
            示例：用户要“商品评论”，而页面只有“商品价格/详情”但无评论 → 不得保存。
            - 当某些页面上的文本信息并不包含用户所需信息时，你还需要注意其图片信息，**某些页面上将重要信息以图片形式展示，你需要根据提供给你的截图结合文本判断是否包含所需信息**。
            - 每当你到达一个满足条件的页面：必须调用 save_url 工具保存该页面 URL。
            - 若用户要求“所有信息”，你需要保存“所有可能包含所需信息”的候选页面 URL（在站内限制与分页规则下）。

            E. 结束条件
            - 当你确认已找到能够覆盖用户 query 所需信息的页面集合（尤其是“全部收集”已遍历到最后页后），即可结束。
            - 在最终回复中必须明确指出你找到的目标页面 URL（可能是多个）。

            【最终输出格式（强制）】
            - 最终回复必须包含如下冗余检错标签，并把所有已保存的目标 URL 放入其中：
            <url>
            https://example.com/a, https://example_22.com/b, https://example.com/c
            </url>

            【输出风格要求】
            - 全程清晰描述你看到的内容（页面结构/关键字段/按钮/分页状态等）
            - 每一步说明“我正在做什么 + 为什么这样做”
            - 找不到信息时不要急于结束：先充分探索（尤其是分页/Tab/筛选/展开内容/站内搜索）
"""
    )
    runtime_cfg = _build_browser_model_config(model_config)

    try:
        # Connect to the browser client
        await browser_client.connect()
        await toolkit.register_mcp_client(browser_client)
        set_browser_toolkit(toolkit)

        # Create browser agent with custom system prompt
        agent = BrowserAgent(
            name="BrowserBot",
            model=OpenAIChatModel(
                model_name=runtime_cfg["model_name"],
                api_key=runtime_cfg["api_key"],
                client_args={
                    "base_url": runtime_cfg["base_url"],
                },
            ),

            # formatter=OllamaChatFormatter(),
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=toolkit,
            sys_prompt=custom_sys_prompt,
            max_iters=max_iters,
            start_url=url,
            enable_screenshots=os.environ.get("ENABLE_SCREENSHOTS", "").lower() in ("1", "true", "yes"),
        )

        # 初始消息
        msg = Msg('user', query, 'user')

        # 记录原始查询，用于后续循环
        original_query = query

        def _safe_get_text_content(resp_msg: Msg) -> str:
            try:
                return resp_msg.get_text_content()
            except Exception:
                texts = []
                for block in resp_msg.content or []:
                    if isinstance(block, dict):
                        if block.get("type") == "text" and block.get("text"):
                            texts.append(block.get("text"))
                    else:
                        text = getattr(block, "text", None)
                        if text:
                            texts.append(text)
                return "\n".join(texts)

        while True:
            msg = await agent(msg)
            response_text = _safe_get_text_content(msg)

            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'

            if "<url>" in response_text and "</url>" in response_text:
                try:
                    urls_text = response_text.split("<url>")[1].split("</url>")[0]
                    url_parts = urls_text.split(',')
                    urls = []
                    for part in url_parts:
                        found_urls = re.findall(url_pattern, part.strip())
                        urls.extend(found_urls)
                except Exception as e:
                    urls = re.findall(url_pattern, response_text)

                for parsed_url in urls:
                    append_url_only_page(parsed_url)

                # Agent 未调用 save_url，直接用 browser_evaluate 提取当前页 HTML 作为兜底
                try:
                    payload = await _browser_evaluate_json(
                        """() => ({
                            url: window.location.href || "",
                            title: document.title || "",
                            html: document.documentElement ? document.documentElement.outerHTML : ""
                        })"""
                    )
                    if payload.get("html"):
                        _store_page_record(
                            url=payload.get("url", urls[0]),
                            title=payload.get("title", ""),
                            html=payload["html"],
                            capture_method="fallback_on_exit",
                        )
                except Exception as exc:
                    print(f"兜底 HTML 保存失败: {exc}")

                return get_collected_pages()

            continue_msg = f"{original_query}\n\n请继续导航，找到包含所需信息的页面，并在最终回复中明确指出目标页面的完整URL。"
            msg = Msg('user', continue_msg, 'user')

    except Exception as e:
        print(f"An error occurred: {e}")
        print("Cleaning up browser client...")
        raise RuntimeError(f"Browser navigation failed: {e}") from e
    finally:
        set_browser_toolkit(None)
        # Ensure browser client is always closed,
        # regardless of success or failure
        try:
            await browser_client.close()
            print("Browser client closed successfully.")
        except Exception as cleanup_error:
            print(f"Error while closing browser client: {cleanup_error}")


def crawler_entrance(
        initial_url: str,
        user_query: str,
        mode: str,
        json_model: Optional[Type[BaseModel]] = None
):
    """
    :param initial_url: 网页初始 url
    :param user_query: 用户查询
    :param mode: 启动模式
    :param json_model: 提取 json 所用模式
    :return:
    """

    result_pages = asyncio.run(browse_page(user_query, initial_url))
    result_urls = [item.get("url", "") for item in result_pages]
    result_htmls = [item.get("html", "") for item in result_pages]
    print(f"找到的目标页面URL: {result_urls}")
    if mode == "json":

        llm_client = LLMClient(
            api_key=os.environ.get("WCODE_API_KEY"),
            model_name="qwen3.5-35b-a3b",
            url="https://wcode.net/api/gpt/v1"
        )

        html_extractor = HTMLRecursiveExtractor(
            llm_client=llm_client,
            urls=result_urls,
            htmls=result_htmls,
            json_model=json_model,
            query=user_query
        )
        ans = html_extractor.extract_from_html()
        print(ans)
    elif mode == "markdown":
        for page in result_pages:
            page_url = page.get("url", "")
            page_html = page.get("html", "")
            print(page_html)

            if page_url and page_html:
                convert_html_to_markdown_with_ocr(page_url, page_html)
            elif page_url:
                convert_webpage_to_markdown_with_ocr(page_url, 3)


if __name__ == "__main__":
    print("Starting Browser Agent...")
    print(
        "The browser agent will use "
        "playwright-mcp (https://github.com/microsoft/playwright-mcp)."
        "Make sure the MCP server is can be install "
        "by `npx @playwright/mcp@latest`",
    )

    class newsModel(BaseModel):
        title: str = Field(description="新闻标题")
        publish_time: str = Field(description="发布时间")

    class newsList(BaseModel):
        items: List[newsModel]

    initial_url = "https://www.shaanxi.gov.cn/xw/sxyw/"
    user_query = "帮我获取前50页的要闻"
    mode = "json"

    crawler_entrance(initial_url, user_query, mode)
