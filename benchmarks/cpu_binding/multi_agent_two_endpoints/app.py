import asyncio
import json
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents import run_researcher, run_writer, run_reviewer, PipelineConfig

app = FastAPI()

# Serve static files (logos)
app.mount("/static", StaticFiles(directory="static"), name="static")


def sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


INDEX_HTML = '''
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Pipelined Multi-Agent (2 Endpoints)</title>
    <style>
      body {
        font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        margin: 20px;
        background: radial-gradient(circle at 20% 0%, #eef3ff, #ffffff 60%);
      }
      h2 { margin-bottom: 10px; }
      .controls { display:flex; gap:12px; align-items:center; margin-bottom:18px; }
      input[type="text"] {
        flex:1; padding:10px; border-radius:12px;
        border:1px solid #dcdcdc; font-size:14px;
      }
      button {
        padding:10px 14px; border-radius:12px; border:none;
        font-weight:600; cursor:pointer;
      }
      #run { background: linear-gradient(180deg,#3b82f6,#2563eb); color:white; }
      #stop { background: linear-gradient(180deg,#ef4444,#dc2626); color:white; }
      .pill {
        padding:4px 10px; border-radius:999px; background:#f3f4f6; font-size:12px;
      }
      .row { display:flex; gap:16px; }
      .panel {
        flex:1; border-radius:18px; padding:14px;
        box-shadow:0 8px 24px rgba(0,0,0,.06);
        display:flex; flex-direction:column;
      }
      .researcher { background: linear-gradient(180deg,#fff4d6,#ffffff); border:1px solid #facc15; }
      .writer     { background: linear-gradient(180deg,#e0f2fe,#ffffff); border:1px solid #38bdf8; }
      .reviewer   { background: linear-gradient(180deg,#dcfce7,#ffffff); border:1px solid #22c55e; }
      textarea {
        flex:1; border-radius:12px; border:1px solid rgba(0,0,0,.1);
        padding:10px; resize:none; background:rgba(255,255,255,.7); min-height:260px;
      }
      #log {
        margin-top:18px; border-radius:16px; padding:12px;
        background: linear-gradient(180deg,#f5f3ff,#ffffff);
        border:1px solid #ddd; height:220px; overflow:auto;
        font-family: ui-monospace, monospace;
      }
      .logline {
        padding:6px 8px; margin-bottom:6px; border-radius:10px;
        background:rgba(255,255,255,.8); border-left:6px solid #aaa;
      }
      .logline.researcher { border-left-color:#facc15; }
      .logline.writer { border-left-color:#3b82f6; }
      .logline.reviewer { border-left-color:#22c55e; }
      .logline.status { border-left-color:#a855f7; }

      /* Logo styles */
      .logo-container {
        position: fixed;
        bottom: 16px;
        right: 20px;
        display: flex;
        gap: 14px;
        align-items: center;
        opacity: 0.9;
      }
      .logo-container img {
        height: 30px;
      }
    </style>
  </head>
  <body>
    <h2>Pipelined Multi-Agent (Researcher → Writer → Reviewer)</h2>

    <div class="controls">
      <input id="task" type="text"
        value="Explain how pipelining helps multi-agent latency while preserving dependencies."/>
      <button id="run">Run</button>
      <button id="stop">Stop</button>
      <span id="mode" class="pill">mode: ...</span>
      <span id="routing" class="pill">routing: researcher/reviewer→CPU, writer→GPU</span>
    </div>

    <div class="row">
      <div class="panel researcher">
        <h3>Researcher (CPU 8B)</h3>
        <textarea id="research" readonly></textarea>
      </div>
      <div class="panel writer">
        <h3>Writer (GPU 405B)</h3>
        <textarea id="writer" readonly></textarea>
      </div>
      <div class="panel reviewer">
        <h3>Reviewer (CPU 8B)</h3>
        <textarea id="review" readonly></textarea>
      </div>
    </div>

    <div id="log"></div>

    <!-- Logos -->
    <div class="logo-container">
      <img src="/static/intel_logo.png">
      <img src="/static/supermicro_logo.png">
    </div>

    <script>
      let es = null;

      function appendText(id, text) {
        const el = document.getElementById(id);
        el.value += text;
        el.scrollTop = el.scrollHeight;
      }

      function logLine(obj) {
        const log = document.getElementById("log");
        const div = document.createElement("div");
        div.className = "logline";
        if (obj.stage) div.classList.add(obj.stage);
        if (obj.event === "status") div.classList.add("status");
        div.textContent = JSON.stringify(obj);
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
      }

      async function fetchMode() {
        const r = await fetch("/mode");
        const j = await r.json();
        document.getElementById("mode").textContent = "mode: " + j.mode;
      }

      function resetPanels() {
        document.getElementById("research").value = "";
        document.getElementById("writer").value = "";
        document.getElementById("review").value = "";
        document.getElementById("log").innerHTML = "";
      }

      document.getElementById("run").onclick = async () => {
        resetPanels();
        await fetchMode();

        if (es) es.close();
        const task = encodeURIComponent(document.getElementById("task").value);
        es = new EventSource("/stream?task=" + task);

        es.addEventListener("status", e => {
          logLine({event:"status", ...JSON.parse(e.data)});
        });

        es.addEventListener("update", e => {
          const data = JSON.parse(e.data);
          logLine(data);
          if (data.stage === "researcher" && data.type === "text") appendText("research", data.delta);
          if (data.stage === "writer" && data.type === "text") appendText("writer", data.delta);
          if (data.stage === "reviewer" && data.type === "text") appendText("review", data.delta);
        });
      };

      document.getElementById("stop").onclick = () => {
        if (es) es.close();
        es = null;
        logLine({event:"status", state:"stopped"});
      };

      fetchMode();
    </script>
  </body>
</html>
'''


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


