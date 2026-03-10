
# Multi-Agent App on 2 Endpoints

Routing:
- Researcher -> CPU endpoint (8B)
- Writer -> GPU endpoint (405B)
- Reviewer -> CPU endpoint (8B)

---

## Architecture Overview

The multi-agent pipeline runs **three logical agents** across **two hardware endpoints**.

| Agent | Hardware | Model | UI Color |
|------|------|------|------|
| Researcher | CPU | 8B model | 🟡 Yellow |
| Writer | GPU | 405B model | 🔵 Blue |
| Reviewer | CPU | 8B model | 🟢 Green |

The pipeline follows a **dependency order** but allows **partial parallel execution** using a pipelined architecture.

---

# Hardware Mapping Diagram

This diagram matches the **colors used in the UI demo**.

```mermaid
flowchart LR

User["User Task Input"]

subgraph CPU_Lane["CPU Lane (8B Model)"]
direction TB
Researcher["🟡 Researcher Agent
Fact Finding & Research"]
Reviewer["🟢 Reviewer Agent
Edits & Feedback"]
end

subgraph GPU_Lane["GPU Lane (405B Model)"]
direction TB
Writer["🔵 Writer Agent
Draft Generation"]
end

User --> Researcher
Researcher -->|Research Notes| Writer
Writer -->|Draft| Reviewer
Reviewer --> Output["Final Reviewed Output"]

style Researcher fill:#FFE082,stroke:#333
style Writer fill:#90CAF9,stroke:#333
style Reviewer fill:#A5D6A7,stroke:#333
```

---

# Runtime Execution (Pipelined)

Although the logical dependency is:

```
Researcher → Writer → Reviewer
```

the system uses **pipelined execution**, meaning later stages may start before earlier stages fully complete.

```mermaid
sequenceDiagram

participant U as User
participant R as 🟡 Researcher (CPU 8B)
participant W as 🔵 Writer (GPU 405B)
participant V as 🟢 Reviewer (CPU 8B)

U->>R: Submit task

Note right of R: Extract facts and notes

R-->>W: Partial research notes
Note right of W: Writer starts early

R-->>W: More notes
W->>W: Draft generation

Note right of W: GPU continues writing

W-->>V: Draft available
Note right of V: Reviewer starts

V->>V: Edits and feedback

V-->>U: Final reviewed output
```

---

# Runtime Parallelism

During execution, the stages overlap in time.

```
Time →
Researcher (CPU 8B)  █████████████
Writer (GPU 405B)          █████████████████
Reviewer (CPU 8B)                 ███████
```

This means:

- Researcher begins first
- Writer starts when **partial notes arrive**
- Reviewer starts when **a partial draft exists**

This architecture reduces overall latency compared to strictly sequential execution.

---

# Why This Hardware Split Works

### CPU (8B model)

Best for lightweight reasoning tasks:

- research extraction
- summarization
- critique and editing
- short outputs

### GPU (405B model)

Best for heavy generation tasks:

- long structured responses
- complex reasoning
- synthesis across notes

### Pipeline Benefit

Without pipelining:

```
Total latency = Research + Write + Review
```

With pipelining:

```
Total latency ≈ max(Research, Write, Review)
```

because stages overlap in time.

---

# Files

- `app.py` - colorful UI + SSE stream
- `agents.py` - 2-endpoint routing logic
- `vllm_client.py` - OpenAI-compatible streaming client
- `env_set.sh` - environment setup helper
- `requirements.txt`

---

# Dry-run mode

```bash
source ./env_set.sh
export DRY_RUN=1
uvicorn app:app --host 0.0.0.0 --port 8000
```

---

# Real vLLM mode

First start the two model endpoints.

### CPU 8B endpoint

```bash
VLLM_CPU_KVCACHE_SPACE=8 vllm serve meta-llama/Llama-3.1-8B-Instruct   --host 0.0.0.0 --port 8001   --dtype bfloat16   --max-model-len 8192
```

### GPU 405B endpoint

```bash
vllm serve meta-llama/Llama-3.1-405B-Instruct   --host 0.0.0.0 --port 8002   --dtype bfloat16   --max-model-len 8192
```

Then:

```bash
source ./env_set.sh
export DRY_RUN=0
export CPU_URL=http://<cpu-host>:8001
export GPU_URL=http://<gpu-host>:8002

pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open:

```
http://localhost:8000
```
