# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

"""Generate optional vLLM benchmark sweep files from one initial suggestion."""

from __future__ import annotations

import json
import math
import os
import shlex
from pathlib import Path
from typing import Any

from runtime_tuning import WorkloadHints

SUPPORTED_TENSOR_PARALLEL_SIZES = frozenset({1, 2, 4, 8})


def _positive_int(config: dict[str, Any], key: str) -> int:
    value = config.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Sweep generation requires a positive initial {key!r} value.")
    return value


def _strict_lower_power_of_two(value: int) -> int:
    if value <= 1:
        return 1
    return 1 << ((value - 1).bit_length() - 1)


def _strict_upper_power_of_two(value: int) -> int:
    return 1 << value.bit_length()


def validate_sweep_workload(workload: WorkloadHints) -> None:
    required = {
        "--input-tokens": workload.input_tokens,
        "--output-tokens": workload.output_tokens,
        "--concurrency": workload.concurrency,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError("--generate-sweep requires " + ", ".join(missing) + ".")


def build_serve_params(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a diverse, bounded sweep around the initial suggestion.

    The initial five-point sweep changed only one parameter at a time and
    skipped the useful middle sequence count.  Eight directed points cover the
    batch-budget curve at full concurrency plus interactions at 3/4 and 1/2 of
    the initial scheduler concurrency without paying for a full Cartesian grid.
    """
    initial_seqs = _positive_int(config, "max-num-seqs")
    initial_batch = _positive_int(config, "max-num-batched-tokens")

    minimum_batch = initial_seqs
    if config.get("enable-chunked-prefill") is False:
        max_model_len = config.get("max-model-len")
        if (
            isinstance(max_model_len, int)
            and not isinstance(max_model_len, bool)
            and max_model_len > 0
        ):
            minimum_batch = max(minimum_batch, max_model_len)

    lower_seqs = max(1, (initial_seqs + 1) // 2)
    middle_seqs = max(lower_seqs, (3 * initial_seqs + 3) // 4)
    lower_batch = max(
        minimum_batch,
        _strict_lower_power_of_two(initial_batch),
    )
    smaller_batch = max(
        minimum_batch,
        _strict_lower_power_of_two(lower_batch),
    )
    higher_batch = max(
        minimum_batch,
        _strict_upper_power_of_two(initial_batch),
    )

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    def add(name: str, max_num_seqs: int, max_num_batched_tokens: int) -> None:
        max_num_batched_tokens = max(
            max_num_batched_tokens,
            max_num_seqs,
        )
        signature = (max_num_seqs, max_num_batched_tokens)
        if signature in seen:
            return
        seen.add(signature)
        candidates.append(
            {
                "_benchmark_name": name,
                "max_num_seqs": max_num_seqs,
                "max_num_batched_tokens": max_num_batched_tokens,
            }
        )

    # Keep the exact initial suggestion as the measured baseline. Additional
    # values exist only in the optional sweep package.
    add("initial", initial_seqs, initial_batch)
    add("smaller_batch_budget", initial_seqs, smaller_batch)
    add("lower_batch_budget", initial_seqs, lower_batch)
    add("higher_batch_budget", initial_seqs, higher_batch)
    add("middle_seqs_lower_batch", middle_seqs, lower_batch)
    add("middle_seqs_higher_batch", middle_seqs, higher_batch)
    add("lower_seqs_lower_batch", lower_seqs, lower_batch)
    add("lower_seqs_higher_batch", lower_seqs, higher_batch)

    return candidates


def _scheduler_baseline_for_dp(
    config: dict[str, Any], workload: WorkloadHints, data_parallel_size: int
) -> tuple[int, int]:
    """Return per-replica scheduler settings for a DP layout."""
    assert workload.concurrency is not None
    assert workload.input_tokens is not None
    per_replica_concurrency = math.ceil(workload.concurrency / data_parallel_size)
    output_tokens = workload.output_tokens or 1
    prefills_per_step = max(1.0, per_replica_concurrency / output_tokens)
    if workload.target_qps is not None and workload.tpot_sla_ms is not None:
        per_replica_qps = workload.target_qps / data_parallel_size
        prefills_per_step = max(
            prefills_per_step,
            per_replica_qps * workload.tpot_sla_ms / 1000.0,
        )
    prefills_per_step = min(float(per_replica_concurrency), prefills_per_step)
    batch = max(
        2048,
        per_replica_concurrency,
        per_replica_concurrency + math.ceil(workload.input_tokens * prefills_per_step),
    )
    if config.get("enable-chunked-prefill") is False:
        max_model_len = config.get("max-model-len")
        if isinstance(max_model_len, int) and not isinstance(max_model_len, bool):
            batch = max(batch, max_model_len)
    return per_replica_concurrency, batch


def build_parallel_layout_params(
    config: dict[str, Any], workload: WorkloadHints, numa_node_count: int
) -> list[dict[str, Any]]:
    """Build TP/DP layouts that use every effective NUMA node."""
    validate_sweep_workload(workload)
    if numa_node_count <= 1:
        raise ValueError("Parallel-layout sweep requires at least two NUMA nodes.")

    candidates = []
    for tensor_parallel_size in range(numa_node_count, 0, -1):
        if (
            tensor_parallel_size not in SUPPORTED_TENSOR_PARALLEL_SIZES
            or numa_node_count % tensor_parallel_size
        ):
            continue
        data_parallel_size = numa_node_count // tensor_parallel_size
        max_num_seqs, max_num_batched_tokens = _scheduler_baseline_for_dp(
            config, workload, data_parallel_size
        )
        candidates.append(
            {
                "_benchmark_name": (f"tp{tensor_parallel_size}_dp{data_parallel_size}"),
                "tensor_parallel_size": tensor_parallel_size,
                "data_parallel_size": data_parallel_size,
                "max_num_seqs": max_num_seqs,
                "max_num_batched_tokens": max_num_batched_tokens,
            }
        )
    return candidates


def build_bench_params(workload: WorkloadHints) -> list[dict[str, Any]]:
    validate_sweep_workload(workload)
    assert workload.input_tokens is not None
    assert workload.output_tokens is not None
    assert workload.concurrency is not None

    return [
        {
            "_benchmark_name": "user_workload",
            "random_input_len": workload.input_tokens,
            "random_output_len": workload.output_tokens,
            "max_concurrency": workload.concurrency,
        }
    ]


def _benchmark_models(config: dict[str, Any]) -> tuple[str, str]:
    model = config.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("Sweep generation requires a model in config.yml.")

    served_model_name = config.get("served-model-name")
    if isinstance(served_model_name, str) and served_model_name:
        return served_model_name, model
    if (
        isinstance(served_model_name, list)
        and served_model_name
        and isinstance(served_model_name[0], str)
    ):
        return served_model_name[0], model

    return model, model


def _relative_to(directory: Path, target: str) -> str:
    return os.path.relpath(Path(target).resolve(), directory.resolve())


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_run_script(
    path: Path,
    *,
    config_rel: str,
    env_rel: str,
    request_model: str,
    tokenizer: str,
    workload: WorkloadHints,
    serve_params_name: str = "serve_params.json",
    experiment_name: str = "runtime-tuning",
) -> None:
    bench_parts = [
        "vllm bench serve",
        "--backend vllm",
        f"--model {shlex.quote(request_model)}",
        f"--tokenizer {shlex.quote(tokenizer)}",
        "--dataset-name random",
        "--request-rate inf",
        "--ignore-eos",
        "--metric-percentiles 99",
    ]

    goodput_pairs: list[str] = []
    if workload.ttft_sla_ms is not None:
        goodput_pairs.append(f"ttft:{workload.ttft_sla_ms:g}")
    if workload.tpot_sla_ms is not None:
        goodput_pairs.append(f"tpot:{workload.tpot_sla_ms:g}")
    if goodput_pairs:
        bench_parts.append(
            "--goodput " + " ".join(shlex.quote(pair) for pair in goodput_pairs)
        )

    bench_cmd = " ".join(bench_parts)
    script = f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
CONFIG_PATH="${{SCRIPT_DIR}}/{config_rel}"
ENV_PATH="${{SCRIPT_DIR}}/{env_rel}"

source "${{ENV_PATH}}"

vllm bench sweep serve \
  --serve-cmd "vllm serve --config '${{CONFIG_PATH}}'" \
  --bench-cmd "{bench_cmd}" \
  --serve-params "${{SCRIPT_DIR}}/{serve_params_name}" \
  --bench-params "${{SCRIPT_DIR}}/bench_params.json" \
  --output-dir "${{SCRIPT_DIR}}/results" \
  --experiment-name {experiment_name} \
  "$@"
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def _write_recommend_script(
    path: Path,
    *,
    config_rel: str,
    env_rel: str,
    workload: WorkloadHints,
    results_dir: str = "results/runtime-tuning",
    output_config: str = "recommended-config.yml",
    output_json: str = "recommendation.json",
) -> None:
    template_path = Path(__file__).with_name("sweep_recommendation.py")
    source = template_path.read_text(encoding="utf-8")

    replacements = {
        "DEFAULT_CONFIG_PATH: str | None = None": (
            f"DEFAULT_CONFIG_PATH: str | None = {config_rel!r}"
        ),
        "DEFAULT_ENV_PATH: str | None = None": (
            f"DEFAULT_ENV_PATH: str | None = {env_rel!r}"
        ),
        "DEFAULT_TTFT_SLA_MS: float | None = None": (
            f"DEFAULT_TTFT_SLA_MS: float | None = {workload.ttft_sla_ms!r}"
        ),
        "DEFAULT_TPOT_SLA_MS: float | None = None": (
            f"DEFAULT_TPOT_SLA_MS: float | None = {workload.tpot_sla_ms!r}"
        ),
        'DEFAULT_RESULTS_DIR = "results/runtime-tuning"': (
            f"DEFAULT_RESULTS_DIR = {results_dir!r}"
        ),
        'DEFAULT_OUTPUT_CONFIG = "recommended-config.yml"': (
            f"DEFAULT_OUTPUT_CONFIG = {output_config!r}"
        ),
        'DEFAULT_OUTPUT_JSON = "recommendation.json"': (
            f"DEFAULT_OUTPUT_JSON = {output_json!r}"
        ),
    }
    for marker, replacement in replacements.items():
        if marker not in source:
            raise ValueError(f"Recommender template marker not found: {marker}")
        source = source.replace(marker, replacement, 1)

    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def _write_guide(path: Path, workload: WorkloadHints) -> None:
    sla_lines: list[str] = []
    if workload.ttft_sla_ms is not None:
        sla_lines.append(f"- TTFT objective: `{workload.ttft_sla_ms:g} ms`")
    if workload.tpot_sla_ms is not None:
        sla_lines.append(f"- TPOT objective: `{workload.tpot_sla_ms:g} ms`")

    sla_text = "\n".join(sla_lines)
    if sla_text:
        sla_text = (
            "\n## Supplied latency objectives\n\n"
            + sla_text
            + "\n\nThe generated benchmark uses these values with vLLM "
            "`--goodput`.\n"
        )

    content = f"""# Optional Runtime Tuning Sweep

The generated `config.yml` is the **single initial suggestion** and can be
deployed directly. The sweep benchmarks nearby values for:

- `max-num-seqs`
- `max-num-batched-tokens`

## Run

```bash
./run_sweep.sh --dry-run
./run_sweep.sh
./recommend.py
```

For a quick one-run experiment:

```bash
rm -rf results/runtime-tuning
./run_sweep.sh --num-runs 1
./recommend.py
```

Resume an interrupted sweep:

```bash
./run_sweep.sh --resume
```

By default, vLLM benchmarks each parameter combination three times.
{sla_text}
## Outputs

`recommend.py` writes:

```text
recommended-config.yml
recommendation.json
```

With TTFT/TPOT objectives it requires duration-weighted combined compliance of
at least 99% plus median P99 TTFT/TPOT compliance, then selects highest mean
output-token throughput. If no candidate qualifies, it records a best-effort
candidate but does not write `recommended-config.yml`. Without latency
objectives it selects highest mean output-token throughput. Configurations with
failed requests are excluded.

`recommended-config.yml` copies the initial configuration and changes only
`max-num-seqs` and `max-num-batched-tokens`.
"""
    path.write_text(content, encoding="utf-8")


def write_sweep_files(
    output_dir: str,
    *,
    config_path: str,
    env_path: str,
    config: dict[str, Any],
    workload: WorkloadHints,
) -> list[Path]:
    """Write an optional sweep package around the initial config suggestion."""
    validate_sweep_workload(workload)

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    serve_params = directory / "serve_params.json"
    bench_params = directory / "bench_params.json"
    run_script = directory / "run_sweep.sh"
    recommend_script = directory / "recommend.py"
    guide = directory / "SWEEP.md"

    config_rel = _relative_to(directory, config_path)
    env_rel = _relative_to(directory, env_path)

    _write_json(serve_params, build_serve_params(config))
    _write_json(bench_params, build_bench_params(workload))
    request_model, tokenizer = _benchmark_models(config)
    _write_run_script(
        run_script,
        config_rel=config_rel,
        env_rel=env_rel,
        request_model=request_model,
        tokenizer=tokenizer,
        workload=workload,
    )
    _write_recommend_script(
        recommend_script,
        config_rel=config_rel,
        env_rel=env_rel,
        workload=workload,
    )
    _write_guide(guide, workload)

    return [serve_params, bench_params, run_script, recommend_script, guide]


def write_parallel_layout_sweep_files(
    output_dir: str,
    *,
    config_path: str,
    env_path: str,
    config: dict[str, Any],
    workload: WorkloadHints,
    numa_node_count: int,
) -> list[Path]:
    """Write a TP/DP scan followed by the scheduler sweep package."""
    validate_sweep_workload(workload)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    parallel_params = directory / "parallel_layout_serve_params.json"
    scheduler_params = directory / "serve_params.json"
    bench_params = directory / "bench_params.json"
    run_parallel = directory / "run_parallel_layout_sweep.sh"
    recommend_parallel = directory / "recommend_parallel_layout.py"
    run_scheduler = directory / "run_sweep.sh"
    recommend_scheduler = directory / "recommend.py"
    guide = directory / "SWEEP.md"

    initial_config_rel = _relative_to(directory, config_path)
    selected_config_rel = "parallel-layout-config.yml"
    env_rel = _relative_to(directory, env_path)
    request_model, tokenizer = _benchmark_models(config)

    _write_json(
        parallel_params,
        build_parallel_layout_params(config, workload, numa_node_count),
    )
    _write_json(scheduler_params, build_serve_params(config))
    _write_json(bench_params, build_bench_params(workload))
    _write_run_script(
        run_parallel,
        config_rel=initial_config_rel,
        env_rel=env_rel,
        request_model=request_model,
        tokenizer=tokenizer,
        workload=workload,
        serve_params_name=parallel_params.name,
        experiment_name="parallel-layout",
    )
    _write_recommend_script(
        recommend_parallel,
        config_rel=initial_config_rel,
        env_rel=env_rel,
        workload=workload,
        results_dir="results/parallel-layout",
        output_config=selected_config_rel,
        output_json="parallel-layout-recommendation.json",
    )
    _write_run_script(
        run_scheduler,
        config_rel=selected_config_rel,
        env_rel=env_rel,
        request_model=request_model,
        tokenizer=tokenizer,
        workload=workload,
    )
    _write_recommend_script(
        recommend_scheduler,
        config_rel=selected_config_rel,
        env_rel=env_rel,
        workload=workload,
    )

    guide.write_text(
        f"""# Staged Parallel-Layout and Scheduler Sweep

All parallel-layout candidates use every effective NUMA node:

```text
tensor_parallel_size * data_parallel_size = {numa_node_count}
```

Tensor parallelism is restricted to `1`, `2`, `4`, or `8`.

Run the TP/DP scan first:

```bash
./run_parallel_layout_sweep.sh --dry-run
./run_parallel_layout_sweep.sh
./recommend_parallel_layout.py --results-dir results/parallel-layout
```

The recommender writes `parallel-layout-config.yml`. Then tune
`max-num-seqs` and `max-num-batched-tokens` around the selected layout:

```bash
./run_sweep.sh --dry-run
./run_sweep.sh
./recommend.py
```

Both recommenders require the supplied P99 objectives and combined compliance
when latency objectives are present, then maximize aggregate output throughput.
""",
        encoding="utf-8",
    )

    return [
        parallel_params,
        scheduler_params,
        bench_params,
        run_parallel,
        recommend_parallel,
        run_scheduler,
        recommend_scheduler,
        guide,
    ]
