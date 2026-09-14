"""LangGraph implementation of the Agent orchestration path."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph

from ..base import AgentResult, Intent, IntentType
from ..orchestrator import IntentClassifier, PlanGenerator, ResultFuser
from ..tools import get_tools_for_agent, register_all_tools
from .state import AgentState


class LangGraphOrchestrator:
    """Compatibility entry point whose execution flow is managed by LangGraph."""

    def __init__(self, llm: Any):
        self.llm = llm
        self.classifier = IntentClassifier(llm)
        self.planner = PlanGenerator()
        self.fuser = ResultFuser(llm)
        register_all_tools()
        from ..sensor_agent import SensorAgent
        from ..knowledge_agent import KnowledgeAgent
        from ..search_agent import SearchAgent
        from ..alarm_agent import AlarmAgent
        from ..device_agent import DeviceAgent
        self.agents = {
            "sensor": SensorAgent(llm, get_tools_for_agent("sensor")),
            "knowledge": KnowledgeAgent(llm, get_tools_for_agent("knowledge")),
            "search": SearchAgent(llm, get_tools_for_agent("search")),
            "alarm": AlarmAgent(llm, get_tools_for_agent("alarm")),
            "device": DeviceAgent(llm, get_tools_for_agent("device")),
        }
        self.stats = {"total_requests": 0, "agent_calls": {}}
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("preprocess", self._preprocess)
        workflow.add_node("intent_classifier", self._classify)
        workflow.add_node("planner", self._plan)
        workflow.add_node("agents", self._run_agents)
        workflow.add_node("evaluator", self._evaluate)
        workflow.add_node("final", self._finalize)
        workflow.add_edge(START, "preprocess")
        workflow.add_edge("preprocess", "intent_classifier")
        workflow.add_edge("intent_classifier", "planner")
        workflow.add_edge("planner", "agents")
        workflow.add_edge("agents", "evaluator")
        workflow.add_edge("evaluator", "final")
        workflow.add_edge("final", END)
        return workflow.compile()

    async def _preprocess(self, state: AgentState) -> Dict[str, Any]:
        return {"user_query": state["user_query"].strip(), "context": state.get("context", {}), "retry_count": 0}

    async def _classify(self, state: AgentState) -> Dict[str, Any]:
        return {"intents": await self.classifier.classify(state["user_query"])}

    async def _plan(self, state: AgentState) -> Dict[str, Any]:
        return {"plan": self.planner.generate(state["intents"], state["user_query"])}

    async def _run_agents(self, state: AgentState) -> Dict[str, Any]:
        results: List[AgentResult] = []
        plan = state["plan"]
        for agent_name in plan.agent_sequence:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            intent = next((item for item in plan.intents if PlanGenerator.INTENT_AGENT_MAP.get(item.type) == agent_name), Intent(IntentType.CHITCHAT))
            try:
                result = await agent.execute(state["user_query"], intent, state.get("context", {}))
            except Exception as exc:
                result = AgentResult(agent_name=agent_name, content=f"{agent_name} 模块暂时不可用。", success=False, error=str(exc))
            results.append(result)
            self.stats["agent_calls"][agent_name] = self.stats["agent_calls"].get(agent_name, 0) + 1
        return {"results": results}

    async def _evaluate(self, state: AgentState) -> Dict[str, Any]:
        results = state.get("results", [])
        return {"evaluation": {"passed": bool(results), "tool_failures": sum(not result.success for result in results)}}

    async def _finalize(self, state: AgentState) -> Dict[str, Any]:
        results = state.get("results", [])
        if not results:
            return {"final_response": "未找到可执行的监控分析模块。"}
        return {"final_response": await self.fuser.fuse(state["user_query"], results, state["plan"])}

    async def handle_message(self, message: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        start = time.time()
        self.stats["total_requests"] += 1
        state = await self.graph.ainvoke({"user_query": message, "context": context or {}})
        plan = state["plan"]
        return {
            "reply": state["final_response"],
            "intents": [{"type": item.type.value, "confidence": item.confidence, "reasoning": item.reasoning} for item in state["intents"]],
            "plan": {"agent_sequence": plan.agent_sequence, "parallel": plan.parallel, "reasoning": plan.reasoning},
            "agent_results": [{"agent": item.agent_name, "success": item.success, "latency_ms": round(item.latency_ms, 1), "tool_count": len(item.tool_calls)} for item in state.get("results", [])],
            "tool_calls": [call.tool_name for item in state.get("results", []) for call in item.tool_calls],
            "evaluation": state["evaluation"], "latency_ms": round((time.time() - start) * 1000, 1),
        }

    def get_stats(self) -> Dict[str, Any]:
        return {**self.stats, "registered_agents": list(self.agents), "workflow": "langgraph"}
