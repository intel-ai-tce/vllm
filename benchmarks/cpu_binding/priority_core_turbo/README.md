# Enabling Priority Core Turbo (PCT) for vLLM GPU Performance

## Overview

**Intel® Priority Core Turbo (PCT)** is part of **Intel® Speed Select Technology – Turbo Frequency (SST-TF)**.
It allows a subset of CPU cores to operate at **higher turbo frequencies**, while remaining cores run closer to base frequency.

This is particularly effective for **GPU-accelerated vLLM inference**, where a small number of CPU threads handle
**latency-critical, mostly serial tasks** such as tokenization, scheduling, and feeding GPUs.
Running these threads on **High-Priority (HP) cores** improves GPU utilization, TTFT, and tail latency.

Validated platforms:

- **Intel® Xeon® 6776P**

## How PCT Works

PCT relies on **two Intel Speed Select features**:

- **SST-TF (Turbo Frequency)**
  Defines how many cores are allowed to run at higher turbo frequencies (HP cores).

- **SST-CP (Core Power / CLOS)**
  Assigns CPUs to **Classes of Service (CLOS)**.
  Only CPUs assigned to **CLOS0** are treated as **High-Priority** by PCT.

> **Important:** PCT is only effective when CPUs are explicitly assigned to **CLOS0**.

### PCT bucket-count interpretation

`intel-speed-select turbo-freq info -l <level>` may print the same `bucket-0`,
`bucket-1`, and `bucket-2` SST-TF table under multiple `powerdomain-*` anchors.

For PCT capacity, this flow counts `bucket-0` **once per package/socket**:

```text
bucket-0 high-priority-cores-count:8 @ 4600 MHz
=> 8 PCT physical cores per package/socket
```

On a two-socket Intel® Xeon® 6776P system with Hyper-Threading enabled:

```text
2 packages × 8 physical PCT cores/package = 16 physical PCT cores total
16 physical PCT cores × 2 threads/core    = 32 logical PCT CPUs total
```

## 1. Build the Environment

Export the kernel build variables first:

```bash
source ./set_kernel_env.sh
```

Expected on a Linux `6.8.0-*` host:

```text
Exported KERNEL_MM=6.8
Exported KERNEL_TAG=v6.8
```

These variables are used by `docker-compose.yml`:

| Variable | Example | Purpose |
| --- | --- | --- |
| `KERNEL_MM` | `6.8` | Docker image tag suffix |
| `KERNEL_TAG` | `v6.8` | Linux kernel git tag used to build `intel-speed-select` |

Build the Docker image with required tools:

```bash
docker compose --progress=plain build --no-cache
```

Verify `intel-speed-select` exists inside the image:

```bash
docker compose run --rm intel-speed-select-shell 'which intel-speed-select && intel-speed-select --help | head'
```

## 2. Check PCT Status (Read-Only)

This step verifies:

- Hardware support for Intel® Speed Select features
- SST-TF/PCT bucket-0 capacity
- Correct package/socket-based PCT capacity counting
- Core Power and CLOS enablement
- Current CPU-to-CLOS mapping
- Whether the current `TARGET_CLOS` CPU count matches the expected PCT logical CPU budget

Run:

```bash
docker compose --progress=plain --profile check up --abort-on-container-exit
```

Example results when PCT and CLOS are enabled successfully:

