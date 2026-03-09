import os
import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from vllm_client import vllm_stream_chat


@dataclass(frozen=True)
class PipelineConfig:
    dry_run: bool

    cpu_url: str
    cpu_model: str

    gpu_url: str
    gpu_model: str

    researcher_max_tokens: int
    researcher_temp: float
    researcher_initial_wait_s: float

    writer_max_tokens: int
    writer_temp: float
    writer_timeout_s: int

    reviewer_max_tokens: int
    reviewer_temp: float
    review_start_chars: int

    api_key: str
    chunk_chars: int

    @staticmethod
    def from_env() -> "PipelineConfig":
        def env_int(k: str, default: int) -> int:
            v = os.getenv(k, "")
            try:
                return int(v) if v else default
            except Exception:
                return default

        def env_float(k: str, default: float) -> float:
            v = os.getenv(k, "")
            try:
                return float(v) if v else default
            except Exception:
                return default

        dry_run = os.getenv("DRY_RUN", "1").strip() not in ("0", "false", "False", "no", "NO")

        return PipelineConfig(
            dry_run=dry_run,
            cpu_url=os.getenv("CPU_URL", "http://localhost:8001"),
            cpu_model=os.getenv("CPU_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
            gpu_url=os.getenv("GPU_URL", "http://localhost:8002"),
            gpu_model=os.getenv("GPU_MODEL", "meta-llama/Llama-3.1-405B-Instruct"),
            researcher_max_tokens=env_int("RESEARCHER_MAX_TOKENS", 700),
            researcher_temp=env_float("RESEARCHER_TEMP", 0.2),
            researcher_initial_wait_s=env_float("RESEARCHER_INITIAL_WAIT_S", 0.8),
            writer_max_tokens=env_int("WRITER_MAX_TOKENS", 2500),
            writer_temp=env_float("WRITER_TEMP", 0.4),
            writer_timeout_s=env_int("WRITER_TIMEOUT_S", 300),
            reviewer_max_tokens=env_int("REVIEWER_MAX_TOKENS", 400),
            reviewer_temp=env_float("REVIEWER_TEMP", 0.2),
            review_start_chars=env_int("REVIEW_START_CHARS", 1400),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            chunk_chars=env_int("CHUNK_CHARS", 220),
        )


def _headers(cfg: PipelineConfig) -> dict:
    if cfg.api_key:
        return {"Authorization": f"Bearer {cfg.api_key}"}
    return {}


async def _dry_stream(lines: list[str], *, delay_s: float, chunk_chars: int) -> AsyncGenerator[str, None]:
    buf = ""
    for line in lines:
        await asyncio.sleep(delay_s)
        buf += line
        while len(buf) >= chunk_chars:
            yield buf[:chunk_chars]
            buf = buf[chunk_chars:]
    if buf:
        yield buf


async def run_researcher(task: str, cfg: PipelineConfig) -> AsyncGenerator[str, None]:
    if cfg.dry_run:
        lines = [
            "• Researcher is routed to CPU 8B.\n",
            "• Extract concise facts and constraints only.\n",
            "• Keep notes compact so the GPU writer gets a clean handoff.\n",
        ]
        async for c in _dry_stream(lines, delay_s=0.25, chunk_chars=cfg.chunk_chars):
            yield c
        return

    messages = [
        {
            "role": "system",
            "content": (
                "You are a researcher. Return concise factual bullet notes only. "
                "Do not write a full draft. Keep output compact and structured."
            ),
        },
        {"role": "user", "content": task},
    ]

    buf = ""
    async for delta in vllm_stream_chat(
        cfg.cpu_url,
        cfg.cpu_model,
        messages,
        max_tokens=cfg.researcher_max_tokens,
        temperature=cfg.researcher_temp,
        timeout_s=180,
        headers=_headers(cfg),
    ):
        buf += delta
        if len(buf) >= cfg.chunk_chars:
            yield buf
            buf = ""
    if buf:
        yield buf


async def run_writer(task: str, research_in_q: asyncio.Queue, cfg: PipelineConfig) -> AsyncGenerator[str, None]:
    if cfg.dry_run:
        async for c in _dry_stream(
            [
                f"Draft for task: {task}\n\n",
                "1) Researcher notes arrive from CPU 8B.\n",
                "2) Writer on GPU 405B creates the main draft.\n",
                "3) Optional refine pass uses all researcher notes.\n",
            ],
            delay_s=0.25,
            chunk_chars=cfg.chunk_chars,
        ):
            yield c
        while True:
            msg = await research_in_q.get()
            if msg is None:
                break
        return

    research_notes = ""
    research_done = False

    async def consume_research(timeout_s: Optional[float]) -> None:
        nonlocal research_notes, research_done
        while not research_done:
            try:
                msg = await asyncio.wait_for(research_in_q.get(), timeout=timeout_s) if timeout_s else await research_in_q.get()
            except asyncio.TimeoutError:
                break
            if msg is None:
                research_done = True
                break
            research_notes += msg

    await consume_research(timeout_s=cfg.researcher_initial_wait_s)

    async def writer_pass(notes: str) -> AsyncGenerator[str, None]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a writer. Produce a clear, structured draft. "
                    "Use the notes. Do not invent citations."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task:\n{task}\n\n"
                    f"Research notes so far:\n{notes}\n\n"
                    "Write the draft now."
                ),
            },
        ]
        buf = ""
        async for delta in vllm_stream_chat(
            cfg.gpu_url,
            cfg.gpu_model,
            messages,
            max_tokens=cfg.writer_max_tokens,
            temperature=cfg.writer_temp,
            timeout_s=cfg.writer_timeout_s,
            headers=_headers(cfg),
        ):
            buf += delta
            if len(buf) >= cfg.chunk_chars:
                yield buf
                buf = ""
        if buf:
            yield buf

    async for d in writer_pass(research_notes):
        yield d

    await consume_research(timeout_s=None)

    if research_notes.strip():
        yield "\n\n[Refining with full research]\n\n"
        async for d in writer_pass(research_notes):
            yield d


async def run_reviewer(task: str, writer_in_q: asyncio.Queue, cfg: PipelineConfig) -> AsyncGenerator[str, None]:
    if cfg.dry_run:
        async for c in _dry_stream(
            [
                "• Reviewer is routed to CPU 8B.\n",
                "• Return edits-only feedback.\n",
                "• Keep review short to avoid CPU contention.\n",
            ],
            delay_s=0.30,
            chunk_chars=cfg.chunk_chars,
        ):
            yield c
        while True:
            msg = await writer_in_q.get()
            if msg is None:
                break
        return

    draft = ""
    while True:
        msg = await writer_in_q.get()
        if msg is None:
            break
        draft += msg
        if len(draft) >= cfg.review_start_chars:
            break

    messages = [
        {
            "role": "system",
            "content": (
                "You are a reviewer. Return edits-only feedback. "
                "Do not rewrite the full document. "
                "Focus on clarity, missing points, correctness, and concise fixes."
            ),
        },
        {
            "role": "user",
            "content": f"Task:\n{task}\n\nReview this draft:\n\n{draft}\n\nReturn edits-only.",
        },
    ]

    buf = ""
    async for delta in vllm_stream_chat(
        cfg.cpu_url,
        cfg.cpu_model,
        messages,
        max_tokens=cfg.reviewer_max_tokens,
        temperature=cfg.reviewer_temp,
        timeout_s=180,
        headers=_headers(cfg),
    ):
        buf += delta
        if len(buf) >= cfg.chunk_chars:
            yield buf
            buf = ""
    if buf:
        yield buf
