"""
KnowledgeAgent — RAG 知识库检索 Agent

负责在用户上传的文档知识库中进行语义检索，回答文档、资料、规范类问题。
当用户询问"知识库"、"文档"、"手册"等问题时被调度。
"""

import json
import logging
import time
from typing import Any, Dict

from .base import AgentResult, BaseAgent, Intent, ToolCall
from .llm_provider import LLMMessage

logger = logging.getLogger(__name__)


class KnowledgeAgent(BaseAgent):
    name = "knowledge"
    description = "RAG 知识库检索与问答"

    def system_prompt(self) -> str:
        return """你是工业环境监控系统的「知识库问答专家」。

职责：
1. 基于检索到的知识库片段回答用户问题
2. 准确引用来源文档
3. 知识库信息不足时明确告知用户

输出规则：
- 优先依据知识库片段回答，不要编造知识库中没有的内容
- 如果检索结果不相关或为空，明确说明"知识库中未找到足够信息"
- 引用格式：在回答末尾标注来源文档名
- 用中文回复，简洁专业"""

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        start = time.time()
        tool_calls = []

        # 1. 调用知识库检索
        kb_result = self.call_tool("search_knowledge_base", query=message, top_k=4)
        tool_calls.append(ToolCall(
            tool_name="search_knowledge_base",
            params={"query": message, "top_k": 4},
            result=kb_result,
        ))

        kb_context = kb_result.get("context", "")
        if not kb_result.get("found"):
            return AgentResult(
                agent_name=self.name,
                content="知识库中未找到与您问题相关的信息。您可以尝试上传相关文档到知识库，或换一种问法。",
                data={"found": False},
                tool_calls=tool_calls,
                latency_ms=(time.time() - start) * 1000,
            )

        # 2. 用 LLM 基于知识库内容回答
        messages = self.build_messages(
            message,
            f"以下是从知识库中检索到的相关片段：\n{kb_context}",
        )
        try:
            resp = self.llm.chat(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"KnowledgeAgent LLM 调用失败: {e}")
            content = f"知识库检索到相关内容，但 AI 分析暂时不可用。\n\n检索结果摘要：\n{kb_context[:500]}"

        latency = (time.time() - start) * 1000
        return AgentResult(
            agent_name=self.name,
            content=content,
            data={"found": True, "context_length": len(kb_context)},
            tool_calls=tool_calls,
            latency_ms=latency,
        )
