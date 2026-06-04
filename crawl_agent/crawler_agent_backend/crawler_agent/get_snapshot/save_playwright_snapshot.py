import asyncio
from pathlib import Path
import uuid

from agentscope.mcp import StdIOStatefulClient
from agentscope.message import ToolUseBlock
from agentscope.tool import Toolkit


PAGE_URL = "https://re.jd.com/search?keyword=%E6%96%87%E5%85%B7%E7%94%A8%E5%93%81&ad_od=3&re_dcp=21Sm2D2ZOw&traffic_source=1004&bd_vid=&cu=true&utm_source=haosou-search&utm_medium=cpc&utm_campaign=t_262767352_haosousearch&utm_term=72415908353_0_7c8e8ef3d88e4cc598d81b8eb743a8d1"
OUTPUT_PATH = Path(__file__).resolve().parent / "page_snapshot.md"


async def _collect_tool_text(tool_response) -> str:
    chunks = []
    async for chunk in tool_response:
        if not chunk.content:
            continue
        for block in chunk.content:
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


async def _call_tool(toolkit: Toolkit, name: str, tool_input: dict) -> str:
    tool_call = ToolUseBlock(
        type="tool_use",
        id=str(uuid.uuid4()),
        name=name,
        input=tool_input,
    )
    response = await toolkit.call_tool_function(tool_call)
    return await _collect_tool_text(response)


async def main() -> None:
    toolkit = Toolkit()
    browser_client = StdIOStatefulClient(
        name="playwright-mcp",
        command="npx",
        args=["@playwright/mcp@latest"],
    )

    try:
        await browser_client.connect()
        await toolkit.register_mcp_client(browser_client)

        navigate_result = await _call_tool(
            toolkit,
            "browser_navigate",
            {"url": PAGE_URL},
        )
        snapshot_result = await _call_tool(toolkit, "browser_snapshot", {})

        markdown = "\n\n".join(
            [
                f"# Page Snapshot",
                f"- URL: {PAGE_URL}",
                "",
                "## Navigate Result",
                navigate_result or "(empty)",
                "",
                "## Snapshot",
                snapshot_result or "(empty)",
            ]
        )
        OUTPUT_PATH.write_text(markdown, encoding="utf-8")
        print(f"Snapshot saved to: {OUTPUT_PATH}")
    finally:
        await browser_client.close()


if __name__ == "__main__":
    asyncio.run(main())
