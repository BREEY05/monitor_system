"""
SearchAgent — 联网搜索 Agent

负责在互联网上搜索最新信息，回答需要外部知识的问题。
当用户询问"最新"、"新闻"、"搜索"、"联网"等问题时被调度。
"""

import logging
import time
from typing import Any, Dict

from .base import AgentResult, BaseAgent, Intent, ToolCall

logger = logging.getLogger(__name__)


class SearchAgent(BaseAgent):
    name = "search"
    description = "联网搜索与信息检索"

    def system_prompt(self) -> str:
        return """你是工业环境监控系统的「联网搜索助手」。

职责：
1. 搜索互联网获取最新信息
2. 综合搜索结果回答用户问题
3. 标注信息来源

输出规则：
- 综合多个搜索结果，给出准确、简洁的回答
- 在回答末尾列出参考来源链接
- 如果搜索结果不相关，如实告知
- 用中文回复"""

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        start = time.time()
        tool_calls = []

        # 1. 执行联网搜索
        search_result = self.call_tool("search_web", query=message, max_results=5)
        tool_calls.append(ToolCall(
            tool_name="search_web",
            params={"query": message, "max_results": 5},
            result=search_result,
        ))

        search_context = search_result.get("context", "")
        if not search_result.get("found"):
            return AgentResult(
                agent_name=self.name,
                content="联网搜索未能找到相关信息，可能是网络问题或搜索关键词不够精确。请尝试更具体的描述。",
                data={"found": False},
                tool_calls=tool_calls,
                latency_ms=(time.time() - start) * 1000,
            )

        # 2. 用 LLM 综合搜索结果
        messages = self.build_messages(
            message,
            f"以下是互联网搜索结果：\n{search_context}",
        )
        try:
            resp = self.llm.chat(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"SearchAgent LLM 调用失败: {e}")
            content = f"搜索结果：\n{search_context[:800]}"

        latency = (time.time() - start) * 1000
        return AgentResult(
            agent_name=self.name,
            content=content,
            data={"found": True},
            tool_calls=tool_calls,
            latency_ms=latency,
        )