```bash
------------------------------------------------------------
CPU and Intel Speed Select Capability
------------------------------------------------------------
Intel(R) SST-PP (feature perf-profile) is supported
Intel(R) SST-TF (feature turbo-freq) is supported
Intel(R) SST-BF (feature base-freq) is not supported
Intel(R) SST-CP (feature core-power) is supported
Intel(R) Speed Select Technology
Executing on CPU model:173[0xad]

------------------------------------------------------------
PCT Capacity from SST-TF bucket-0
------------------------------------------------------------
✅ PCT/SST-TF turbo tables detected.
PCT_BUCKET=bucket-0
PCT_REPORTING_ANCHORS=4
PCT_ACTIVE_PACKAGES=2
PCT_CORES_PER_PACKAGE=8
PCT_TOTAL_PHYSICAL_CORES=16
PCT_MAX_FREQ_MHZ=4600
PCT_DOMAIN_ANCHORS=pkg0/die0/pd0/cpu0:cores8:freq4600,pkg0/die0/pd1/cpu32:cores8:freq4600,pkg1/die1/pd0/cpu64:cores8:freq4600,pkg1/die1/pd1/cpu96:cores8:freq4600
PCT_PACKAGE_SUMMARY=pkg0:cores8:freq4600:anchors2,pkg1:cores8:freq4600:anchors2
THREADS_PER_CORE=2
PCT_TOTAL_LOGICAL_CPUS=32

------------------------------------------------------------
Core Power (CLOS) Feature Status
------------------------------------------------------------
✅ Core Power feature ENABLED
✅ CLOS ENABLED

------------------------------------------------------------
CPU -> CLOS Mapping via get-assoc
------------------------------------------------------------
CLOS distribution (count by clos id):
  clos:0 -> 32 CPUs
  clos:3 -> 224 CPUs

------------------------------------------------------------
CPU list for TARGET_CLOS=0
------------------------------------------------------------
clos:0 CPU list: 0,8,16,24,32,40,48,56,64,72,80,88,96,104,112,120,128,136,144,152,160,168,176,184,192,200,208,216,224,232,240,248
Wrote clos:0 CPU list to /workspace/benchmarks/results/clos0_cpulist.txt

------------------------------------------------------------
PCT Budget Validation for CLOS0
------------------------------------------------------------
CLOS0 CPU count             : 32
PCT bucket                        : bucket-0
PCT reporting anchors             : 4
PCT active packages/sockets       : 2
PCT cores per package/socket      : 8
PCT physical core budget          : 16
PCT max frequency                 : 4600 MHz
Threads per core                  : 2
Expected PCT logical CPU budget   : 32
✅ CLOS0 CPU count exactly matches the bucket-0 PCT logical budget.

------------------------------------------------------------
Summary
------------------------------------------------------------
✅ PCT turbo tables detected
✅ PCT capacity detected: 16 physical HP cores total, 32 logical CPUs with HT=2
   Count model: bucket-0 counted once per package/socket, not once per powerdomain anchor.
✅ Core Power enabled
✅ CLOS enabled
Done.
```

The check script writes the current target-CLOS CPU list to:

```text
./results/clos0_cpulist.txt
```

For the example above, `clos0_cpulist.txt` contains 32 logical CPUs. With
Hyper-Threading enabled, that corresponds to 16 physical PCT cores.

> **Note:** CLOS assignment and CLOS enforcement are different. `get-assoc` may
> show CPU-to-CLOS mappings even when `core-power info` reports Core Power or
> CLOS disabled. For PCT benchmarking, ensure both Core Power and CLOS are enabled.

## 3. Set PCT (Assign CPUs to CLOS0)

This step **activates PCT in practice** by assigning CPUs to the correct
**Class of Service (CLOS)**.

The setup script automatically performs the following actions:

- Detects how many **High-Priority (HP) cores** are supported by the platform
  (from Intel Speed Select bucket data)
- Selects HP CPUs according to the script's mapping policy
- Expands the HP set to include **Hyper-Threading siblings** when required
- Assigns:
    - **HP CPUs → CLOS0** (eligible for Priority Core Turbo)
    - **All remaining CPUs → CLOS2/CLOS3** depending on script configuration

Run the setup:

```bash
docker compose --progress=plain --profile set up --abort-on-container-exit
```

Example results when PCT is set successfully based on power-domains.

