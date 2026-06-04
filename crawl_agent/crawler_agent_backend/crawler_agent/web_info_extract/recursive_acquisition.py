from html_node.HTMLNode import HTMLNode
from base.base import LLMClient
from bs4 import BeautifulSoup, Tag, NavigableString
from typing import Optional, Type, List, Any, Tuple, Dict
from pydantic import BaseModel, Field
import json
import re
import os
import requests
from fake_useragent import UserAgent
from typing import Optional
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
PROMPT_DIR = os.path.join(PROJECT_ROOT, "prompt")


class HTMLRecursiveExtractor:
    def __init__(
            self,
            llm_client: LLMClient,
            urls: List[str],
            htmls: List[str],
            query: str,
            json_model: Optional[Type[BaseModel] | Dict[str, Any] | List[Any]] = None,
            min_frontier_candidates: int = 20,
            max_frontier_candidates: int = 40,
            max_frontier_depth: int = 4,
            max_node_str_num: int = 500,
            cached_position_paths: Optional[List[List[str]]] = None,
    ):
        self.llm_client = llm_client
        self.urls = urls
        self.query = query
        self.json_model = json_model
        self.htmls = htmls
        self.markdowns = []
        self.bss = []
        # 将 HTML 转换为 bs 格式
        self.gain_bs_from_html()
        # 将 HTML 转换为 markdown 格式作为全局信息
        self.generate_global_info()
        self.nodes = []  # 自定义数据格式
        self.rewrited_query = ""
        self.min_frontier_candidates = max(1, min_frontier_candidates)
        self.max_frontier_candidates = max(self.min_frontier_candidates, max_frontier_candidates)
        self.max_frontier_depth = max(1, max_frontier_depth)
        self.max_node_str_num = max(1, max_node_str_num)
        self.cached_position_paths = cached_position_paths or []
        self.last_selected_paths_per_page: List[List[str]] = []
        self.last_position_cache_used_per_page: List[bool] = []

    def generate_global_info(self):
        generator = DefaultMarkdownGenerator()
        for html in self.htmls:
            self.markdowns.append(generator.generate_markdown(html))

    @staticmethod
    def _is_noise_fragment(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        # 纯分隔符片段
        if re.fullmatch(r"[|/\\\-\u2014\u2013\u00b7:：]+", stripped):
            return True
        return False

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        normalized = (
            text.replace("\xa0", " ")
            .replace("\u200b", "")
            .replace("\ufeff", "")
            .replace("\r", "\n")
        )
        normalized = re.sub(r"[ \t]+", " ", normalized)
        lines = []
        for raw_line in normalized.split("\n"):
            line = raw_line.strip()
            if self._is_noise_fragment(line):
                continue
            lines.append(line)
        # 避免大量空行，统一为单行文本
        return " ".join(lines).strip()

    def _compact_element_text(self, element: Tag) -> str:
        parts: List[str] = []
        for frag in element.stripped_strings:
            normalized = self._normalize_text(str(frag))
            if not normalized:
                continue
            if self._is_noise_fragment(normalized):
                continue
            parts.append(normalized)
        return " ".join(parts).strip()

    def _count_non_empty_information(self, nodes: List[HTMLNode]) -> int:
        return sum(1 for node in nodes if node.information and node.information.strip())

    def _expand_frontier_once(self, frontier: List[HTMLNode]) -> Tuple[List[HTMLNode], bool]:
        """
        对前沿做一层展开。
        - 有子节点：展开到子节点
        - 无子节点：保留当前节点，避免分支信息丢失
        """
        expanded: List[HTMLNode] = []
        has_expandable = False

        for node in frontier:
            if node.child_node_count() > 0:
                has_expandable = True
                expanded.extend(node.child_node)
            else:
                expanded.append(node)

        return expanded, has_expandable

    def _build_dynamic_frontier(self, current_node: HTMLNode) -> Tuple[List[HTMLNode], int]:
        """
        动态决定本轮候选层：
        - 候选数过少则继续下探
        - 候选数进入区间即停
        - 候选数过多则回退到上一层
        """
        if current_node.child_node_count() == 0:
            return [], 0

        depth = 0
        frontier: List[HTMLNode] = [current_node]
        best_frontier: List[HTMLNode] = []
        best_depth = 0

        while depth < self.max_frontier_depth:
            previous_frontier = list(frontier)
            frontier, has_expandable = self._expand_frontier_once(frontier)
            depth += 1

            frontier_count = self._count_non_empty_information(frontier)
            previous_count = self._count_non_empty_information(previous_frontier)

            if frontier_count == 0:
                continue

            best_frontier = list(frontier)
            best_depth = depth

            if self.min_frontier_candidates <= frontier_count <= self.max_frontier_candidates:
                break

            if frontier_count > self.max_frontier_candidates and depth > 1 and previous_count > 0:
                best_frontier = previous_frontier
                best_depth = depth - 1
                break

            if not has_expandable:
                break

        return best_frontier, best_depth

    def rewrite_query(self):
        """重写 query，将 query 中与第一步即 web agent 导航相关的信息去除掉"""
        with open(os.path.join(PROMPT_DIR, "query_rewrite.md"), "r", encoding="utf-8") as f:
            rewrite_prompt = f.read()
        self.rewrited_query = self.llm_client.invoke(system_prompt=rewrite_prompt, user_prompt=self.query)
        print(f"重写后的 query：{self.rewrited_query}")

    def _extract_balanced_json_fragment(self, text: str, opening_char: str) -> Optional[str]:
        closing_char = "}" if opening_char == "{" else "]"

        for start_index, char in enumerate(text):
            if char != opening_char:
                continue

            depth = 0
            in_string = False
            escape = False

            for current_index in range(start_index, len(text)):
                current_char = text[current_index]

                if in_string:
                    if escape:
                        escape = False
                    elif current_char == "\\":
                        escape = True
                    elif current_char == '"':
                        in_string = False
                    continue

                if current_char == '"':
                    in_string = True
                    continue

                if current_char == opening_char:
                    depth += 1
                elif current_char == closing_char:
                    depth -= 1
                    if depth == 0:
                        return text[start_index:current_index + 1].strip()

        return None

    def _extract_json_text(self, response: str) -> str:
        """
        从模型回复中提取 JSON 。
        按照一下顺序进行提取：
        1. ```json ... ``` 或 ``` ... ``` 中的完整 JSON
        2. 混杂文本中的完整 JSON 对象
        3. 混杂文本中的完整 JSON 数组
        4. 实在没有则原样返回
        """
        response = response.strip()

        code_block_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if code_block_match:
            code_content = code_block_match.group(1).strip()
            obj_fragment = self._extract_balanced_json_fragment(code_content, "{")
            if obj_fragment is not None:
                return obj_fragment
            array_fragment = self._extract_balanced_json_fragment(code_content, "[")
            if array_fragment is not None:
                return array_fragment
            return code_content

        code_block_match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
        if code_block_match:
            code_content = code_block_match.group(1).strip()
            obj_fragment = self._extract_balanced_json_fragment(code_content, "{")
            if obj_fragment is not None:
                return obj_fragment
            array_fragment = self._extract_balanced_json_fragment(code_content, "[")
            if array_fragment is not None:
                return array_fragment
            return code_content

        obj_fragment = self._extract_balanced_json_fragment(response, "{")
        if obj_fragment is not None:
            return obj_fragment

        array_fragment = self._extract_balanced_json_fragment(response, "[")
        if array_fragment is not None:
            return array_fragment

        return response

    def gain_bs_from_html(self):
        """将原始 HTML 转化为 bs"""
        for html in self.htmls:
            soup = BeautifulSoup(html, "html.parser")
            self.bss.append(soup)

    def _load_json_with_error(self, text: str) -> Tuple[Optional[Any], Optional[str]]:
        try:
            return json.loads(text), None
        except json.JSONDecodeError as e:
            # 标准 JSON 的检错信息，包含行/列定位
            return None, f"JSONDecodeError: {e.msg} (line {e.lineno}, column {e.colno})"
        except Exception as e:
            return None, f"JSONDecodeError: {str(e)}"

    def _validate_with_pydantic(self, model: Type[BaseModel], data: Any) -> Tuple[Optional[BaseModel], Optional[str]]:
        try:
            return model.model_validate(data), None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _dedupe_preserve_order(values: List[str]) -> List[str]:
        seen = set()
        ordered = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _iter_nodes(self, node: Optional[HTMLNode]):
        if node is None:
            return
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            for child in reversed(current.child_node):
                stack.append(child)

    def _build_node_path_index(self, node: Optional[HTMLNode]) -> Dict[str, HTMLNode]:
        index: Dict[str, HTMLNode] = {}
        for current in self._iter_nodes(node):
            if current.original_tag_path:
                index[current.original_tag_path] = current
        return index

    def _build_original_text_from_paths(self, node: HTMLNode, position_paths: List[str]) -> Tuple[str, List[str]]:
        if not position_paths:
            return "", []

        path_index = self._build_node_path_index(node)
        fragments: List[str] = []
        matched_paths: List[str] = []
        for path in position_paths:
            matched_node = path_index.get(path)
            if matched_node is None:
                continue
            fragment = matched_node.original_html or matched_node.information or ""
            fragment = fragment.strip()
            if not fragment:
                continue
            fragments.append(f"{fragment}\n---------------------------------------------------")
            matched_paths.append(path)

        return "\n".join(fragments).strip(), self._dedupe_preserve_order(matched_paths)

    def _build_original_tag_path(self, element) -> Optional[str]:
        """生成元素的原始标签路径（包含同级序号，避免合并后路径丢失）。"""
        if isinstance(element, NavigableString):
            parent = element.parent
            parent_path = self._build_original_tag_path(parent) if parent else None
            if parent_path:
                return f"{parent_path} > #text"
            return "#text"

        if not isinstance(element, Tag):
            return None

        segments = []
        current = element
        while current and isinstance(current, Tag):
            if current.name == "[document]":
                break

            index = 1
            previous_sibling = current.previous_sibling
            while previous_sibling:
                if isinstance(previous_sibling, Tag) and previous_sibling.name == current.name:
                    index += 1
                previous_sibling = previous_sibling.previous_sibling

            segments.append(f"{current.name}[{index}]")
            current = current.parent

        segments.reverse()
        return " > ".join(segments) if segments else None

    def _create_html_node(self, element) -> HTMLNode:
        if isinstance(element, NavigableString):
            original_html = str(element)
        elif isinstance(element, Tag):
            original_html = str(element)
        else:
            original_html = str(element).strip()

        return HTMLNode(
            element,
            original_html=original_html,
            original_tag_path=self._build_original_tag_path(element),
        )

    def merge_information(self, element, depth=0) -> Optional[HTMLNode]:
        """
        将子节点所有文本信息合并到父节点上，同时做清洗。
        """

        IGNORE_TAGS = {"script", "style", "noscript", "iframe"}

        # 处理文本节点
        if isinstance(element, NavigableString):
            parent = element.parent
            # 如果父节点是忽略标签，那么直接返回 None
            if parent and isinstance(parent, Tag) and parent.name in IGNORE_TAGS:
                return None
            text = self._normalize_text(str(element))
            if not text or self._is_noise_fragment(text):
                return None
            node = self._create_html_node(element)
            node.update_information(text)
            return node

        # 处理普通标签节点
        if isinstance(element, Tag):
            if element.name in IGNORE_TAGS:
                return None

            current_node = self._create_html_node(element)
            direct_texts: List[str] = []

            compact_subtree_text = self._compact_element_text(element)
            if compact_subtree_text and len(compact_subtree_text) < self.max_node_str_num:
                current_node.update_information(compact_subtree_text)
                print(current_node.information)
                print("\n")
                return current_node

            for child in element.children:
                if isinstance(child, Tag):
                    child_node = self.merge_information(child, depth + 1)
                    if child_node is not None:
                        current_node.append_node(child_node)
                elif isinstance(child, NavigableString):
                    text = self._normalize_text(str(child))
                    if text and not self._is_noise_fragment(text):
                        direct_texts.append(text)

            direct_text = self._normalize_text(" ".join(direct_texts))

            if current_node.child_node_count() == 0 and not direct_text:
                return None

            # 叶子节点保留文本
            if current_node.child_node_count() == 0:
                current_node.update_information(direct_text)
                return current_node

            current_info_lines: List[str] = []
            if direct_text:
                current_info_lines.append(f'{direct_text}')

            for child_node in current_node.child_node:
                if child_node.information and child_node.information.strip():
                    current_info_lines.append(f'{child_node.information}')

            current_node.update_information(self._normalize_text(" ".join(current_info_lines)))

            # 在当前节点没有直接文本且只有一个子节点时，合并节点
            if not direct_text and current_node.child_node_count() == 1:
                return current_node.child_node[0]

            return current_node

        # 处理 BeautifulSoup 根对象
        if isinstance(element, BeautifulSoup):
            root_node = self._create_html_node(element)
            root_info_lines: List[str] = []

            for child in element.children:
                child_node = self.merge_information(child, depth)
                if child_node is None:
                    continue
                root_node.append_node(child_node)
                if child_node.information and child_node.information.strip():
                    root_info_lines.append(child_node.information)

            if root_node.child_node_count() == 0:
                return None

            root_node.update_information("\n".join(root_info_lines).strip())

            # 根节点也做单层嵌套合并
            if root_node.child_node_count() == 1:
                return root_node.child_node[0]
            return root_node

        node = self._create_html_node(element)
        node.update_information(str(element).strip())
        return node

    def collect_information(
            self,
            node: HTMLNode,
            markdown: str,
            max_extract_attempts: int = 3,
            preferred_position_paths: Optional[List[str]] = None,
    ) -> Any:
        """
        将与查询相关的文本块提取出来，获取信息
        :param node: 根节点
        :param max_extract_attempts: 最大抽取尝试次数
        :return:
        """
        with open(os.path.join(PROMPT_DIR, "dive_down.md"), "r", encoding="utf-8") as f:
            sys_dive_prompt = f.read()

        with open(os.path.join(PROMPT_DIR, "extract_info_multiple.md"), "r", encoding="utf-8") as f:
            sys_extract_info_multiple = f.read()

        stack = [node]
        original_text = ""
        selected_paths: List[str] = []
        used_position_cache = False
        print("开始遍历寻找信息")

        if preferred_position_paths:
            cached_text, matched_paths = self._build_original_text_from_paths(node, preferred_position_paths)
            if matched_paths and len(matched_paths) >= max(1, int(len(preferred_position_paths) * 0.6)):
                original_text = cached_text
                selected_paths.extend(matched_paths)
                used_position_cache = True

        while stack and not used_position_cache:
            current_node = stack.pop()
            frontier_nodes, frontier_depth = self._build_dynamic_frontier(current_node)

            cur_info = f"用户查询：{self.rewrited_query} \n"
            cur_info += f"当前 HTML 的大致结构：{markdown}"
            cur_info += f"当前输入：{current_node.information} ->"

            node_dict: Dict[int, HTMLNode] = {}
            node_index = 1

            # 进入下探式文本获取
            for candidate in frontier_nodes:
                if candidate.information and candidate.information.strip():
                    cur_info = (f"{cur_info}\n\n\n---\n节点ID: {node_index}\n内容: {candidate.information}\n---")
                    node_dict[node_index] = candidate
                    node_index += 1

            if not node_dict:
                if current_node.information and current_node.information.strip():
                    original_text += f"{current_node.information}\n"
                    original_text += "---------------------------------------------------"
                    if current_node.original_tag_path:
                        selected_paths.append(current_node.original_tag_path)
                continue

            # 获取相关信息项
            reply = self.llm_client.invoke(user_prompt=cur_info, system_prompt=sys_dive_prompt, effert="none")
            print(f"当前输入信息：{cur_info}")
            print(f"当前回复：{reply}")
            print("......................................")

            try:
                if "<contain>" not in reply or "</contain>" not in reply:
                    raise ValueError("回复中缺少 <contain> 标签")

                reply = reply.split("<contain>")[1].split("</contain>")[0].strip()
                reply = reply.split(",")

                reply = [re.strip() for re in reply if re.strip()]

                # 如果模型认为不存在包含有用信息的节点，直接跳到处理下一个节点
                if not reply:
                    continue

                # 检查输出节点是否存在
                for repl in reply:
                    repl_stripped = repl.strip()
                    if repl_stripped.isdigit():
                        repl_int = int(repl_stripped)
                        if repl_int not in node_dict:
                            raise ValueError(f"输出了不存在的节点: {repl_int}")
                    else:
                        raise ValueError(f"输出格式错误，期望数字: {repl_stripped}")

            except Exception as e:
                print(f"[ERROR]{str(e)}")
                # 如果提取失败则再进行一次询问提取
                cur_info += f"你之前输出了不存在的节点：{str(e)}，请检查"
                reply = self.llm_client.invoke(user_prompt=cur_info, system_prompt=sys_dive_prompt)

                try:
                    # 再次检查标签
                    if "<contain>" not in reply or "</contain>" not in reply:
                        raise ValueError("回复中缺少 <contain> 标签")

                    reply = reply.split("<contain>")[1].split("</contain>")[0]
                    reply = reply.split(",")

                    has_mistakes = False

                    # 如果还有问题，就把所有子节点都加入待选节点
                    for repl in reply:
                        repl_stripped = repl.strip()
                        if repl_stripped.isdigit():
                            repl_int = int(repl_stripped)
                            if repl_int not in node_dict:
                                has_mistakes = True
                        else:
                            has_mistakes = True

                    if has_mistakes:
                        reply = [str(i) for i in range(1, node_index)]
                except Exception as e2:
                    print(f"[ERROR] 第二次提取也失败: {str(e2)}")
                    reply = [str(i) for i in range(1, node_index)]

            for re in reply:
                if re.strip().isdigit():
                    child_node = node_dict[int(re.strip())]

                    if child_node.child_node_count() == 0:
                        original_text += f"{child_node.original_html}\n"
                        original_text += "---------------------------------------------------"
                        if child_node.original_tag_path:
                            selected_paths.append(child_node.original_tag_path)

                    else:
                        stack.append(child_node)

                else:
                    print("提取失败")

        if self.json_model is not None:
            if isinstance(self.json_model, (dict, list)):
                schema_text = json.dumps(self.json_model, ensure_ascii=False)
            elif hasattr(self.json_model, "model_json_schema"):
                schema_text = self.json_model.model_json_schema()
            else:
                schema_text = self.json_model.schema()
            schema_prompt = f"请你输出一个严格符合以下 JSON Schema 的 JSON：{schema_text}"
        else:
            schema_prompt = "请你输出标准 JSON（必须是合法 JSON，不要附加解释文本）"

        user_prompt = f"""
    # 原始查询：{self.rewrited_query}\n\n
    # {schema_prompt}
    # 原始信息项如下，按横线划分：
        {original_text}"""
        print(f"当前输入:{user_prompt}")

        last_error = None

        for attempt in range(1, max_extract_attempts + 1):
            info_response = self.llm_client.invoke(
                user_prompt=user_prompt,
                system_prompt=sys_extract_info_multiple
            )
            print(f"检索到回复(第{attempt}次):\n{info_response}")

            extracted_items = self._extract_json_text(info_response)
            json_data, json_error = self._load_json_with_error(extracted_items)

            if json_error is not None:
                last_error = f"JSON 解析失败：{json_error}"
            else:
                pydantic_error = None
                if self.json_model is not None and not isinstance(self.json_model, (dict, list)):
                    _, pydantic_error = self._validate_with_pydantic(self.json_model, json_data)

                if pydantic_error is None:
                    self._last_selected_paths = self._dedupe_preserve_order(selected_paths)
                    self._last_position_cache_used = used_position_cache
                    return json_data

                last_error = f"Pydantic 校验失败：{pydantic_error}"

            if attempt < max_extract_attempts:
                user_prompt = f"""
            # 原始查询：{self.rewrited_query}\n\n
            # {schema_prompt}
            # 原始信息项如下，按横线划分：
                {original_text}
    
                上一次输出（原始）：
                {info_response}
    
                上一次输出（提取到的 JSON 片段）：
                {extracted_items}
    
                错误信息：
                {last_error}
    
                请修正并仅输出符合要求的标准 JSON，不要包含解释文本。
                """

        raise ValueError(
            f"超出最大尝试次数({max_extract_attempts})，最后一次错误：{last_error}"
        )

    def extract_from_html(
            self,
            max_extract_attempts: int = 3,
    ):
        """
        入口函数，完成整个流程
        :param max_extract_attempts: 最大抽取尝试次数
        :return: 所需结果
        """
        self.rewrite_query()
        required_info = []
        self.last_selected_paths_per_page = []
        self.last_position_cache_used_per_page = []
        for idx, (bs, markdown) in enumerate(zip(self.bss, self.markdowns)):

            initial_node = self.merge_information(bs)
            self.nodes.append(initial_node)  # 保存

            result = self.collect_information(
                node=initial_node,
                markdown=markdown,
                max_extract_attempts=max_extract_attempts,
                preferred_position_paths=self.cached_position_paths[idx] if idx < len(self.cached_position_paths) else None,
            )
            self.last_selected_paths_per_page.append(getattr(self, "_last_selected_paths", []))
            self.last_position_cache_used_per_page.append(getattr(self, "_last_position_cache_used", False))

            required_info.append(result)

        return required_info


def get_html_from_url(url: str, timeout: int = 10, encoding: Optional[str] = None) -> str:
    """
    根据 URL 获取网页 HTML，测试用
    """
    if not url:
        raise ValueError("url 不能为空")

    def _decode_html_bytes(raw_bytes: bytes, declared_encoding: Optional[str]) -> str:
        if encoding:
            return raw_bytes.decode(encoding, errors="replace")

        def _looks_like_mojibake(text: str) -> bool:
            markers = ("Ã", "Â", "ç", "é¢", "å", "ä¸", "ï¼")
            hit = sum(1 for marker in markers if marker in text)
            return hit >= 2

        decode_candidates: List[str] = []
        for candidate in (
                declared_encoding,
                "utf-8",
                "gb18030",
                "gbk",
                "big5",
        ):
            if not candidate:
                continue
            normalized = candidate.lower()
            if normalized not in [enc.lower() for enc in decode_candidates]:
                decode_candidates.append(candidate)

        best_text = ""
        best_bad_score = float("inf")

        for candidate in decode_candidates:
            try:
                decoded_text = raw_bytes.decode(candidate, errors="replace")
            except Exception:
                continue

            replacement_count = decoded_text.count("\ufffd")
            mojibake_penalty = 1000 if _looks_like_mojibake(decoded_text) else 0
            bad_score = replacement_count + mojibake_penalty

            if bad_score < best_bad_score:
                best_bad_score = bad_score
                best_text = decoded_text

            if bad_score == 0:
                break

        if best_text:
            return best_text

        return raw_bytes.decode("utf-8", errors="replace")

    ua = UserAgent()
    headers = {"User-Agent": ua.random}

    # 优先使用浏览器渲染，确保拿到 JS 执行后的完整 DOM
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=headers["User-Agent"])
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 12000))
            except Exception:
                pass
            page.wait_for_timeout(600)
            html = page.content()
            browser.close()
            if html and html.strip():
                return html
    except Exception:
        pass

    # 浏览器路径不可用时，回退 requests
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return _decode_html_bytes(response.content, response.encoding)


if __name__ == '__main__':
    class newsModel(BaseModel):
        title: str = Field(description="新闻标题")
        publish_time: str = Field(description="发布时间")

    class newsList(BaseModel):
        items: List[newsModel]


    class questionModel(BaseModel):
        questionTitle: str = Field(description="题目名称")
        difficulty: str = Field(description="题目难度")

    class typeList(BaseModel):
        type: str = Field(description="题目类型")
        questions: List[questionModel]

    class questionList(BaseModel):
        types: List[typeList]

    llm_client = LLMClient(
        api_key=os.environ.get("WCODE_API_KEY"),
        model_name="qwen/qwen3.5-9b",
        url="https://wcode.net/api/gpt/v1",
    )

    print(str(getattr(llm_client, "api_key", "")))

    urls = ["https://www.shaanxi.gov.cn/xw/"]
    htmls = []
    for url in urls:
        htmls.append(get_html_from_url(url))

    html_extractor = HTMLRecursiveExtractor(
        llm_client=llm_client,
        urls=urls,
        htmls=htmls,
        json_model=newsList,
        query="帮我提取网页中的要闻"
    )

    ans = html_extractor.extract_from_html()
    for a in ans:
        print(a)
