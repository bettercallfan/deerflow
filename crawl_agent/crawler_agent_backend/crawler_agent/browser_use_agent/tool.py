"""Browser agent tool functions and shared state."""
import asyncio
import base64
import hashlib
import json
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from agentscope.message import TextBlock, ToolUseBlock
from agentscope.tool import Toolkit, ToolResponse

_collected_pages: List[Dict[str, Any]] = []
_collected_page_keys: set[str] = set()
_active_toolkit: Optional[Toolkit] = None


def reset_browser_tool_state() -> None:
    """Reset collected pages and bound toolkit."""
    global _collected_pages, _collected_page_keys, _active_toolkit
    _collected_pages = []
    _collected_page_keys = set()
    _active_toolkit = None


def set_browser_toolkit(toolkit: Optional[Toolkit]) -> None:
    """Bind or clear the active toolkit used by browser tools."""
    global _active_toolkit
    _active_toolkit = toolkit


def get_collected_pages() -> List[Dict[str, Any]]:
    """Return collected pages."""
    return _collected_pages


def append_url_only_page(url: str) -> bool:
    """Append a URL-only record when the agent only returns the URL in text."""
    global _collected_pages

    existing_urls = {item.get("url", "") for item in _collected_pages}
    if url in existing_urls:
        return False

    _collected_pages.append(
        {
            "url": url,
            "title": "",
            "html": "",
            "html_hash": "",
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "capture_method": "final_text_url_only",
        },
    )
    return True


async def _extract_text_from_tool_response(tool_response: Any) -> str:
    texts: List[str] = []
    async for chunk in tool_response:
        for block in chunk.content or []:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    texts.append(block.get("text"))
            else:
                text = getattr(block, "text", None)
                if text:
                    texts.append(text)
    return "\n".join(texts)


def _parse_any_json_payload(raw_text: str) -> Any:
    candidates: List[str] = []

    result_block = re.search(r"### Result\s*([\s\S]*?)(?:\n### |\Z)", raw_text)
    if result_block:
        candidates.append(result_block.group(1).strip())

    candidates.extend(
        x.strip() for x in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
    )
    candidates.append(raw_text.strip())

    for candidate in candidates:
        if not candidate:
            continue

        try:
            return json.loads(candidate)
        except Exception:
            pass

        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", candidate)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

    raise ValueError(f"无法从 browser_evaluate 返回中解析 JSON: {raw_text[:500]}")


async def _browser_evaluate_json(function_source: str) -> Any:
    global _active_toolkit

    if _active_toolkit is None:
        raise RuntimeError("当前工具环境未初始化，无法调用 browser_evaluate。")

    evaluate_call = ToolUseBlock(
        id=str(uuid.uuid4()),
        type="tool_use",
        name="browser_evaluate",
        input={"function": function_source},
    )
    evaluate_response = await _active_toolkit.call_tool_function(evaluate_call)
    evaluate_text = await _extract_text_from_tool_response(evaluate_response)
    return _parse_any_json_payload(evaluate_text)


def _store_page_record(url: str, title: str, html: str, capture_method: str) -> bool:
    global _collected_pages, _collected_page_keys

    if not html:
        return False

    page_key = hashlib.sha256(f"{url}\n{html}".encode("utf-8")).hexdigest()
    if page_key in _collected_page_keys:
        return False

    _collected_pages.append(
        {
            "url": url,
            "title": title,
            "html": html,
            "html_hash": page_key,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "capture_method": capture_method,
        }
    )
    _collected_page_keys.add(page_key)
    return True


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip().strip(".")
    return name or f"download_{uuid.uuid4().hex[:8]}"


def _normalize_optional_string(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    normalized = value.strip()
    return normalized or None


def _normalize_string_list_param(
    value: Optional[Any],
    default: Optional[List[str]] = None,
) -> List[str]:
    """Normalize tool inputs that may arrive as list, JSON string, or plain string."""
    if value is None:
        return list(default or [])

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return list(default or [])

        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

        if "," in stripped:
            parts = [part.strip() for part in stripped.split(",")]
            return [part for part in parts if part]

        return [stripped]

    return [str(value).strip()] if str(value).strip() else list(default or [])


def _filename_from_content_disposition(content_disposition: str) -> Optional[str]:
    if not content_disposition:
        return None

    match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.I)
    if match:
        return unquote(match.group(1))

    match = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.I)
    if match:
        return match.group(1)

    return None


