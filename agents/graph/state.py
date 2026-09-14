"""Structured state exchanged by LangGraph nodes."""

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    user_query: str
    context: Dict[str, Any]
    intents: List[Any]
    plan: Any
    results: List[Any]
    retry_count: int
    evaluation: Dict[str, Any]
    final_response: str
