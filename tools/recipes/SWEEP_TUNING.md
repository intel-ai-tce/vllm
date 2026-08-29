# Sweep Tuning

Sweep tuning is optional. The converter always writes an initial `config.yml`
that can be deployed immediately. A sweep adds benchmark evidence and produces
a measured recommendation without changing the source recipe.

## Choose a Workflow

| Goal | Option | Stages |
| --- | --- | --- |
| Keep the initial TP/DP layout and tune scheduling | `--generate-sweep` | Scheduler sweep |
| Compare full-NUMA TP/DP layouts before tuning scheduling | `--generate-parallel-layout-sweep` | Parallel-layout sweep, then scheduler sweep |

Both workflows require `--input-tokens`, `--output-tokens`, and `--concurrency`.
TTFT and TPOT objectives are optional but recommended for deployment tuning.

## Scheduler-Only Sweep

Use this workflow when the recipe or runtime policy already provides the TP/DP
layout to retain.

### Generate

```bash
python3 tools/recipes/recipe_json_to_vllm_config.py \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --hardware xeon6 \
  --detect-hardware \
  --input-tokens 128 \
  --output-tokens 128 \
  --concurrency 32 \
  --ttft-sla-ms 3000 \
  --tpot-sla-ms 100 \
  --generate-sweep
```

The generated eight-point directed design jointly varies:

- `max-num-seqs`
- `max-num-batched-tokens`

It measures the batch-budget curve at the initial sequence count and selected
interactions at three-quarters and one-half of that count. This provides broader
coverage than one-parameter-at-a-time tuning without a full Cartesian grid.

### Run

```bash
sweep/run_sweep.sh --dry-run
sweep/run_sweep.sh
sweep/recommend.py
```

Resume an interrupted benchmark with:

```bash
sweep/run_sweep.sh --resume
```

## Staged Parallel-Layout and Scheduler Sweep

Use this workflow when TP/DP placement must be measured before scheduler
tuning. Hardware detection is required because the candidate layouts are
derived from the effective NUMA topology visible to the process or container.

### Generate

```bash
python3 tools/recipes/recipe_json_to_vllm_config.py \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --hardware xeon6 \
  --detect-hardware \
  --input-tokens 128 \
  --output-tokens 128 \
  --concurrency 32 \
  --ttft-sla-ms 3000 \
  --tpot-sla-ms 100 \
  --generate-parallel-layout-sweep
```

### Stage 1: Select TP/DP

The primary candidates use all effective NUMA nodes:

```text
tensor-parallel-size * data-parallel-size = effective NUMA nodes
```

TP is restricted to the supported values `1`, `2`, `4`, and `8`.

The sweep also includes the largest supported TP size that does not exceed the
effective NUMA-node count. This additional candidate may leave some NUMA nodes
idle, but measures whether a larger single-replica TP layout performs better.

| Effective NUMA nodes | Generated layouts |
| ---: | --- |
| 2 | `TP=2, DP=1`; `TP=1, DP=2` |
| 4 | `TP=4, DP=1`; `TP=2, DP=2`; `TP=1, DP=4` |
| 6 | `TP=4, DP=1` (4 of 6 nodes); `TP=2, DP=3`; `TP=1, DP=6` |
| 8 | `TP=8, DP=1`; `TP=4, DP=2`; `TP=2, DP=4`; `TP=1, DP=8` |

`TP=1, DP=1` is excluded when it is neither a full-NUMA layout nor the largest
supported TP candidate. Unsupported layouts such as `TP=6, DP=1` remain
excluded. Each candidate receives an initial per-replica scheduler baseline:

```text
max-num-seqs = ceil(global concurrency / data-parallel-size)
```

Run and select the parallel layout:

```bash
sweep/run_parallel_layout_sweep.sh --dry-run
sweep/run_parallel_layout_sweep.sh
sweep/recommend_parallel_layout.py
```

This writes:

```text
sweep/parallel-layout-config.yml
sweep/parallel-layout-recommendation.json
```

### Stage 2: Tune the Selected Layout

The scheduler sweep uses `parallel-layout-config.yml` as its base and varies
only `max-num-seqs` and `max-num-batched-tokens`:

```bash
sweep/run_sweep.sh --dry-run
sweep/run_sweep.sh
sweep/recommend.py
```

Do not start Stage 2 before Stage 1 has produced
`parallel-layout-config.yml`.

## Recommendation Policy

With TTFT or TPOT objectives, the benchmark uses vLLM `--goodput`. Each
recommender:

1. Excludes configurations with failed requests or missing required metrics.
2. Calculates duration-weighted combined compliance across repeated runs.
3. Requires median P99 TTFT/TPOT compliance and the minimum combined compliance
   ratio, which defaults to `0.99`.
4. Selects the eligible configuration with the highest mean aggregate
   output-token throughput.

Change the compliance threshold with:

```bash
sweep/recommend.py --minimum-compliance VALUE
```

If no configuration is eligible, the recommender records the highest-goodput
candidate as `best_effort`, does not write a deployable configuration, and exits
with status 2. Without latency objectives it selects the highest mean
output-token throughput. Recommendation JSON records mean, median, and worst-run
P99 values, combined compliance, and evidence for every candidate.

## Generated Files

The scheduler-only package contains:

```text
sweep/
├── bench_params.json
├── serve_params.json
├── run_sweep.sh
├── recommend.py
└── SWEEP.md
```

The staged workflow additionally contains:

```text
sweep/
├── parallel_layout_serve_params.json
├── run_parallel_layout_sweep.sh
├── recommend_parallel_layout.py
├── parallel-layout-config.yml             # after Stage 1 recommendation
└── parallel-layout-recommendation.json     # after Stage 1 recommendation
```

The final scheduler recommendation is written to:

```text
sweep/recommended-config.yml
sweep/recommendation.json
```

## Run in the vLLM CPU Container

Use the CPU container setup in
[RUNTIME_TUNING.md](RUNTIME_TUNING.md#vllm-cpu-docker-shell). Running hardware
detection inside the target container ensures that CPU, NUMA, memory, and
cgroup limits match the deployment.

Example staged generation inside the container:

```bash
python3 /recipes/recipe_json_to_vllm_config.py \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --hardware xeon6 \
  --detect-hardware \
  --input-tokens 128 \
  --output-tokens 128 \
  --concurrency 32 \
  --ttft-sla-ms 3000 \
  --tpot-sla-ms 100 \
  --config-out /output/config.yml \
  --env-out /output/env.sh \
  --generate-parallel-layout-sweep \
  --sweep-out-dir /output/sweep
```

The initial configuration remains directly deployable:

```bash
source /output/env.sh
vllm serve --config /output/config.yml
```

Stop a manually started server before running a sweep because the sweep scripts
start and stop their own vLLM servers.

Run the staged workflow:

```bash
/output/sweep/run_parallel_layout_sweep.sh
/output/sweep/recommend_parallel_layout.py
/output/sweep/run_sweep.sh
/output/sweep/recommend.py
```

Inspect and deploy the final result:

```bash
cat /output/sweep/recommendation.json
source /output/env.sh
vllm serve --config /output/sweep/recommended-config.yml
```
