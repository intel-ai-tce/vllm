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

`lspci` lists the PCIe devices on the VM, including the InfiniBand NIC and GPUs, if any. If `lspci` doesn't return successfully, you may need to install LIS on CentOS/RHEL.

Then run installation commands specific to your distribution.

## Install CUDA drivers on N-series VMs

Reference this guide: [Install GRID drivers on NCv6 RTX PRO 6000 BSE VMs](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/n-series-driver-setup#install-grid-drivers-on-ncv6-rtx-pro-6000-bse-vms).

### Disable Secure Boot and vTPM

Ensure Secure Boot and vTPM are disabled — done via the Azure Portal:

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

#### Ubuntu

Ubuntu packages NVIDIA proprietary drivers. Those drivers come directly from NVIDIA and are simply packaged by Ubuntu so that they can be automatically managed by the system. Downloading and installing drivers from another source can lead to a broken system. Moreover, installing third-party drivers requires extra steps on VMs with TrustedLaunch and Secure Boot enabled. They require the user to add a new Machine Owner Key for the system to boot. Drivers from Ubuntu are signed by Canonical and will work with Secure Boot.

Install the `ubuntu-drivers` utility:

```bash
sudo apt update && sudo apt install -y ubuntu-drivers-common
```

Install the latest NVIDIA drivers:

```bash
sudo ubuntu-drivers install
```

Reboot the VM after the GPU driver is installed:

```bash
sudo reboot
```

After the driver is installed, install the CUDA toolkit (reference):

```bash
sudo apt install -y cuda-toolkit-12-5
```

Download and install the CUDA toolkit from NVIDIA:

> **Note**
> The example shows the CUDA package path for Ubuntu 24.04 LTS. Use the path that's specific to the version you plan to use.
>
> Visit the NVIDIA Download Center or the NVIDIA CUDA Resources page for the full path that's specific to each version.

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo apt install -y ./cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt -y install cuda-toolkit-12-5
```

The installation can take several minutes.

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

This installs Docker, enables it on boot, and adds the user to the `docker` group to avoid needing `sudo` for every `docker` command.

### Verify GPU inside Docker

```bash
sudo docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
```

#### NVIDIA driver updates

We recommend that you periodically update NVIDIA drivers after deployment.

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

After enabling PCT a CPU list file will be generated:

```bash
priority_core_turbo/results/clos0_cpulist.txt
```

This list is used for CPU binding.

---

## 1. Environment Setup

Install the Python venv package:

```bash
sudo apt install python3.12-venv -y
```

Then create and activate the venv:

```bash
python3 -m venv ~/venv
source ~/venv/bin/activate
```

Then install your requirements:

```bash
pip install -r requirements_cpu_binding.txt
pip install regex
```

---

## 2. GPU vLLM Service with CPU Pinning

Generate the CPU binding configuration:

```bash
export MODEL="Qwen/Qwen2.5-32B-Instruct"
export HF_TOKEN="<your huggingface token>"

python3 generate_cpu_binding_from_csv.py   --settings cpu_binding_gnr.csv   --output docker-compose.override.yml
```

This generates a **docker-compose.override.yml** containing cpuset rules using lookup table
inside the cpu_binding_gnr.csv file.

All **deploy** and **benchmark** runs should include this override file.

---

### Deploy Mode

Runs a persistent OpenAI‑compatible vLLM server.

```bash
MODE=deploy MODEL="Qwen/Qwen2.5-32B-Instruct" PORT=8000 docker compose   -f docker-compose.yml   -f docker-compose.override.yml   --profile deploy up
```

Test:

```bash
curl http://localhost:8000/v1/models
```

---

### Benchmark Mode

Runs the automated benchmark driver.

```bash
MODE=benchmark docker compose   -f docker-compose.yml   -f docker-compose.override.yml   --profile benchmark up
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

Test:

```bash
curl http://localhost:8000/v1/models
curl http://localhost:8001/v1/models
```

#### Benchmark Mode

```bash
MODE=benchmark docker compose   -f docker-compose.yml   -f docker-compose.cpu.yml   -f docker-compose.override.yml   --profile benchmark up
```

Outputs:

```bash
benchmarks/results/
benchmarks/results-cpu/
```

---

## Key Takeaways

- **docker-compose.override.yml** defines NUMA-aware CPU pinning
- GPU inference uses **closest CPUs and PCT turbo cores**
- CPU inference uses **remaining idle CPUs**
- Both stacks support **deploy and benchmark workflows**