def _choose_download_filename(
    final_url: str,
    content_type: str,
    content_disposition: str,
    preferred_name: Optional[str],
) -> str:
    if preferred_name:
        name = preferred_name
    else:
        name = _filename_from_content_disposition(content_disposition)
        if not name:
            parsed = urlparse(final_url)
            name = unquote(Path(parsed.path).name) or f"download_{uuid.uuid4().hex[:8]}"

    if "." not in Path(name).name:
        ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
        name = f"{name}{ext}"

    return _safe_filename(name)


def _direct_http_download(url: str, referer: Optional[str], max_bytes: int) -> Dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer

    req = Request(url, headers=headers)
    with urlopen(req, timeout=60) as resp:
        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"文件过大，超过限制 {max_bytes} bytes")

        content_type = resp.headers.get("Content-Type", "")
        content_disposition = resp.headers.get("Content-Disposition", "")
        final_url = resp.geturl()

    return {
        "ok": True,
        "status": 200,
        "finalUrl": final_url,
        "contentType": content_type,
        "contentDisposition": content_disposition,
        "size": len(data),
        "bytes": data,
    }


async def save_url(url: str) -> ToolResponse:
    """{保存当前浏览器页面的 URL 和 DOM HTML 到全局结果集中}

    Args:
        url (str):
            {需要保存的当前页面 URL，用于校验和记录页面来源}
    """
    url = url.strip()

    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    if not re.fullmatch(url_pattern, url):
        return ToolResponse(
            content=[TextBlock(type="text", text=f"输入了无效的url: {url}")]
        )

    if _active_toolkit is None:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="保存失败：当前工具环境未初始化，无法获取浏览器当前页HTML。",
                )
            ]
        )

    try:
        payload = await _browser_evaluate_json(
            """
            () => ({
                url: window.location.href || "",
                title: document.title || "",
                html: document.documentElement ? document.documentElement.outerHTML : ""
            })
            """
        )
        current_url = str(payload.get("url", "") or url)
        title = str(payload.get("title", "") or "")
        html = str(payload.get("html", "") or "")
    except Exception as error:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"保存失败：读取当前页面HTML时报错：{str(error)}",
                )
            ]
        )

    if not html:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="保存失败：未获取到当前浏览页HTML，请确认页面已加载完成后重试。",
                )
            ]
        )

    created = _store_page_record(
        url=current_url,
        title=title,
        html=html,
        capture_method="agent_current_dom",
    )

    if created:
        print(f"将url:{url}及当前页面HTML保存成功")
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        f"成功保存当前页面：url={current_url}，title={title or 'N/A'}，"
                        f"html_length={len(html)}"
                    ),
                )
            ]
        )

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=(
                    f"url: {current_url} 的当前HTML版本已保存过（按 url+html 去重），"
                    "不需要重复保存。"
                ),
            )
        ]
    )


def view_url() -> ToolResponse:
    """{查看当前已经保存的页面 URL、标题、保存时间和 HTML 长度}"""
    if not _collected_pages:
        url_text = "当前没有已保存页面"
    else:
        lines = []
        for idx, item in enumerate(_collected_pages, start=1):
            lines.append(
                f"{idx}. {item['url']} | title={item.get('title', '') or 'N/A'} | "
                f"saved_at={item.get('saved_at', '')} | "
                f"html_length={len(item.get('html', ''))}"
            )
        url_text = "\n".join(lines)

    return ToolResponse(content=[TextBlock(type="text", text=url_text)])


