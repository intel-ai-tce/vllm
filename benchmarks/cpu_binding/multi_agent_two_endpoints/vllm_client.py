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
    headers: Optional[Dict[str, str]] = None,
) -> AsyncGenerator[str, None]:
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as client:
        async with client.stream("POST", url, json=payload) as resp:
            body = await resp.aread()
            print("DEBUG url =", url)
            print("DEBUG status =", resp.status_code)
            print("DEBUG request headers auth present =", "Authorization" in (headers or {}))
            print("DEBUG request headers content-type =", (headers or {}).get("Content-Type"))
            print("DEBUG payload =", payload)
            print("DEBUG response body =", body[:1000])
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
