# Pinning CPU Cores for Improving vLLM Performance on GPUs

This guide explains how to pin CPU cores for GPU-based vLLM inference and reuse idle CPUs for CPU-only inference workloads.

CPU pinning improves:

- **NUMA locality** for GPU workloads
- **Latency stability** for scheduling and tokenization threads
- **System utilization** by reusing idle CPUs for CPU inference

Intel **Priority Core Turbo (PCT)** can further improve GPU inference by ensuring latency-sensitive threads run on **high‑priority turbo cores**.

The validated platform for this workflow:

- **Intel Xeon 6776P (Xeon 6 platform)**

### Tested Azure VM

This workflow was validated on an Azure **NC RTX PRO 6000 Blackwell Server Edition v6-sizes series** VM (Preview as of May 20th, 2026).

Verify the GPU is exposed to the VM:

```bash
lspci | grep -i NVIDIA
```

`lspci` lists PCIe devices on the VM, including the InfiniBand NIC and GPUs. If it fails, you may need to install LIS on CentOS/RHEL.

## Install Drivers and CUDA on Azure NC RTX PRO 6000 BSE v6 (Blackwell)

This guide targets Azure NC RTX PRO 6000 BSE v6 (Blackwell).
Use Azure GRID vGPU20 drivers for this VM family, not Ubuntu-packaged NVIDIA drivers.

