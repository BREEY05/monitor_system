"""
LLM Provider — 统一的大语言模型调用接口

支持 Ollama 本地模型和 OpenAI 兼容的云端 API（通义千问、DeepSeek 等）。
提供同步调用和流式调用两种模式，供不同 Agent 按需使用。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    role: str          # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


class LLMProvider:
    """统一的 LLM 调用接口，屏蔽 Ollama 与 OpenAI 兼容 API 的差异。"""

    def __init__(
        self,
        backend: str = "ollama",
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:0.8b",
        api_key: str = "",
        temperature: float = 0.2,
        top_p: float = 0.8,
        timeout: int = 120,
    ):
        self.backend = backend          # "ollama" | "openai"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout

    # ------------------------------------------------------------------
    # 同步调用
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """非流式调用，返回完整回复文本。"""
        if self.backend == "ollama":
            return self._ollama_chat(messages, model, temperature)
        return self._openai_chat(messages, model, temperature)

    def chat_json(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """调用 LLM 并解析 JSON 输出。"""
        resp = self.chat(messages, model=model, temperature=0.0)
        text = resp.content.strip()
        # 提取 JSON 块
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"LLM JSON 输出解析失败: {text[:200]}")
            return {}

    # ------------------------------------------------------------------
    # 流式调用
    # ------------------------------------------------------------------
    def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Generator[str, None, None]:
        """流式调用，逐块 yield 文本增量。"""
        if self.backend == "ollama":
            yield from self._ollama_stream(messages, model, temperature)
        else:
            yield from self._openai_stream(messages, model, temperature)

    # ==================================================================
    # Ollama 后端
    # ==================================================================
    def _ollama_chat(
        self, messages: List[LLMMessage], model: Optional[str], temperature: Optional[float]
    ) -> LLMResponse:
        import requests

        payload = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": self.top_p,
            },
        }
        r = requests.post(
            f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
        )
        r.raise_for_status()
        data = r.json()
        content = data.get("message", {}).get("content", "")
        return LLMResponse(content=content, model=payload["model"])

    def _ollama_stream(
        self, messages: List[LLMMessage], model: Optional[str], temperature: Optional[float]
    ) -> Generator[str, None, None]:
        import requests

        payload = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": self.top_p,
            },
        }
        r = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
            if chunk.get("done"):
                break

    # ==================================================================
    # OpenAI 兼容 API 后端
    # ==================================================================
    def _build_openai_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _openai_chat(
        self, messages: List[LLMMessage], model: Optional[str], temperature: Optional[float]
    ) -> LLMResponse:
        import requests

        payload = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
        }
        r = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._build_openai_headers(),
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return LLMResponse(content=content, model=payload["model"], usage=usage)

    def _openai_stream(
        self, messages: List[LLMMessage], model: Optional[str], temperature: Optional[float]
    ) -> Generator[str, None, None]:
        import requests

        payload = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
        }
        r = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._build_openai_headers(),
            stream=True,
            timeout=self.timeout,
        )
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                decoded = decoded[6:]
            if decoded.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(decoded)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield content

    # ==================================================================
    # 辅助方法
    # ==================================================================
    def get_available_models(self) -> List[str]:
        """获取当前后端可用的模型列表。"""
        import requests

        try:
            if self.backend == "ollama":
                r = requests.get(f"{self.base_url}/api/tags", timeout=5)
                r.raise_for_status()
                return [m["name"] for m in r.json().get("models", [])]
            else:
                r = requests.get(
                    f"{self.base_url}/models",
                    headers=self._build_openai_headers(),
                    timeout=5,
                )
                r.raise_for_status()
                return [m["id"] for m in r.json().get("data", [])]
        except Exception as e:
            logger.warning(f"获取模型列表失败: {e}")
            return []

    def test_connection(self) -> Dict[str, Any]:
        """测试 LLM 后端连通性。"""
        import requests

        try:
            if self.backend == "ollama":
                r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            else:
                r = requests.get(
                    f"{self.base_url}/models",
                    headers=self._build_openai_headers(),
                    timeout=5,
                )
            ok = r.status_code == 200
            return {"success": ok, "backend": self.backend, "status_code": r.status_code}
        except Exception as e:
            return {"success": False, "backend": self.backend, "error": str(e)}
