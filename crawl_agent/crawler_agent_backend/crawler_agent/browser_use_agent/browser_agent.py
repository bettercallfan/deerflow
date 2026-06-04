# -*- coding: utf-8 -*-
"""浏览器智能体"""
import json
# pylint: disable=W0212

import os
import re
import uuid
from pathlib import Path
from typing import Optional, Any, Iterable
import base64

from agentscope.agent import ReActAgent
from agentscope.formatter import FormatterBase
from agentscope.memory import MemoryBase
from agentscope.message import (
    Msg,
    ToolUseBlock,
    TextBlock,
    ImageBlock, Base64Source
)
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit
from agentscope.token import TokenCounterBase, OpenAITokenCounter

_BROWSER_AGENT_DEFAULT_SYS_PROMPT = (
    "你是一个有帮助的浏览器自动化助手。"
    "你可以导航网站、截图并与网页交互。"
    "请始终清晰描述你看到的内容并规划下一步。"
    "在执行操作时，解释你在做什么以及原因。"
)
_BROWSER_AGENT_REASONING_PROMPT = (
    "你正在浏览当前网站。"
    "当前网页的快照（以及截图）如下所示。"
    "由于你只能看到最新网页，"
    "你必须及时总结当前状态、记录所需数据并你必须首先总结当前页面状态和 "
    "并规划你的下一步。"
    "**重要**：每当导航到一个包含所需信息的页面时，必须调用 save_url 工具保存该页面（url 参数填当前页面完整URL）。"
    "不要只输出 URL 文本，必须调用 save_url 工具！"
    "如果你在搜索结果页找到了相关结果，请先调用 save_url 保存搜索结果页，然后点击进入详情页再调用 save_url 保存详情页。"
)


async def browser_agent_default_url_pre_reply(
    self: "BrowserAgent",  # pylint: disable=W0613
    *args: Any,  # pylint: disable=W0613
    **kwargs: Any,  # pylint: disable=W0613
) -> None:
    """如果这是首次交互，则导航到起始URL"""
    if self.start_url and not self._has_initial_navigated:
        await self._navigate_to_start_url()
        self._has_initial_navigated = True


async def browser_agent_summarize_mem_pre_reasoning(
    self: "BrowserAgent",  # pylint: disable=W0613
    *args: Any,
    **kwargs: Any,
) -> None:
    """当记忆过长时进行摘要"""
    mem_len = await self.memory.size()
    if mem_len > self.max_memory_length:
        await self._memory_summarizing()


async def browser_agent_observe_pre_reasoning(
    self: "BrowserAgent",  # pylint: disable=W0613
    *args: Any,
    **kwargs: Any,
) -> None:
    """在推理前获取文本快照"""
    snapshot_msg = await self._get_snapshot_in_text()
    await self.memory.add(snapshot_msg)


async def browser_agent_remove_observation_post_reasoning(
    self: "BrowserAgent",  # pylint: disable=W0613
    *args: Any,
    **kwargs: Any,
) -> None:
    """推理后移除快照消息"""
    mem_len = await self.memory.size()
    if mem_len >= 2:
        await self.memory.delete(mem_len - 2)


async def browser_agent_post_acting_clean_content(
    self: "BrowserAgent",  # pylint: disable=W0613
    *args: Any,
    **kwargs: Any,
) -> None:
    """
    用于清理动作后杂乱返回的钩子函数。
    观察会在推理步骤之前完成。
    """
    mem_msgs = await self.memory.get_memory()
    mem_length = await self.memory.size()
    if len(mem_msgs) == 0:
        return
    last_output_msg = mem_msgs[-1]
    for i, b in enumerate(last_output_msg.content):
        if b["type"] == "tool_result":
            for j, return_json in enumerate(b.get("output", [])):
                if isinstance(return_json, dict):
                    text = return_json.get("text")
                    if text:
                        last_output_msg.content[i]["output"][j][
                            "output"
                        ] = self._filter_execution_text(text)
    await self.memory.delete(mem_length - 1)
    await self.memory.add(last_output_msg)


