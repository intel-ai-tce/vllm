# SPDX-License-Identifier: Apache-2.0

"""CPU ISA / AMX policy helpers.

This wraps PyTorch's AMX tile capability probe and adds a vLLM-wide policy
switch via the VLLM_CPU_AMX environment variable.

VLLM_CPU_AMX values:
  - auto (default): use PyTorch capability check
  - off / 0 / false / disable / no: disable AMX globally
  - on / 1 / true / enable: allow AMX when HW/OS support it

Note: this does not force AMX execution on unsupported systems; it only
controls whether vLLM is allowed to use AMX code paths.
"""

from __future__ import annotations

import os

import torch


def _normalize(val: str | None) -> str:
    return (val or "").strip().lower()


def is_amx_tile_supported() -> bool:
    """Return True if AMX tile is supported and allowed by vLLM policy."""
    policy = _normalize(os.getenv("VLLM_CPU_AMX", "auto"))
    if policy in ("off", "0", "false", "disable", "no"):
        return False

    hw_supported = torch._C._cpu._is_amx_tile_supported()

    if policy in ("on", "1", "true", "enable"):
        # Still require HW/OS support for safety.
        return hw_supported

    # auto (default)
    return hw_supported