async def download_file(
    url: str,
    save_dir: str = "./downloads",
    filename: Optional[str] = None,
    max_bytes: int = 30 * 1024 * 1024,
) -> ToolResponse:
    """{下载文件到本地，优先复用当前浏览器会话以支持登录态下载}

    Args:
        url (str):
            {待下载文件的 URL，支持绝对地址，也支持相对当前页面的相对地址}
        save_dir (str):
            {下载文件保存到的本地目录路径}
        filename (Optional[str]):
            {可选的目标文件名，不传时会根据响应头或 URL 自动推断}
        max_bytes (int):
            {允许下载的最大字节数，超过该大小时工具会直接返回失败}
    """
    url = url.strip()
    if not url:
        return ToolResponse(
            content=[TextBlock(type="text", text="下载失败：url 不能为空")]
        )

    absolute_url = url
    referer = None

    if not re.match(r"^https?://", absolute_url, flags=re.I):
        try:
            page_info = await _browser_evaluate_json(
                "() => ({ url: window.location.href || '', title: document.title || '' })"
            )
            referer = page_info.get("url") or None
            absolute_url = urljoin(page_info.get("url", ""), absolute_url)
        except Exception:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"下载失败：相对路径无法解析，url={url}",
                    )
                ]
            )

    save_root = Path(save_dir).expanduser().resolve()
    save_root.mkdir(parents=True, exist_ok=True)

    browser_payload = None
    if _active_toolkit is not None:
        js = f"""
        async () => {{
            try {{
                const targetUrl = {json.dumps(absolute_url)};
                const maxBytes = {max_bytes};
                const resp = await fetch(targetUrl, {{
                    method: "GET",
                    credentials: "include",
                    redirect: "follow",
                }});

                const contentType = resp.headers.get("content-type") || "";
                const contentDisposition = resp.headers.get("content-disposition") || "";
                const contentLength = Number(resp.headers.get("content-length") || "0");

                if (!resp.ok) {{
                    return {{
                        ok: false,
                        status: resp.status,
                        statusText: resp.statusText,
                        finalUrl: resp.url,
                        contentType,
                        contentDisposition,
                        reason: "http_error"
                    }};
                }}

                if (contentLength && contentLength > maxBytes) {{
                    return {{
                        ok: false,
                        status: resp.status,
                        finalUrl: resp.url,
                        contentType,
                        contentDisposition,
                        reason: "file_too_large"
                    }};
                }}

                const blob = await resp.blob();
                if (blob.size > maxBytes) {{
                    return {{
                        ok: false,
                        status: resp.status,
                        finalUrl: resp.url,
                        contentType,
                        contentDisposition,
                        reason: "file_too_large"
                    }};
                }}

                const bodyBase64 = await new Promise((resolve, reject) => {{
                    const reader = new FileReader();
                    reader.onload = () => {{
                        const result = String(reader.result || "");
                        const parts = result.split(",", 2);
                        resolve(parts.length === 2 ? parts[1] : "");
                    }};
                    reader.onerror = () => reject(new Error("FileReader failed"));
                    reader.readAsDataURL(blob);
                }});

                return {{
                    ok: true,
                    status: resp.status,
                    finalUrl: resp.url,
                    contentType,
                    contentDisposition,
                    size: blob.size,
                    bodyBase64
                }};
            }} catch (error) {{
                return {{
                    ok: false,
                    reason: "browser_fetch_failed",
                    error: String(error)
                }};
            }}
        }}
        """
        try:
            browser_payload = await _browser_evaluate_json(js)
        except Exception:
            browser_payload = None

    try:
        if browser_payload and browser_payload.get("ok"):
            download_payload = {
                "ok": True,
                "status": browser_payload.get("status", 200),
                "finalUrl": browser_payload.get("finalUrl", absolute_url),
                "contentType": browser_payload.get("contentType", ""),
                "contentDisposition": browser_payload.get("contentDisposition", ""),
                "size": int(browser_payload.get("size", 0) or 0),
                "bytes": base64.b64decode(browser_payload.get("bodyBase64", "")),
            }
        elif browser_payload and browser_payload.get("reason") == "file_too_large":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"下载失败：文件过大，超过限制 {max_bytes} bytes",
                    )
                ]
            )
        else:
            download_payload = await asyncio.to_thread(
                _direct_http_download,
                absolute_url,
                referer,
                max_bytes,
            )
    except Exception as error:
        return ToolResponse(
            content=[TextBlock(type="text", text=f"下载失败：{str(error)}")]
        )

    final_url = download_payload.get("finalUrl", absolute_url)
    content_type = download_payload.get("contentType", "")
    content_disposition = download_payload.get("contentDisposition", "")
    data = download_payload["bytes"]

    final_name = _choose_download_filename(
        final_url=final_url,
        content_type=content_type,
        content_disposition=content_disposition,
        preferred_name=filename,
    )
    file_path = save_root / final_name
    file_path.write_bytes(data)

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=(
                    "下载成功：\n"
                    f"- url: {final_url}\n"
                    f"- path: {file_path}\n"
                    f"- size: {len(data)} bytes\n"
                    f"- content_type: {content_type or 'unknown'}"
                ),
            )
        ]
    )


