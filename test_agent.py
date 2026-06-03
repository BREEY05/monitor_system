"""
多 Agent 协作框架 — 端到端测试脚本

运行方式：
    cd monitor_system
    python test_agent.py

测试内容：
    1. 模块导入与初始化
    2. 工具注册与分配
    3. 意图分类（快速模式 + LLM 模式）
    4. 执行计划生成
    5. Agent 调度与结果融合
    6. HTTP API 接口测试
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")


async def main():
    print("=" * 60)
    print("  Multi-Agent Framework - End-to-End Test")
    print("=" * 60)

    # 1. 导入测试
    print("\n[1] Module Import")
    try:
        from agents import (
            LLMProvider, LLMMessage, BaseAgent,
            IntentType, Intent, Plan, ToolCall, AgentResult,
            OrchestratorAgent, SensorAgent, KnowledgeAgent,
            SearchAgent, AlarmAgent, DeviceAgent,
            create_orchestrator, register_all_tools,
            TOOL_REGISTRY, TOOL_SCHEMAS,
        )
        check("all modules imported", True)
    except Exception as e:
        check("all modules imported", False, str(e))
        return

    # 2. 工具注册
    print("\n[2] Tool Registration")
    register_all_tools()
    check("tools registered", len(TOOL_REGISTRY) == 10, f"got {len(TOOL_REGISTRY)}")
    check("tool schemas defined", len(TOOL_SCHEMAS) == 10, f"got {len(TOOL_SCHEMAS)}")

    from agents.tools import get_tools_for_agent
    for agent_name, expected_count in [
        ("sensor", 3), ("knowledge", 1), ("search", 1),
        ("alarm", 4), ("device", 3),
    ]:
        tools = get_tools_for_agent(agent_name)
        check(
            f"{agent_name} has {expected_count} tools",
            len(tools) == expected_count,
            f"got {len(tools)}: {list(tools.keys())}",
        )

    # 3. Orchestrator 初始化
    print("\n[3] Orchestrator Initialization")
    orch = create_orchestrator(backend="ollama", model="qwen3.5:0.8b")
    check("orchestrator created", orch is not None)
    check("5 agents registered", len(orch.agents) == 5, f"got {len(orch.agents)}")
    for name in ["sensor", "knowledge", "search", "alarm", "device"]:
        check(f"agent '{name}' exists", name in orch.agents)

    # 4. 意图分类（快速模式）
    print("\n[4] Intent Classification (Fast Mode)")
    test_cases = [
        ("当前温度多少", IntentType.SENSOR_QUERY),
        ("有什么报警", IntentType.ALARM_QUERY),
        ("查知识库安全文档", IntentType.KNOWLEDGE),
        ("搜索最新技术", IntentType.SEARCH),
        ("设备列表", IntentType.DEVICE_MANAGE),
        ("你好", IntentType.CHITCHAT),
        ("历史温度趋势", IntentType.HISTORY_QUERY),
    ]
    for msg, expected in test_cases:
        intents = orch.classifier.classify_fast(msg)
        top = intents[0] if intents else None
        check(
            f'"{msg}" -> {expected.value}',
            top is not None and top.type == expected,
            f"got {top.type.value if top else 'None'}",
        )

    # 5. 计划生成
    print("\n[5] Plan Generation")
    from agents.orchestrator import PlanGenerator
    planner = PlanGenerator()

    intents_single = [Intent(type=IntentType.SENSOR_QUERY, confidence=0.9)]
    plan = planner.generate(intents_single, "温度多少")
    check("single intent plan", plan.agent_sequence == ["sensor"])
    check("single not parallel", not plan.parallel)

    intents_multi = [
        Intent(type=IntentType.ALARM_QUERY, confidence=0.9),
        Intent(type=IntentType.HISTORY_QUERY, confidence=0.7),
    ]
    plan = planner.generate(intents_multi, "查报警并分析趋势")
    check("multi intent plan", len(plan.agent_sequence) == 2)
    check("multi parallel", plan.parallel)

    # 6. 闲聊处理
    print("\n[6] Chitchat Handling")
    result = await orch._handle_chitchat("你好")
    check("chitchat reply", len(result.content) > 10, f"len={len(result.content)}")
    check("chitchat agent name", result.agent_name == "chitchat")

    # 7. LLM 连通性测试（可选）
    print("\n[7] LLM Connection (optional)")
    llm_test = orch.llm.test_connection()
    if llm_test.get("success"):
        check("LLM connected", True)

        # 尝试 LLM 意图分类
        intents = await orch.classifier.classify("帮我看看当前车间温度是否正常")
        check("LLM classification", len(intents) > 0)
        if intents:
            print(f"    -> {intents[0].type.value} ({intents[0].confidence:.2f})")

        # 尝试完整对话流程
        print("\n[8] Full Conversation Flow")
        try:
            result = await orch.handle_message("你好")
            check("handle_message reply", bool(result.get("reply")))
            check("handle_message intents", len(result.get("intents", [])) > 0)
            check("handle_message plan", bool(result.get("plan")))
            print(f"    Reply: {result['reply'][:80]}...")
        except Exception as e:
            check("handle_message", False, str(e))
    else:
        print("    LLM not available, skipping LLM-dependent tests")
        print(f"    (status: {llm_test})")

    # 8. API 集成测试
    print("\n[9] API Integration")
    try:
        from api_server import app, get_orchestrator
        routes = [r.path for r in app.routes]
        for route in ["/api/agent/status", "/api/agent/chat", "/api/agent/test"]:
            check(f"route {route}", route in routes)
        check("get_orchestrator callable", callable(get_orchestrator))
    except Exception as e:
        check("API integration", False, str(e))

    # 汇总
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)
    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
