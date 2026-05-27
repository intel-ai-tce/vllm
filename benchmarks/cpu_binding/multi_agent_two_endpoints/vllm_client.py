import json
from typing import AsyncGenerator, Dict, Any, List, Optional

import httpx


async def vllm_stream_chat(
    base_url: str,
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 512,
    temperature: float = 0.2,
    timeout_s: int = 180,
    connect_timeout_s: int = 10,
    headers: Optional[Dict[str, str]] = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completions from a vLLM endpoint.

    Uses a short connect timeout so callers fail fast when a backend is
    unreachable, while still allowing a long read timeout for slow
    generation (e.g. first inference on Blackwell).
    """
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    timeout = httpx.Timeout(timeout_s, connect=connect_timeout_s)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: "):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content")
                except Exception:
                    delta = None
                if delta:
                    yield delta
