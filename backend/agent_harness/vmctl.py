"""Wrapper around the Go `vmm` CLI for VM lifecycle."""

import json
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()

SANDBOX_INFRA = os.environ.get(
    "DEVIN_VMM_DIR", r"C:\projects\devin\backend\sandboxes_infra"
)
VMM_CMD = os.environ.get(
    "DEVIN_VMM_CMD",
    os.path.join(SANDBOX_INFRA, "vmm.exe"),
)


class VMMError(Exception):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            VMM_CMD.split() + args,
            cwd=SANDBOX_INFRA,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as e:
        raise VMMError(f"vmm timed out: {e}") from e


def create_sandbox(socket: str = "/tmp/vm1.socket", tap: str = "tap-vm1",
                   guest_ip: str = "172.16.1.2", host_ip: str = "172.16.1.1",
                   rootfs: str | None = None) -> dict:
    args = ["create", "--socket", socket, "--tap", tap,
            "--guest-ip", guest_ip, "--host-ip", host_ip, "--json"]
    if rootfs:
        args += ["--rootfs", rootfs]
    p = _run(args)
    if p.returncode != 0:
        raise VMMError(p.stderr.strip() or "create failed")
    last = p.stdout.strip().splitlines()[-1]
    return json.loads(last)


def destroy_sandbox(socket: str = "/tmp/vm1.socket", tap: str = "tap-vm1") -> str:
    p = _run(["destroy", "--socket", socket, "--tap", tap])
    if p.returncode != 0:
        raise VMMError(p.stderr.strip() or "destroy failed")
    return p.stdout.strip()


def status_sandbox(socket: str = "/tmp/vm1.socket", guest_ip: str = "172.16.1.2") -> str:
    p = _run(["status", "--socket", socket, "--guest-ip", guest_ip])
    return p.stdout.strip()