class BrowserAgent(ReActAgent):
    """
    扩展自 ReActAgent 的浏览器智能体，提供浏览器特有能力。

    该智能体通过 MCP（Model Context Protocol）服务器接入 Playwright
    浏览器工具，实现更复杂的网页自动化任务。

    示例:
        .. code-block:: python

            agent = BrowserAgent(
                name="web_navigator",
                model=my_chat_model,
                formatter=my_formatter,
                memory=my_memory,
                toolkit=browser_toolkit,
                start_url="https://example.com"
            )

            response = await agent.reply("Search for Python tutorials")
    """

    def __init__(
        self,
        name: str,
        model: ChatModelBase,
        formatter: FormatterBase,
        memory: MemoryBase,
        toolkit: Toolkit,
        sys_prompt: str = _BROWSER_AGENT_DEFAULT_SYS_PROMPT,
        max_iters: int = 50,
        start_url: Optional[str] = "https://www.google.com",
        reasoning_prompt: str = _BROWSER_AGENT_REASONING_PROMPT,
        token_counter: TokenCounterBase = OpenAITokenCounter("gpt-4o"),
        max_mem_length: int = 10,
        enable_screenshots: bool = True,
    ) -> None:
        """初始化浏览器智能体。

        Args:
            name (str):
                智能体实例的唯一名称。
            model (ChatModelBase):
                用于生成回复和推理的对话模型。
            formatter (FormatterBase):
                用于将消息转换为模型 API 所需格式的格式化器。
            memory (MemoryBase):
                用于存储和检索对话历史的记忆组件。
            toolkit (Toolkit):
                包含浏览器工具函数和工具方法的工具包对象。
            sys_prompt (str, optional):
                定义智能体行为与人格的系统提示词。
                默认值为 _BROWSER_AGENT_DEFAULT_SYS_PROMPT。
            max_iters (int, optional):
                推理-行动循环的最大迭代次数。
                默认值为 50。
            start_url (Optional[str], optional):
                智能体启动时导航到的初始 URL。
                默认值为 "https://www.google.com"。
            reasoning_prompt (str, optional):
                推理阶段用于引导决策的提示词。
                默认值为 _BROWSER_AGENT_REASONING_PROMPT。

        Returns:
            None
        """
        super().__init__(
            name=name,
            sys_prompt=sys_prompt,
            model=model,
            formatter=formatter,
            memory=memory,
            toolkit=toolkit,
            max_iters=max_iters,
        )

        self.start_url = start_url
        self._has_initial_navigated = False
        self.reasoning_prompt = reasoning_prompt
        self.max_memory_length = max_mem_length
        self.token_estimator = token_counter
        self.enable_screenshots = enable_screenshots

        self.register_instance_hook(
            "pre_reply",
            "browser_agent_default_url_pre_reply",
            browser_agent_default_url_pre_reply,
        )

        self.register_instance_hook(
            "pre_reasoning",
            "browser_agent_summarize_mem_pre_reasoning",
            browser_agent_summarize_mem_pre_reasoning,
        )

        self.register_instance_hook(
            "pre_reasoning",
            "browser_agent_observe_pre_reasoning",
            browser_agent_observe_pre_reasoning,
        )

        self.register_instance_hook(
            "post_reasoning",
            "browser_agent_remove_observation_post_reasoning",
            browser_agent_remove_observation_post_reasoning,
        )

        self.register_instance_hook(
            "post_acting",
            "browser_agent_post_acting_clean_content",
            browser_agent_post_acting_clean_content,
        )

    async def _navigate_to_start_url(self) -> None:
        """
        使用 browser_navigate 工具导航到指定的起始 URL。

        该方法会在首次交互时自动调用，以导航到配置的起始 URL。
        它会执行浏览器导航工具并处理返回结果，以确保初始页面加载完成。

        Returns:
            None
        """
        tool_call = ToolUseBlock(
            id=str(uuid.uuid4()),
            type="tool_use",
            name="browser_navigate",
            input={"url": self.start_url},
        )

        # 执行导航工具
        await self.toolkit.call_tool_function(tool_call)

    async def _get_snapshot_in_text(self) -> Msg:
        """获取当前网页内容的文本快照。

        该方法使用 browser_snapshot 工具获取当前网页的文本内容，
        在推理阶段作为当前浏览器状态的上下文。

        Returns:
            str: 当前网页内容的文本表示，
                包含元素、结构与可见文本。

        Note:
            该方法会在推理阶段自动调用，
            为下一步行动的决策提供关键上下文。
        """
        snapshot_tool_call = ToolUseBlock(
            type="tool_use",
            id=str(uuid.uuid4()),  # 为工具调用生成唯一 ID
            name="browser_snapshot",
            input={},  # 该工具不需要参数
        )

        snapshot_response = await self.toolkit.call_tool_function(
            snapshot_tool_call,
        )
        snapshot_str = ""
        async for chunk in snapshot_response:
            if not chunk.content:
                continue
            first_block = chunk.content[0]
            if isinstance(first_block, dict):
                snapshot_str = first_block.get("text", "")
            else:
                snapshot_str = ""
            if snapshot_str:
                break

        # 过滤快照数据，移除 base64 图片和冗余内容
        snapshot_str = self._filter_snapshot_text(snapshot_str)

        if not self.enable_screenshots:
            msg_observe = Msg(
                "user",
                content=[
                    TextBlock(
                        type="text",
                        text=self.reasoning_prompt + "\n" + snapshot_str,
                    ),
                ],
                role="user",
            )
            return msg_observe

        # Use a workspace-local directory to satisfy filesystem access policy.
        project_root = Path(__file__).resolve().parents[1]
        screenshot_dir = project_root / ".playwright-mcp" / "crawler_agent_shots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(screenshot_dir / f"page_{uuid.uuid4().hex}.png")

        image_tool_call = ToolUseBlock(
            type="tool_use",
            id=str(uuid.uuid4()),
            name="browser_take_screenshot",
            input={
                "fullPage": True,
                "type": "png",
                "filename": screenshot_path,
            },
        )

        image_response = await self.toolkit.call_tool_function(
            image_tool_call,
        )

        try:
            tool_error_text = None
            async for tool_response in image_response:
                if tool_response.content:
                    block = tool_response.content[0]
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if "Error" in text or "错误" in text:
                            tool_error_text = text
                            break

            if tool_error_text:
                raise RuntimeError(tool_error_text)

            if not os.path.exists(screenshot_path):
                raise RuntimeError(
                    f"截图文件未生成：{screenshot_path}",
                )

            with open(screenshot_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

            msg_observe = Msg(
                "user",
                content=[
                    TextBlock(
                        type="text",
                        text=self.reasoning_prompt + "\n" + snapshot_str,
                    ),
                    ImageBlock(
                        type="image",
                        source=Base64Source(
                            type="base64",
                            media_type="image/png",
                            data=image_b64,
                        ),
                    )
                ],
                role="user",
            )

        except Exception as e:
            print(f"获取页面截图过程中出现错误：{str(e)}，进入纯文本浏览模式")

            msg_observe = Msg(
                "user",
                content=[
                    TextBlock(
                        type="text",
                        text=self.reasoning_prompt + "\n" + snapshot_str,
                    ),
                ],
                role="user",
            )

        return msg_observe

    async def _memory_summarizing(self) -> None:
        """对当前记忆内容进行摘要，避免上下文溢出。

        该方法会定期压缩对话历史，通过生成进度摘要并仅保留关键信息。
        它会保留最初的用户问题，并生成关于已完成内容和待完成事项的简明总结。

        Returns:
            None

        Note:
            该方法会每 10 次迭代自动调用，用于控制记忆使用量并保持上下文相关性。
            摘要有助于避免 token 上限问题，同时保留重要任务背景。
        """
        print("-------------开始提取记忆--------------")
        # 提取初始用户问题
        initial_question = None
        memory_msgs = await self.memory.get_memory()
        for msg in memory_msgs:
            if msg.role == "user":
                initial_question = self._msg_to_plain_text(msg)
                break

        # 输出一下当前记忆
        state_pre = self.memory.state_dict()
        print(
            "当前记忆: \n"
            f"{json.dumps(state_pre, indent=2, ensure_ascii=False)}",
        )

        # 生成当前进度摘要
        hint_msg = Msg(
            "user",
            (
                f"更新当前任务的记忆状态。用户任务为:{initial_question}。\n"
                "请根据已有记忆，对任务状态进行结构化压缩总结，只保留关键内容。\n"
                "目标是在尽量减少token的同时，确保任务可以连续执行，不丢失关键状态。\n"

                "你的总结必须保持任务的可继续执行性。\n"
                "特别注意保留：当前任务目标、当前执行位置、下一步计划。\n\n"

                "需要更新的内容包括：\n"

                "1. 当前任务目标\n"
                "   - 用户的核心需求是什么（必须始终保留，不得删除）。\n"

                "2. 已完成的工作\n"
                "   - 到目前为止已经执行过的关键步骤。\n"

                "3. 已发现的关键信息\n"
                "   - 从网页、搜索结果或页面内容中获得的重要信息。\n"

                "4. 已访问的页面\n"
                "   - 已经访问过的重要URL。\n"

                "5. 当前任务状态（执行锚点）\n"
                "   - 当前正在处理的步骤。\n"
                "   - 当前处于哪个页面，当前页面URL。\n"
                "   - 当前步骤是否完成。\n"
                "   - 当前准备执行什么操作。\n"

                "6. 未完成的工作\n"
                "   - 仍然需要寻找或验证的信息。\n"

                "7. 下一步计划\n"
                "   - 下一步准备执行的具体操作。\n"
                "   - 必须具体，例如：点击某链接、翻页、搜索关键词等。\n\n"

                "重要规则：\n"
                "- 必须始终保留【当前任务目标】和【下一步计划】。\n"
                "- 优先保留最近执行的步骤，避免丢失最新状态。\n"
                "- 不要删除仍然可能有用的信息。\n"
                "- 不要生成与任务无关的信息。\n"
                "- 输出必须严格遵循以下模板。\n\n"

                "请严格按以下JSON模板输出：\n"
                "{\n"
                "  \"task_goal\": {\n"
                "    \"core_need\": \"\"  \n"
                "  },\n"
                "  \"done\": [\n"
                "    \"\"\n"
                "  ],\n"
                "  \"key_findings\": [\n"
                "    \"\"\n"
                "  ],\n"
                "  \"visited_pages\": [\n"
                "    {\n"
                "      \"url\": \"\",\n"
                "      \"note\": \"\"  \n"
                "    }\n"
                "  ],\n"
                "  \"current_status\": {\n"
                "    \"current_page_url\": \"\",\n"
                "    \"current_step\": \"\",\n"
                "    \"step_completed\": false,\n"
                "    \"in_progress\": \"\",\n"
                "    \"next_intended_action\": \"\"\n"
                "  },\n"
                "  \"todo\": [\n"
                "    \"\"\n"
                "  ],\n"
                "  \"next_plan\": [\n"
                "    {\n"
                "      \"action\": \"\",        \n"
                "      \"target\": \"\",        \n"
                "      \"method\": \"\",        \n"
                "      \"keyword\": \"\",       \n"
                "      \"expected_output\": \"\" \n"
                "    }\n"
                "  ]\n"
                "}\n"
            ),
            role="user",
        )

        # 生成发送给模型的提示词
        plain_memory_msgs = []
        for msg in memory_msgs:
            plain_text = self._msg_to_plain_text(msg)
            if plain_text:
                role = msg.role
                name = msg.name
                if role == "system":
                    role = "assistant"
                    if name == "system":
                        name = self.name
                plain_memory_msgs.append(
                    Msg(name, plain_text, role),
                )
        prompt = await self.formatter.format(
            msgs=[
                Msg("system", self.sys_prompt, "system"),
                *plain_memory_msgs,
                hint_msg,
            ],
        )

        # 调用模型生成摘要
        res = await self.model(prompt)

        # 处理响应
        summary_text = ""
        if self.model.stream:
            assembled_text = ""
            async for content_chunk in res:
                chunk_text = self._extract_text_from_blocks(
                    getattr(content_chunk, "content", []),
                )
                if chunk_text:
                    assembled_text = self._merge_stream_text(
                        assembled_text,
                        chunk_text,
                    )
            summary_text = assembled_text.strip()
        else:
            summary_text = self._extract_text_from_blocks(
                getattr(res, "content", []),
            )

        if not summary_text.strip() or len(summary_text.strip()) < 20:
            fallback_chunks = [
                self._msg_to_plain_text(msg) for msg in memory_msgs[-4:]
            ]
            fallback_text = "\n\n".join(
                chunk for chunk in fallback_chunks if chunk.strip()
            )
            summary_text = (
                "摘要生成异常或过短，使用最近记忆作为回退。\n"
                f"{fallback_text or '无可用的最近记忆。'}"
            )
            print("摘要生成异常")

        # 用摘要内容更新记忆
        summarized_memory = []
        if initial_question:
            summarized_memory.append(
                Msg("user", initial_question, role="user"),
            )
        summarized_memory.append(
            Msg(self.name, summary_text, role="assistant"),
        )

        # 清空并重载记忆
        await self.memory.clear()
        for msg in summarized_memory:
            await self.memory.add(msg)

        # 输出一下总结后的记忆
        state_pre = self.memory.state_dict()
        print(
            "总结后的记忆: \n"
            f"{json.dumps(state_pre, indent=2, ensure_ascii=False)}",
        )

    @staticmethod
    def _extract_text_from_blocks(blocks: Iterable[Any]) -> str:
        """从模型返回的多类型 block 中提取可用文本。"""
        text_parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text" and block.get("text"):
                    text_parts.append(block["text"])
                # elif block_type == "thinking" and block.get("thinking"):
                #     text_parts.append(block["thinking"])
                continue

            text = getattr(block, "text", None)
            thinking = getattr(block, "thinking", None)
            if text:
                text_parts.append(text)
            elif thinking:
                text_parts.append(thinking)

        return "\n".join(part for part in text_parts if part).strip()

    @staticmethod
    def _merge_stream_text(existing: str, chunk: str) -> str:
        """合并流式文本，兼容“增量块”和“累计块”，避免重复拼接。"""
        if not existing:
            return chunk
        if not chunk:
            return existing

        if chunk.startswith(existing):
            return chunk
        if existing.endswith(chunk):
            return existing

        # 查找最大重叠：existing 的后缀 == chunk 的前缀
        max_overlap = min(len(existing), len(chunk))
        for overlap in range(max_overlap, 0, -1):
            if existing.endswith(chunk[:overlap]):
                return existing + chunk[overlap:]

        return existing + chunk

    @staticmethod
    def _msg_to_plain_text(msg: Msg) -> str:
        """将消息中的混合 block 压平成纯文本，供摘要模型理解。"""
        parts: list[str] = []
        for block in msg.get_content_blocks():
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
                continue

            if block_type == "thinking":
                thinking = block.get("thinking", "")
                if thinking:
                    parts.append(f"[thinking] {thinking}")
                continue

            if block_type == "tool_use":
                tool_name = block.get("name", "")
                tool_input = block.get("input", {})
                parts.append(
                    f"[tool_use] {tool_name} input="
                    f"{json.dumps(tool_input, ensure_ascii=False)}",
                )
                continue

            if block_type == "tool_result":
                tool_name = block.get("name", "")
                outputs = block.get("output", [])
                output_texts: list[str] = []
                if isinstance(outputs, list):
                    for item in outputs:
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "text"
                            and item.get("text")
                        ):
                            output_texts.append(item["text"])
                elif isinstance(outputs, str):
                    output_texts.append(outputs)
                merged_output = "\n".join(output_texts).strip()
                if merged_output:
                    parts.append(
                        f"[tool_result] {tool_name} output={merged_output}",
                    )
                continue

        return "\n".join(parts).strip()

    @staticmethod
    def _filter_snapshot_text(text: str, max_length: int = 100000) -> str:
        """
        过滤快照文本，移除 base64 图片和冗余内容，限制长度。

        Args:
            text (str): 原始快照文本
            max_length (int): 最大保留长度，默认 50000 字符

        Returns:
            str: 过滤后的快照文本
        """
        # 移除 base64 编码的图片数据（data:image/...;base64,...）
        text = re.sub(
            r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}',
            '[图片已移除]',
            text,
            flags=re.DOTALL
        )
        
        # 移除较长的 base64 字符串（可能是图片或其他二进制数据）
        text = re.sub(
            r'[A-Za-z0-9+/=]{500,}',
            '[长字符串已移除]',
            text
        )

        text = BrowserAgent._filter_execution_text(text, keep_page_state=False)

        if len(text) > max_length:
            text = text[:max_length] + "\n\n[内容已截断...]"
            print("内容已截断")
        
        return text

    @staticmethod
    def _filter_execution_text(
        text: str,
        keep_page_state: bool = False,
    ) -> str:
        """
        过滤并清理浏览器工具的执行输出，以移除冗长内容。

        该工具方法会移除浏览器工具响应中的无用冗长内容，
        包括 JavaScript 代码块、控制台消息和 YAML 内容，
        以避免占用上下文窗口而不提供有效信息。

        Args:
            text (str):
                浏览器工具返回的原始执行文本，需要进行过滤。
            keep_page_state (bool, optional):
                是否保留页面状态信息，
                包括 URL 和 YAML 内容。默认 False。

        Returns:
            str: 过滤后的执行文本。
        """
        if not keep_page_state:
            # 移除页面快照和 YAML 内容
            text = re.sub(r"- Page URL.*", "", text, flags=re.DOTALL)
            text = re.sub(r"```yaml.*?```", "", text, flags=re.DOTALL)
        # 移除 JavaScript 代码块
        text = re.sub(r"```js.*?```", "", text, flags=re.DOTALL)
        # 移除非常冗长的控制台消息区块
        # （位于 "### New console messages" 和 "### Page state" 之间）
        text = re.sub(
            r"### New console messages.*?(?=### Page state)",
            "",
            text,
            flags=re.DOTALL,
        )
        # 移除 base64 编码的图片数据
        text = re.sub(
            r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}',
            '[图片已移除]',
            text,
            flags=re.DOTALL
        )
        # 去除首尾空白
        return text.strip()