Reference this guide: [Install GRID drivers on NCv6 RTX PRO 6000 BSE VMs](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/n-series-driver-setup#install-grid-drivers-on-ncv6-rtx-pro-6000-bse-vms).

### Disable Secure Boot and vTPM

Disable Secure Boot and vTPM in the Azure Portal:

1. Stop the VM.
2. Go to **Configuration** → **Security type**.
3. Change from **Trusted Launch** to **Standard**.
4. Under the security settings, **uncheck / disable Secure Boot** (and vTPM if present).
5. Save and restart.

Verify from the terminal:

```bash
mokutil --sb-state
```

Should return `SecureBoot disabled`.

### NVIDIA Driver (Required for Blackwell)

Do not use Ubuntu-packaged NVIDIA drivers on Azure Blackwell VMs.
The Ubuntu `nvidia-driver-595-open` package does not support the Azure Blackwell vGPU
(PCI ID `10de:2bb5`, subsystem `1414:2187`).

Install Azure GRID vGPU20:

```bash
sudo apt update
sudo apt install -y build-essential dkms linux-headers-$(uname -r)
command -v cc
cc --version

wget https://download.microsoft.com/download/51239696-ec04-4c02-a6b3-1d9c608fb57c/NVIDIA-Linux-x86_64-595.58.03-grid-azure.run --no-check-certificate
chmod +x NVIDIA-Linux-x86_64-595.58.03-grid-azure.run
sudo ./NVIDIA-Linux-x86_64-595.58.03-grid-azure.run -M open --silent
```

The `-M open` flag is required because Blackwell needs open kernel modules.

Reboot the VM after the GPU driver is installed:

```bash
sudo reboot
```

After the driver is installed, add the NVIDIA CUDA apt repository and install the CUDA toolkit:

> **Note**
> The example shows the CUDA package path for Ubuntu 24.04 LTS. Use the path that's specific to the version you plan to use.
>
> Visit the NVIDIA Download Center or the NVIDIA CUDA Resources page for the full path that's specific to each version.

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo apt install -y ./cuda-keyring_1.1-1_all.deb
sudo apt update
apt-cache search '^cuda-toolkit-[0-9-]\+$' | sort
sudo apt -y install cuda-toolkit-12-5
```

If `cuda-toolkit-12-5` is not available on your image, install the latest version shown by `apt-cache search`.

Installation can take several minutes.

Reboot the VM after installation completes:

```bash
sudo reboot
```

Verify that the GPU is correctly recognized (after reboot):

```bash
nvidia-smi
```

### Install and start Docker

```bash
sudo apt install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker
sudo systemctl restart docker
sudo usermod -aG docker $USER
newgrp docker
```

This installs Docker, enables it at boot, and adds your user to the `docker` group so `sudo` is not needed for each Docker command.

Install and configure NVIDIA Container Toolkit:

```bash
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Verify GPU inside Docker

```bash
sudo docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
```

#### NVIDIA driver updates

Periodically update NVIDIA drivers after deployment.
For this VM family, use Azure/Microsoft-published GRID driver updates and do not
switch to Ubuntu-packaged NVIDIA drivers.

```bash
sudo apt update
sudo apt full-upgrade
```

---

## Architecture Overview


**docker-compose.override.yml** defines CPU pinning policy:

- GPU services run on **NUMA‑local CPUs**
- PCT cores are used for latency-sensitive GPU threads
- Remaining CPUs can be assigned to **CPU-only inference workloads**

---

## 0. (Optional) Enable Priority Core Turbo

Follow [Enabling Priority Core Turbo](priority_core_turbo/README.md)
to enable PCT on Intel® Xeon® 6 platforms.

After enabling PCT, a CPU list file is generated:

```bash
priority_core_turbo/results/clos0_cpulist.txt
```

Use this list for CPU binding.

---

## 1. Environment Setup

Install the Python venv package:

```bash
sudo apt install python3.12-venv -y
```

Create and activate the venv:

```bash
python3 -m venv ~/venv
source ~/venv/bin/activate
```

Clone vLLM, switch to the Azure CPU binding branch, and move into `vllm/benchmarks`:

```bash
git clone https://github.com/vllm-project/vllm.git
cd vllm
git checkout cpu_binding_demo_Azure
cd benchmarks
```

Install requirements:

```bash
pip install -r cpu_binding/requirements_cpu_binding.txt
pip install regex
```

Preflight checks before generating CPU binding:

```bash
cd ~/vllm/benchmarks/cpu_binding
pwd
ls generate_cpu_binding_from_csv.py cpu_binding_gnr.csv
```

---

## Blackwell Runtime Notes (Azure NC RTX PRO 6000 BSE v6)

### MIG Mode

Azure enables MIG, and it cannot be disabled on this VM type
(`nvidia-smi -i 0 -mig 0` returns `Not Supported`).
This is expected, and vLLM works normally.

### Tensor Parallel Size Overrides

- **GPU**: Single-GPU VMs must override `EXTRA_ARGS` to set
  `--tensor-parallel-size 1` (default is 2).
- **CPU**: The CPU container auto-detects NUMA nodes for TP size. On
  6-NUMA-node systems, this sets TP=6, but Llama-3.1-8B has 32 attention
  heads (not divisible by 6). Override with `--tensor-parallel-size 4` via
  `CPU_EXTRA_ARGS`.

### Disk Space Management

The 128GB root disk can fill from two sources:

- HF model cache (fix with `MODEL_CACHE` and `CPU_MODEL_CACHE`)
- Docker/containerd image layers under `/var/lib` (fix by moving Docker runtime storage to `/mnt`)

#### A) Configure HF cache on the ephemeral disk

```bash
sudo mkdir -p /mnt/hf_cache
sudo chown -R $USER:docker /mnt/hf_cache
mkdir -p ~/.cache
ln -sfn /mnt/hf_cache ~/.cache/huggingface
ls -ld /mnt/hf_cache ~/.cache/huggingface

export MODEL_CACHE=/mnt/hf_cache
export CPU_MODEL_CACHE=/mnt/hf_cache
```

#### B) Move Docker/containerd runtime storage to the ephemeral disk

```bash
sudo systemctl stop docker
sudo systemctl stop containerd

sudo mkdir -p /mnt/docker-data /mnt/containerd-data
sudo rsync -aHAX /var/lib/docker/ /mnt/docker-data/ 2>/dev/null || true
sudo rsync -aHAX /var/lib/containerd/ /mnt/containerd-data/ 2>/dev/null || true

sudo mv /var/lib/docker /var/lib/docker.bak 2>/dev/null || true
sudo mv /var/lib/containerd /var/lib/containerd.bak 2>/dev/null || true

sudo ln -s /mnt/docker-data /var/lib/docker
sudo ln -s /mnt/containerd-data /var/lib/containerd

sudo systemctl start containerd
sudo systemctl start docker

docker info | grep -i "Docker Root Dir"
df -h
```

`Docker Root Dir` should report `/mnt/docker-data`.

Note: `/mnt` is ephemeral and wiped on VM deallocation (but persists across
restarts).

### Standalone Deployment (Outside vllm Repo Tree)

When deploying the `cpu_binding/` directory standalone (outside the full
vllm repo), the default relative volume paths (`../../benchmarks`,
`../../.buildkite`) won't exist. Override them with real paths on the host.

Keep repo mounts under your local vllm checkout, and keep model cache on
`/mnt`:

```bash
export BENCHMARKS_DIR=~/vllm/benchmarks
export BUILDKITE_DIR=~/vllm/.buildkite
export MODEL_CACHE=/mnt/hf_cache
export CPU_MODEL_CACHE=/mnt/hf_cache
```

### CUDA Kernel Compilation on First Inference

The first inference request on a Blackwell GPU triggers CUDA kernel
compilation and can take **30+ minutes**. Plan for this warmup time. Do not
use health checks that send inference requests during startup.

---

## 2. GPU vLLM Service with CPU Pinning

Generate the CPU binding configuration:

```bash
cd ~/vllm/benchmarks/cpu_binding

# set token again on one line (no trailing newline)
export HF_TOKEN="YOUR_HF_TOKEN"

export MODEL="Qwen/Qwen2.5-32B-Instruct"
export MODEL_CACHE=/mnt/hf_cache
export CPU_MODEL_CACHE=/mnt/hf_cache

python3 generate_cpu_binding_from_csv.py \
  --settings cpu_binding_gnr.csv \
  --output docker-compose.override.yml
```

This generates a **docker-compose.override.yml** containing cpuset rules using lookup table
inside the cpu_binding_gnr.csv file.

All **deploy** and **benchmark** runs should include this override file.

---

### Deploy Mode

Runs a persistent OpenAI‑compatible vLLM server.

Run from `~/vllm/benchmarks/cpu_binding`.

```bash
MODE=deploy MODEL="Qwen/Qwen2.5-32B-Instruct" PORT=8000 docker compose   -f docker-compose.yml   -f docker-compose.override.yml   --profile deploy up
```

#### Troubleshooting: `docker compose` not available

If you see `docker: unknown command: docker compose` or `unknown shorthand flag: 'f' in -f`, install and use the `docker-compose` binary:

```bash
# check available compose packages
apt-cache search docker-compose | cat

# install distro compose binary
sudo apt install -y docker-compose

# verify
docker-compose --version
```

Then run deploy with:

```bash
MODE=deploy MODEL="Qwen/Qwen2.5-32B-Instruct" PORT=8000 \
docker-compose -f docker-compose.yml -f docker-compose.override.yml --profile deploy up
```

If image extraction fails with `no space left on device`, complete the Docker/containerd move in **Disk Space Management** and retry.

Test:

```bash
curl http://localhost:8000/v1/models
```

---

### Benchmark Mode

Runs the automated benchmark driver.

Run from `~/vllm/benchmarks/cpu_binding`.

```bash
MODE=benchmark docker compose   -f docker-compose.yml   -f docker-compose.override.yml   --profile benchmark up
```

If your system uses `docker-compose` instead of `docker compose`, run:

```bash
MODE=benchmark docker-compose -f docker-compose.yml -f docker-compose.override.yml --profile benchmark up
```

Results:

```bash
benchmarks/results/
```

---

## 3. Reusing Idle CPUs for CPU vLLM

Idle CPUs released from the GPU workload can be reused for CPU inference.

Generate CPU binding including CPU service named as "vllm-cpu-server" provided in docker-compose.cpu.yml:

```bash
python3 generate_cpu_binding_from_csv.py   --settings cpu_binding_gnr.csv   --output docker-compose.override.yml   --cpuservice vllm-cpu-server
```

---

### Running GPU and CPU Together

Both GPU and CPU services can run simultaneously while sharing the same CPU binding policy.

#### Deploy Mode

```bash
MODE=deploy MODEL="meta-llama/Llama-3.1-405B-Instruct" PORT=8000 CPU_MODEL=meta-llama/Llama-3.1-8B-Instruct CPU_PORT=8001 docker compose   -f docker-compose.yml   -f docker-compose.cpu.yml   -f docker-compose.override.yml   --profile deploy up
```

If your system uses `docker-compose` instead of `docker compose`, run:

```bash
MODE=deploy MODEL="meta-llama/Llama-3.1-405B-Instruct" PORT=8000 CPU_MODEL=meta-llama/Llama-3.1-8B-Instruct CPU_PORT=8001 docker-compose -f docker-compose.yml -f docker-compose.cpu.yml -f docker-compose.override.yml --profile deploy up
```

Test:

```bash
curl http://localhost:8000/v1/models
curl http://localhost:8001/v1/models
```

#### Benchmark Mode

```bash
MODE=benchmark docker compose   -f docker-compose.yml   -f docker-compose.cpu.yml   -f docker-compose.override.yml   --profile benchmark up
```

If your system uses `docker-compose` instead of `docker compose`, run:

```bash
MODE=benchmark docker-compose -f docker-compose.yml -f docker-compose.cpu.yml -f docker-compose.override.yml --profile benchmark up
```

Outputs:

```bash
benchmarks/results/
benchmarks/results-cpu/
```

---

### Example: Single-GPU Deploy with CPU Service

```bash
MODE=deploy MODEL="Qwen/Qwen2.5-32B-Instruct" PORT=8000 \
  CPU_MODEL="meta-llama/Llama-3.1-8B-Instruct" CPU_PORT=8001 \
  HF_TOKEN="<your-token>" \
  MODEL_CACHE=/mnt/hf_cache CPU_MODEL_CACHE=/mnt/hf_cache \
  EXTRA_ARGS="--swap-space 16 --tensor-parallel-size 1 --disable-log-stats --gpu-memory-utilization 0.85 --max-model-len 2048" \
  CPU_EXTRA_ARGS="--dtype bfloat16 --distributed-executor-backend mp --block-size 128 --trust-remote-code --enable-chunked-prefill --disable-log-stats --enforce-eager --max-num-batched-tokens 2048 --max-num-seqs 256 --tensor-parallel-size 4" \
  docker compose -f docker-compose.yml -f docker-compose.cpu.yml -f docker-compose.override.yml --profile deploy up -d
```

---

## Key Takeaways

- **docker-compose.override.yml** defines NUMA-aware CPU pinning
- GPU inference uses **closest CPUs and PCT turbo cores**
- CPU inference uses **remaining idle CPUs**
- Both stacks support **deploy and benchmark workflows**
