"""Web search tool using Bing (with Baidu fallback)"""
import re
import logging
from urllib.parse import quote_plus
import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索查询关键词")
    max_results: int = Field(default=5, description="返回的最大结果数 (1-10)")


def _web_search(query: str, max_results: int = 5) -> str:
    """搜索网页并返回结果摘要"""
    max_results = max(1, min(max_results, 10))

    for engine in ["bing", "baidu"]:
        try:
            if engine == "bing":
                results = _search_bing(query, max_results)
            else:
                results = _search_baidu(query, max_results)

            if results:
                results.append(
                    "请基于以上搜索结果回答用户问题。"
                    "用你自己的语言综合整理，引用时注明来源 URL。"
                )
                return "\n\n".join(results)
        except Exception as e:
            logger.warning(f"{engine} search failed: {e}")
            continue

    return f"搜索 \"{query}\" 暂时失败，请稍后重试。"


def _search_bing(query: str, max_results: int) -> list[str]:
    """Bing 搜索"""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=zh-cn"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    html = resp.text

    results = []

    # 匹配 b_algo 块: <li ... b_algo ...> 直到下一个 <li ... 或结束
    # 使用向前查找来定位每个结果块的边界
    block_pattern = re.compile(
        r'<li[^>]*\bb_algo\b[^>]*>(.*?)(?=<li[^>]*\bb_algo\b|</ol>)', re.DOTALL
    )
    blocks = block_pattern.findall(html)

    for block in blocks[:max_results]:
        # 提取 <h2> 中的链接（这是真正的搜索结果链接）
        h2_match = re.search(
            r'<h2[^>]*>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>(.+?)</a>', block, re.DOTALL
        )
        if not h2_match:
            continue

        href = h2_match.group(1)
        title = re.sub(r'<[^>]+>', '', h2_match.group(2)).strip()
        # 解码 HTML 实体
        title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

        # 提取 b_caption 中的摘要
        snippet = ""
        caption_match = re.search(
            r'<div class="b_caption"[^>]*>(.*?)</div>', block, re.DOTALL
        )
        if caption_match:
            snippet = re.sub(r'<[^>]+>', ' ', caption_match.group(1)).strip()
            snippet = re.sub(r'\s+', ' ', snippet)[:300]

        results.append(
            f"--- 搜索结果 {len(results) + 1} ---\n"
            f"标题: {title}\n"
            f"URL: {href}\n"
            f"摘要: {snippet}\n"
        )

    return results


def _search_baidu(query: str, max_results: int) -> list[str]:
    """Baidu 搜索 (降级方案)"""
    url = f"https://www.baidu.com/s?wd={quote_plus(query)}"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    html = resp.text

    results = []
    # 匹配 Baidu 结果: <div ... class="result c-container" ...>
    block_pattern = re.compile(
        r'<div[^>]*\bresult\b[^>]*\bc-container\b[^>]*>(.*?)</div>\s*</div>\s*</div>', re.DOTALL
    )
    blocks = block_pattern.findall(html)

    for block in blocks[:max_results]:
        # 提取 <h3> 中的链接
        link_match = re.search(
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.+?)</a>', block, re.DOTALL
        )
        if not link_match:
            continue

        href = link_match.group(1)
        title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()

        # 提取摘要
        snippet = ""
        snippet_match = re.search(
            r'<span[^>]*class="[^"]*content-right_[^"]*"[^>]*>(.+?)</span>', block, re.DOTALL
        )
        if not snippet_match:
            snippet_match = re.search(
                r'<span[^>]*class="[^"]*content[^"]*"[^>]*>(.+?)</span>', block, re.DOTALL
            )
        if snippet_match:
            snippet = re.sub(r'<[^>]+>', ' ', snippet_match.group(1)).strip()
            snippet = re.sub(r'\s+', ' ', snippet)[:300]

        results.append(
            f"--- 搜索结果 {len(results) + 1} ---\n"
            f"标题: {title}\n"
            f"URL: {href}\n"
            f"摘要: {snippet}\n"
        )

    return results


web_search_tool = StructuredTool.from_function(
    name="web_search",
    description="搜索互联网获取信息。输入关键词，返回搜索结果列表（标题+URL+摘要）。",
    func=_web_search,
    args_schema=WebSearchInput,
)