async def auto_save_paginated_pages(
    max_pages: int = 1000,
    item_selector: Optional[str] = None,
    next_selectors: Optional[List[str]] = None,
    same_origin_only: bool = True,
    wait_after_click_ms: int = 2000,
    min_items_per_page: int = 2,
    stop_if_no_new_items: bool = True,
) -> ToolResponse:
    """{自动遍历当前列表页的分页，并调用 save_url 工具保存每一页的 URL 与 HTML}

    Args:
        max_pages (int):
            {最多遍历的分页数量，用于防止死循环，默认值 1000，通常不需要设置}
        item_selector (Optional[str]):
            {可选的列表项 CSS 选择器，传入后会优先按该选择器识别当前页的列表项}
        next_selectors (Optional[List[str]]):
            {可选的下一页按钮 CSS 选择器列表，工具会按顺序优先尝试这些选择器}
        same_origin_only (bool):
            {是否只允许点击当前站点同源的下一页链接，避免误跳出站}
        wait_after_click_ms (int):
            {点击下一页后每轮等待页面变化的毫秒数，默认值 2000}
        min_items_per_page (int):
            {识别列表结构时要求当前页至少命中的最少列表项数量}
        stop_if_no_new_items (bool):
            {当翻到新页后没有识别出新的列表项时，是否立即停止分页遍历，默认为 True}
    """
    default_next_selectors = [
        "a[rel='next']",
        "a.next",
        ".next a",
        ".pagination-next",
        "button.next",
        ".pager-next",
        ".page-next",
        ".next-page",
    ]
    next_selectors = _normalize_string_list_param(
        next_selectors,
        default=default_next_selectors,
    )
    item_selector = _normalize_optional_string(item_selector)

    before_count = len(_collected_pages)
    seen_page_signatures: set[str] = set()
    seen_item_keys: set[str] = set()

    recorded_item_selector = item_selector
    recorded_next_selector: Optional[str] = None

    async def extract_page_bundle(preferred_item_selector: Optional[str]) -> Dict[str, Any]:
        js = f"""
        () => {{
            const preferredItemSelector = {json.dumps(preferred_item_selector)};
            const minItemsPerPage = {int(min_items_per_page)};
            const sameOriginOnly = {json.dumps(same_origin_only)};

            const esc = (value) => String(value || "")
                .replace(/([ !"#$%&'()*+,./:;<=>?@[\\\\\\]^`{{|}}~])/g, "\\\\$1");

            const normalize = (value) =>
                String(value || "").replace(/\\s+/g, " ").trim();

            const isVisible = (el) => {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return (
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            }};

            const stableClasses = (el) => {{
                return Array.from(el.classList || []).filter((cls) => {{
                    return (
                        cls &&
                        cls.length <= 40 &&
                        !/\\d{{4,}}/.test(cls) &&
                        !cls.includes(":") &&
                        !cls.includes("active") &&
                        !cls.includes("selected")
                    );
                }});
            }};

            const absUrl = (href) => {{
                if (!href) return "";
                try {{
                    return new URL(href, location.href).href;
                }} catch (e) {{
                    return "";
                }}
            }};

            const allowOrigin = (href) => {{
                if (!sameOriginOnly || !href) return true;
                try {{
                    return new URL(href, location.href).origin === location.origin;
                }} catch (e) {{
                    return true;
                }}
            }};

            const buildSelector = (el, maxDepth = 4) => {{
                if (!el || el.nodeType !== 1) return "";
                if (el.id && !/^\\d+$/.test(el.id)) {{
                    return `#${{esc(el.id)}}`;
                }}

                const parts = [];
                let cur = el;
                let depth = 0;

                while (cur && cur.nodeType === 1 && cur !== document.body && depth < maxDepth) {{
                    let seg = cur.tagName.toLowerCase();
                    const classes = stableClasses(cur).slice(0, 2);
                    if (classes.length) {{
                        seg += classes.map((c) => `.${{esc(c)}}`).join("");
                    }} else {{
                        const parent = cur.parentElement;
                        if (parent) {{
                            const sameTagSiblings = Array.from(parent.children).filter(
                                (x) => x.tagName === cur.tagName
                            );
                            if (sameTagSiblings.length > 1) {{
                                const index = sameTagSiblings.indexOf(cur) + 1;
                                seg += `:nth-of-type(${{index}})`;
                            }}
                        }}
                    }}
                    parts.unshift(seg);

                    if (cur.parentElement && cur.parentElement.id && !/^\\d+$/.test(cur.parentElement.id)) {{
                        parts.unshift(`#${{esc(cur.parentElement.id)}}`);
                        break;
                    }}

                    cur = cur.parentElement;
                    depth += 1;
                }}

                return parts.join(" > ");
            }};

            const intersectClasses = (elements) => {{
                if (!elements.length) return [];
                let common = new Set(stableClasses(elements[0]));
                for (const el of elements.slice(1, 8)) {{
                    const cur = new Set(stableClasses(el));
                    common = new Set(Array.from(common).filter((c) => cur.has(c)));
                }}
                return Array.from(common).slice(0, 2);
            }};

            const scoreItems = (elements) => {{
                if (!elements.length) return -1;
                const linkCount = elements.filter((el) => el.querySelector("a[href]")).length;
                const textLens = elements.map((el) => normalize(el.innerText || "").length);
                const avgTextLen = textLens.reduce((a, b) => a + b, 0) / Math.max(1, textLens.length);
                const tag = elements[0].tagName.toLowerCase();

                let score = 0;
                score += Math.min(elements.length, 40) * 10;
                score += Math.min(avgTextLen, 200) * 0.2;
                score += linkCount * 3;

                if (tag === "article") score += 20;
                if (tag === "li") score += 10;
                if (tag === "tr") score += 8;

                return score;
            }};

            const candidateBundles = [];

            const pushCandidate = (selector, elements, source) => {{
                const visibleItems = elements.filter(isVisible);
                if (visibleItems.length < minItemsPerPage) return;

                const itemWithText = visibleItems.filter(
                    (el) => normalize(el.innerText || "").length >= 8
                );
                if (itemWithText.length < minItemsPerPage) return;

                candidateBundles.push({{
                    selector,
                    source,
                    score: scoreItems(itemWithText),
                    elements: itemWithText.slice(0, 100),
                }});
            }};

            if (preferredItemSelector) {{
                try {{
                    const nodes = Array.from(document.querySelectorAll(preferredItemSelector));
                    pushCandidate(preferredItemSelector, nodes, "preferred");
                }} catch (e) {{}}
            }}

            const knownSelectors = [
                "article",
                "main article",
                "li",
                "ul > li",
                "ol > li",
                ".list-item",
                ".item",
                ".items > *",
                ".results > *",
                ".result",
                ".result-item",
                ".job",
                ".job-item",
                ".jobs-list > *",
                ".post",
                ".post-item",
                ".posts-list > *",
                ".news-item",
                ".card",
                ".cards > *",
                "tbody > tr",
                "table tbody tr"
            ];

            for (const selector of knownSelectors) {{
                try {{
                    const nodes = Array.from(document.querySelectorAll(selector));
                    pushCandidate(selector, nodes, "known");
                }} catch (e) {{}}
            }}

            const parents = Array.from(
                document.querySelectorAll("main, section, div, ul, ol, tbody, table, article")
            ).slice(0, 1200);

            for (const parent of parents) {{
                const children = Array.from(parent.children || []).filter(isVisible);
                if (children.length < minItemsPerPage || children.length > 200) continue;

                const groups = new Map();
                for (const child of children) {{
                    const tag = child.tagName.toLowerCase();
                    const cls = stableClasses(child).slice(0, 2).sort().join(".");
                    const key = `${{tag}}|${{cls}}`;
                    if (!groups.has(key)) groups.set(key, []);
                    groups.get(key).push(child);
                }}

                for (const elements of groups.values()) {{
                    if (elements.length < minItemsPerPage) continue;

                    const parentSelector = buildSelector(parent, 3);
                    const tag = elements[0].tagName.toLowerCase();
                    const commonClasses = intersectClasses(elements);
                    let childSelector = tag;
                    if (commonClasses.length) {{
                        childSelector += commonClasses.map((c) => `.${{esc(c)}}`).join("");
                    }}

                    const fullSelector = parentSelector
                        ? `${{parentSelector}} > ${{childSelector}}`
                        : childSelector;

                    pushCandidate(fullSelector, elements, "repeated_children");
                }}
            }}

            candidateBundles.sort((a, b) => b.score - a.score);

            const picked = candidateBundles.length
                ? candidateBundles[0]
                : {{
                    selector: preferredItemSelector || "",
                    source: "fallback",
                    score: -1,
                    elements: []
                }};

            const itemElements = picked.elements || [];
            const items = itemElements.map((el, idx) => {{
                const anchors = Array.from(el.querySelectorAll("a[href]")).filter(isVisible);
                const mainAnchor = anchors.find((a) => allowOrigin(a.getAttribute("href") || a.href || "")) || anchors[0] || null;

                const heading =
                    el.querySelector("h1, h2, h3, h4, h5, h6") ||
                    mainAnchor ||
                    null;

                const rawTitle = heading
                    ? normalize(heading.innerText || heading.textContent || "")
                    : normalize(el.innerText || "");

                const text = normalize(el.innerText || el.textContent || "");
                const link = mainAnchor ? absUrl(mainAnchor.getAttribute("href") || mainAnchor.href || "") : "";
                const key = link || rawTitle || `${{idx}}::${{text.slice(0, 120)}}`;

                return {{
                    key,
                    url: link,
                    title: rawTitle.slice(0, 300),
                    text_preview: text.slice(0, 500),
                }};
            }});

            const itemKeys = items.map((x) => x.key);
            const itemSignature = itemKeys.join("\\n");

            return {{
                page: {{
                    url: window.location.href || "",
                    title: document.title || "",
                    html: document.documentElement ? document.documentElement.outerHTML : "",
                    readyState: document.readyState || "",
                }},
                list: {{
                    item_selector: picked.selector || "",
                    selector_source: picked.source || "",
                    item_count: items.length,
                    items,
                    item_keys: itemKeys,
                    item_signature: itemSignature,
                }}
            }};
        }}
        """
        return await _browser_evaluate_json(js)

    async def click_next(preferred_next_selector: Optional[str]) -> Dict[str, Any]:
        selector_candidates: List[str] = []
        if preferred_next_selector:
            selector_candidates.append(preferred_next_selector)
        selector_candidates.extend(next_selectors)
        selector_candidates = [
            selector.strip()
            for selector in selector_candidates
            if isinstance(selector, str) and selector.strip() and len(selector.strip()) > 1
        ]

        js = f"""
        () => {{
            const selectorCandidates = {json.dumps(selector_candidates, ensure_ascii=False)};
            const sameOriginOnly = {json.dumps(same_origin_only)};

            const normalize = (value) =>
                String(value || "").replace(/\\s+/g, " ").trim();

            const normalizeSoft = (value) =>
                String(value || "").replace(/\\s+/g, "").trim().toLowerCase();

            const isVisible = (el) => {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return (
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            }};

            const isDisabled = (el) => {{
                const cls = normalizeSoft(el.className);
                const ariaDisabled = normalizeSoft(el.getAttribute("aria-disabled"));
                return !!el.disabled || ariaDisabled === "true" || cls.includes("disabled") || cls.includes("off");
            }};

            const allowOrigin = (el) => {{
                const href = el.href || el.getAttribute("href") || "";
                if (!sameOriginOnly || !href || href.startsWith("javascript:")) return true;
                try {{
                    return new URL(href, location.href).origin === location.origin;
                }} catch (e) {{
                    return true;
                }}
            }};

            for (const selector of selectorCandidates) {{
                if (!selector) continue;
                try {{
                    const el = document.querySelector(selector);
                    if (el && isVisible(el) && !isDisabled(el) && allowOrigin(el)) {{
                        el.scrollIntoView({{ block: "center" }});
                        el.click();
                        return {{
                            clicked: true,
                            strategy: "selector",
                            selector_used: selector,
                            text: normalize(el.innerText || el.textContent || el.value || "")
                        }};
                    }}
                }} catch (e) {{}}
            }}

            const nodes = Array.from(
                document.querySelectorAll("a, button, [role='button'], input[type='button'], input[type='submit']")
            );

            const candidates = nodes.map((el, index) => {{
                const text = normalize(el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || el.getAttribute("title") || "");
                const t = normalizeSoft(text);
                const cls = normalizeSoft(el.className);
                const rel = normalizeSoft(el.getAttribute("rel"));
                const href = el.href || el.getAttribute("href") || "";

                let score = 0;
                if (rel === "next") score += 120;
                if (t === "下一页" || t === "下页" || t === "next" || t === "nextpage") score += 100;
                if (t.includes("下一页") || t.includes("next")) score += 60;
                if (text === ">" || text === ">>" || text === "›" || text === "»") score += 50;
                if (cls.includes("next") || cls.includes("pager-next") || cls.includes("page-next")) score += 40;
                if (href && /(page|pageindex|pageno|paging|p=|offset=)/i.test(href)) score += 20;

                const rect = el.getBoundingClientRect();
                if (rect.top > window.innerHeight * 0.5) score += 10;

                return {{
                    index,
                    text,
                    score,
                    visible: isVisible(el),
                    disabled: isDisabled(el),
                    allowed: allowOrigin(el),
                }};
            }})
            .filter((x) => x.visible && !x.disabled && x.allowed && x.score > 0)
            .sort((a, b) => b.score - a.score);

            if (!candidates.length) {{
                return {{
                    clicked: false,
                    reason: "no_next_candidate"
                }};
            }}

            const target = nodes[candidates[0].index];
            target.scrollIntoView({{ block: "center" }});
            target.click();

            return {{
                clicked: true,
                strategy: "heuristic",
                selector_used: "",
                text: candidates[0].text
            }};
        }}
        """
        return await _browser_evaluate_json(js)

    def build_page_signature(bundle: Dict[str, Any]) -> str:
        page = bundle.get("page", {})
        item_keys = bundle.get("list", {}).get("item_keys", []) or []
        raw = (
            f"{page.get('url', '')}\n"
            f"{bundle.get('list', {}).get('item_selector', '')}\n"
            + "\n".join(item_keys)
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    for page_no in range(1, max_pages + 1):
        bundle = await extract_page_bundle(recorded_item_selector)
        page = bundle.get("page", {}) or {}
        list_info = bundle.get("list", {}) or {}
        current_items = list_info.get("items", []) or []

        current_page_signature = build_page_signature(bundle)
        if current_page_signature in seen_page_signatures:
            break
        seen_page_signatures.add(current_page_signature)

        detected_item_selector = list_info.get("item_selector", "") or ""
        if detected_item_selector and not recorded_item_selector:
            recorded_item_selector = detected_item_selector

        _store_page_record(
            url=page.get("url", ""),
            title=page.get("title", ""),
            html=page.get("html", ""),
            capture_method="auto_paginate_weblists_style",
        )

        new_items = []
        for item in current_items:
            key = str(item.get("key", "") or "").strip()
            if not key:
                continue
            if key not in seen_item_keys:
                seen_item_keys.add(key)
                new_items.append(item)

        if page_no > 1 and stop_if_no_new_items and not new_items:
            break

        if page_no >= max_pages:
            break

        click_result = await click_next(recorded_next_selector)
        if not click_result.get("clicked"):
            break

        if click_result.get("selector_used"):
            recorded_next_selector = click_result["selector_used"]

        previous_url = page.get("url", "")
        previous_item_signature = list_info.get("item_signature", "")
        changed = False

        max_wait_rounds = max(1, int(8000 / max(200, wait_after_click_ms)))
        for _ in range(max_wait_rounds):
            await asyncio.sleep(wait_after_click_ms / 1000.0)
            next_bundle = await extract_page_bundle(recorded_item_selector)
            next_page = next_bundle.get("page", {}) or {}
            next_list = next_bundle.get("list", {}) or {}

            if (
                next_page.get("url", "") != previous_url
                or next_list.get("item_signature", "") != previous_item_signature
            ):
                changed = True
                break

        if not changed:
            break

    new_pages = _collected_pages[before_count:]
    lines = [
        f"自动分页完成，共新增保存 {len(new_pages)} 页。",
        f"共识别到 {len(seen_item_keys)} 个唯一 item。",
        f"recorded_item_selector={recorded_item_selector or 'N/A'}",
        f"recorded_next_selector={recorded_next_selector or 'N/A'}",
    ]

    for idx, item in enumerate(new_pages, start=1):
        lines.append(
            f"{idx}. {item.get('url', '')} | title={item.get('title', '') or 'N/A'} | "
            f"html_length={len(item.get('html', ''))}"
        )

    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])


def register_browser_tools(toolkit: Toolkit) -> None:
    """Register all local browser helper tools onto the toolkit."""
    toolkit.register_tool_function(save_url)
    toolkit.register_tool_function(view_url)
    toolkit.register_tool_function(download_file)
    toolkit.register_tool_function(auto_save_paginated_pages)