```bash
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | Config
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | HP_PER_DOMAIN=8 (HP_BUCKET=0)
intel-speed-select-set-1  | INCLUDE_HT=0
intel-speed-select-set-1  | HP_CLOS=0  OTHER_CLOS=2
intel-speed-select-set-1  | DEBUG_MODE=0  DRY_RUN=0  DEBUG_VERBOSE=0  DEBUG_MAP=0
intel-speed-select-set-1  |
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | HP selection per NUMA node (initial pick)
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | node 0 -> 0 1 2 3 4 5 6 7
intel-speed-select-set-1  | node 1 -> 32 33 34 35 36 37 38 39
intel-speed-select-set-1  | node 2 -> 64 65 66 67 68 69 70 71
intel-speed-select-set-1  | node 3 -> 96 97 98 99 100 101 102 103
intel-speed-select-set-1  |
intel-speed-select-set-1  | HP initial ranges      : 0-7,32-39,64-71,96-103
intel-speed-select-set-1  | HP effective (with HT) : 0-7,32-39,64-71,96-103,128-135,160-167,192-199,224-231
intel-speed-select-set-1  |
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | Computed CPU lists
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | HP (effective) : 0-7,32-39,64-71,96-103,128-135,160-167,192-199,224-231
intel-speed-select-set-1  | Non-HP         : 8-31,40-63,72-95,104-127,136-159,168-191,200-223,232-255
intel-speed-select-set-1  |
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | Apply CLOS assignments (quiet)
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | Setting HP -> CLOS0, Non-HP -> CLOS2
intel-speed-select-set-1  | Applied.
intel-speed-select-set-1  |
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | Verification (concise CPU->CLOS)
intel-speed-select-set-1  | ------------------------------------------------------------
intel-speed-select-set-1  | HP list should be clos:0
intel-speed-select-set-1  | cpu-0 clos:0
intel-speed-select-set-1  | … (showing first 40 lines)
intel-speed-select-set-1  |
intel-speed-select-set-1  | Non-HP list should be clos:2
intel-speed-select-set-1  | cpu-8 clos:2
intel-speed-select-set-1  | … (showing first 40 lines)
intel-speed-select-set-1  |
intel-speed-select-set-1  | Done.
intel-speed-select-set-1 exited with code 0
```

## 4. Benchmark CLOS0 CPUs with Host PerfSpect

Use Docker only to configure and verify PCT/CLOS. Run PerfSpect on the host so
the frequency benchmark can access host CPU frequency interfaces directly.

### prerequisites

The host benchmark script reads the CPU list generated by the check profile:

```bash
./results/clos0_cpulist.txt
```

Install PerfSpect on the host first:

```bash
mkdir -p "${HOME}/tools"
cd "${HOME}/tools"

wget -qO- https://github.com/intel/PerfSpect/releases/latest/download/perfspect.tgz | tar -xz

sudo ln -sf "${HOME}/tools/perfspect/perfspect" /usr/local/bin/perfspect
```

Confirm it is available:

```bash
which perfspect
perfspect --help | head
```

### Run the benchmark

Run the full flow:

```bash
docker compose --progress=plain --profile set up --abort-on-container-exit
docker compose --progress=plain --profile check up --abort-on-container-exit

./run_host_perfspect_benchmark.sh
```

Default host benchmark command:

```bash
sudo taskset -c "${CLOS_CPUS}" perfspect benchmark --speed --frequency --no-summary --output <output-dir>
```

Override the PerfSpect benchmark options with `PERFSPECT_ARGS`:

```bash
PERFSPECT_ARGS="--speed --frequency --memory --no-summary" \
./run_host_perfspect_benchmark.sh
```

### Analyze results

Benchmark output is written under:

```bash
./results/perfspect_host_clos0_<timestamp>/
```

The directory includes:

```text
clos0_cpulist.txt
perfspect_benchmark.log
perfspect/
```

Check the Frequency Benchmark section in the generated HTML report.

A near-4.6 GHz frequency is expected only when the benchmark uses a small number
of active PCT/high-priority cores. When more logical CPUs are active, the observed
frequency should be compared against the active physical core count and the
corresponding SST-TF / turbo ratio bucket.

For PCT validation, start with `--speed --frequency --no-summary`. Avoid `--all`
unless you intentionally want storage, memory, power, and other platform-level
tests included in the same run.

## 5. Debug / Manual Inspection (Optional)

This section is useful for **troubleshooting**, **validation**, or **manual experimentation**
with Intel® Speed Select and PCT behavior.

Start an interactive shell with the required tools installed:

```bash
docker compose run --rm intel-speed-select-shell
```
