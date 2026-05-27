import asyncio
import json
import uuid
from typing import AsyncGenerator, Dict, Any, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents import run_researcher, run_writer, run_reviewer, PipelineConfig

app = FastAPI()

# Serve static files (logos)
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory store for active pipeline runs
_runs: Dict[str, Dict[str, Any]] = {}


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
    <h2>Pipelined Multi-Agent (Researcher &rarr; Writer &rarr; Reviewer)</h2>

    <div class="controls">
      <input id="task" type="text"
        value="Explain how pipelining helps multi-agent latency while preserving dependencies."/>
      <button id="run">Run</button>
      <button id="stop">Stop</button>
      <span id="mode" class="pill">mode: ...</span>
      <span id="routing" class="pill">routing: researcher/reviewer&rarr;CPU, writer&rarr;GPU</span>
    </div>

    <div class="row">
      <div class="panel researcher">
        <h3>Researcher (CPU {{CPU_MODEL}})</h3>
        <textarea id="research" readonly></textarea>
      </div>
      <div class="panel writer">
        <h3>Writer (GPU {{GPU_MODEL}})</h3>
        <textarea id="writer" readonly></textarea>
      </div>
      <div class="panel reviewer">
        <h3>Reviewer (CPU {{CPU_MODEL}})</h3>
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
      let runId = null;
      let pollTimer = null;
      let cursor = 0;

      const panelMap = {researcher: "research", writer: "writer", reviewer: "review"};

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

      function showError(stage, msg) {
        const id = panelMap[stage];
        if (!id) return;
        const el = document.getElementById(id);
        el.value += "\\n[ERROR] " + msg;
        el.style.borderColor = "#ef4444";
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

      function processEvent(evt) {
        if (evt.event === "status") {
          logLine({event: "status", ...evt.data});
        } else if (evt.event === "update") {
          const data = evt.data;
          logLine(data);
          if (data.type === "error") showError(data.stage, data.error);
          if (data.type === "text") {
            const id = panelMap[data.stage];
            if (id) appendText(id, data.delta);
          }
        }
      }

      async function poll() {
        if (!runId) return;
        try {
          const r = await fetch("/poll?run_id=" + runId + "&cursor=" + cursor);
          const j = await r.json();
          if (j.events) {
            for (const evt of j.events) processEvent(evt);
            cursor += j.events.length;
          }
          if (j.done) {
            stopPolling();
            return;
          }
        } catch(e) {
          logLine({event: "status", state: "poll error", error: e.message});
        }
      }

      function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      }

      document.getElementById("run").onclick = async () => {
        resetPanels();
        stopPolling();
        Object.values(panelMap).forEach(id => {
          document.getElementById(id).style.borderColor = "";
        });
        try { await fetchMode(); } catch(e) {
          logLine({event: "status", state: "error", error: "Failed to reach server"});
          return;
        }
        const task = document.getElementById("task").value;
        try {
          const r = await fetch("/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({task: task})
          });
          const j = await r.json();
          runId = j.run_id;
          cursor = 0;
          logLine({event: "status", state: "started", run_id: runId});
          pollTimer = setInterval(poll, 400);
        } catch(e) {
          logLine({event: "status", state: "error", error: e.message});
        }
      };

      document.getElementById("stop").onclick = () => {
        stopPolling();
        runId = null;
        logLine({event: "status", state: "stopped"});
      };

      fetchMode();
    </script>
  </body>
</html>
'''


@app.get("/", response_class=HTMLResponse)
def index():
    cfg = PipelineConfig.from_env()
    html = INDEX_HTML
    html = html.replace("{{CPU_MODEL}}", cfg.cpu_model.split("/")[-1])
    html = html.replace("{{GPU_MODEL}}", cfg.gpu_model.split("/")[-1])
    return html


@app.get("/mode")
def mode():
    cfg = PipelineConfig.from_env()
    return {
        "mode": "dry-run" if cfg.dry_run else "vllm",
        "cpu_url": cfg.cpu_url,
        "gpu_url": cfg.gpu_url,
    }


@app.post("/start")
async def start_run(body: Dict[str, Any]):
    """Kick off pipeline in background, return run_id for polling."""
    task = body.get("task", "")
    cfg = PipelineConfig.from_env()
    run_id = uuid.uuid4().hex[:12]

    run_state = {
        "events": [],
        "done": False,
    }
    _runs[run_id] = run_state

    async def run_pipeline():
        research_q: asyncio.Queue = asyncio.Queue()
        writer_q: asyncio.Queue = asyncio.Queue()
        ui_q: asyncio.Queue = asyncio.Queue()

        async def bridge_research():
            try:
                async for delta in run_researcher(task, cfg):
                    await research_q.put(delta)
                    await ui_q.put({"stage": "researcher", "type": "text", "delta": delta})
            except Exception as exc:
                await ui_q.put({"stage": "researcher", "type": "error", "error": str(exc)})
            finally:
                await research_q.put(None)
                await ui_q.put({"stage": "researcher", "type": "done"})

        async def bridge_writer():
            try:
                async for delta in run_writer(task, research_q, cfg):
                    await writer_q.put(delta)
                    await ui_q.put({"stage": "writer", "type": "text", "delta": delta})
            except Exception as exc:
                await ui_q.put({"stage": "writer", "type": "error", "error": str(exc)})
            finally:
                await writer_q.put(None)
                await ui_q.put({"stage": "writer", "type": "done"})

        async def bridge_reviewer():
            try:
                async for delta in run_reviewer(task, writer_q, cfg):
                    await ui_q.put({"stage": "reviewer", "type": "text", "delta": delta})
            except Exception as exc:
                await ui_q.put({"stage": "reviewer", "type": "error", "error": str(exc)})
            finally:
                await ui_q.put({"stage": "reviewer", "type": "done"})

        bg_tasks = [
            asyncio.create_task(bridge_research()),
            asyncio.create_task(bridge_writer()),
            asyncio.create_task(bridge_reviewer()),
        ]

        run_state["events"].append({
            "event": "status",
            "data": {
                "state": "started",
                "mode": "dry-run" if cfg.dry_run else "vllm",
                "routing": "researcher/reviewer->CPU, writer->GPU",
            },
        })

        done = {"researcher": False, "writer": False, "reviewer": False}
        stall_timeout = max(cfg.writer_timeout_s, 300) + 60
        while True:
            try:
                msg = await asyncio.wait_for(ui_q.get(), timeout=stall_timeout)
            except asyncio.TimeoutError:
                run_state["events"].append({
                    "event": "status",
                    "data": {"state": "error", "error": "Pipeline stalled."},
                })
                break
            if msg.get("type") == "done":
                done[msg["stage"]] = True
            run_state["events"].append({"event": "update", "data": msg})
            if all(done.values()):
                break

        await asyncio.gather(*bg_tasks, return_exceptions=True)
        run_state["events"].append({
            "event": "status",
            "data": {"state": "finished"},
        })
        run_state["done"] = True

    asyncio.create_task(run_pipeline())
    return {"run_id": run_id}


@app.get("/poll")
async def poll(run_id: str, cursor: int = 0):
    """Return new events since cursor."""
    run_state = _runs.get(run_id)
    if not run_state:
        return JSONResponse({"error": "unknown run_id"}, status_code=404)

    events = run_state["events"][cursor:]
    done = run_state["done"]

    # Clean up finished runs after client has seen all events
    if done and cursor + len(events) >= len(run_state["events"]):
        _runs.pop(run_id, None)

    return {"events": events, "done": done}