@app.get("/mode")
def mode():
    cfg = PipelineConfig.from_env()
    return {
        "mode": "dry-run" if cfg.dry_run else "vllm",
        "cpu_url": cfg.cpu_url,
        "gpu_url": cfg.gpu_url,
    }


@app.get("/stream")
async def stream(task: str):
    cfg = PipelineConfig.from_env()

    async def gen() -> AsyncGenerator[str, None]:
        research_q: asyncio.Queue = asyncio.Queue()
        writer_q: asyncio.Queue = asyncio.Queue()
        ui_q: asyncio.Queue = asyncio.Queue()

        async def bridge_research():
            async for delta in run_researcher(task, cfg):
                await research_q.put(delta)
                await ui_q.put({"stage": "researcher", "type": "text", "delta": delta})
            await research_q.put(None)
            await ui_q.put({"stage": "researcher", "type": "done"})

        async def bridge_writer():
            async for delta in run_writer(task, research_q, cfg):
                await writer_q.put(delta)
                await ui_q.put({"stage": "writer", "type": "text", "delta": delta})
            await writer_q.put(None)
            await ui_q.put({"stage": "writer", "type": "done"})

        async def bridge_reviewer():
            async for delta in run_reviewer(task, writer_q, cfg):
                await ui_q.put({"stage": "reviewer", "type": "text", "delta": delta})
            await ui_q.put({"stage": "reviewer", "type": "done"})

        tasks = [
            asyncio.create_task(bridge_research()),
            asyncio.create_task(bridge_writer()),
            asyncio.create_task(bridge_reviewer()),
        ]

        yield sse("status", {
            "state": "started",
            "mode": "dry-run" if cfg.dry_run else "vllm",
            "routing": "researcher/reviewer->CPU, writer->GPU",
        })

        done = {"researcher": False, "writer": False, "reviewer": False}
        while True:
            msg = await ui_q.get()
            if msg.get("type") == "done":
                done[msg["stage"]] = True
            yield sse("update", msg)
            if all(done.values()):
                break

        await asyncio.gather(*tasks, return_exceptions=True)
        yield sse("status", {"state": "finished"})

    return StreamingResponse(gen(), media_type="text/event-stream")
