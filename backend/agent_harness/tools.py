"""Agent-facing tools: JSON schemas + dispatch."""

import json
from typing import Any

import sandbox
import vmctl

_IMAGES = {
    "node": "/home/shahryar/firecracker-lab/rootfs/base-dev.ext4",
    "python": "/home/shahryar/firecracker-lab/rootfs/base-dev.ext4",
    "go": "/home/shahryar/firecracker-lab/rootfs/base-dev.ext4",
    "rust": "/home/shahryar/firecracker-lab/rootfs/base-dev.ext4",
    "default": "/home/shahryar/firecracker-lab/rootfs/base-dev.ext4",
}

_state: dict[str, Any] = {"cwd": "/", "history": [], "env": None}


class ToolError(Exception):
    pass


class Finish(Exception):
    def __init__(self, summary: str):
        self.summary = summary


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_sandbox",
            "description": "Boot a fresh Firecracker sandbox and point the harness at it. Pass stack=node|python|go|rust|default to pick a pre-baked image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_ip": {"type": "string"},
                    "rootfs": {"type": "string"},
                    "stack": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "destroy_sandbox",
            "description": "Tear down the running sandbox.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_status",
            "description": "Report sandbox VM/envd status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": "Run code in the sandbox. language: sh|python|node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "enum": ["sh", "python", "node"]},
                    "code": {"type": "string"},
                    "timeout_ms": {"type": "integer"},
                },
                "required": ["language", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Run a shell command (string) in the sandbox cwd. Equivalent to exec with language='sh'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_ms": {"type": "integer"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the sandbox filesystem (path relative to cwd if not absolute).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files in a sandbox directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_cwd",
            "description": "Set the working directory used for relative paths and sh exec.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "history",
            "description": "Show the commands run in this session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clone_repo",
            "description": "Clone a git repo into /workspace/repo in the sandbox and switch cwd to it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "branch": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_env",
            "description": "Detect the repo stack/language from manifest files in the current cwd.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "setup_env",
            "description": "Run the detected setup commands for the repo (install dependencies, etc.).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Commit tracked changes with a Conventional Commit message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "End the task and give the user a summary.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


def _record(entry: str) -> None:
    _state["history"].append(entry)


def get_cwd() -> str:
    return _state["cwd"]


def _resolve(path: str) -> str:
    if path.startswith("/"):
        return path
    return f"{_state['cwd'].rstrip('/')}/{path}"


def dispatch(name: str, args: dict[str, Any]) -> str:
    try:
        if name == "create_sandbox":
            # Reuse a healthy running sandbox if one exists; never boot a second
            # VM on top of the same tap device.
            for candidate in [args.get("guest_ip"), "172.16.1.2"]:
                if not candidate:
                    continue
                sandbox.set_envd_url(f"http://{candidate}:8080")
                try:
                    sandbox.health()
                    return json.dumps({"guest_ip": candidate, "status": "reused existing sandbox"})
                except Exception:
                    continue
            stack = args.get("stack")
            if not stack and _state.get("env"):
                stack = _state["env"].get("stack")
            rootfs = args.get("rootfs") or _IMAGES.get(stack or "default", _IMAGES["default"])
            info = vmctl.create_sandbox(guest_ip=args.get("guest_ip", "172.16.1.2"),
                                        rootfs=rootfs)
            sandbox.set_envd_url(f"http://{info['guest_ip']}:8080")
            _state["cwd"] = "/"
            return json.dumps(info)
        if name == "destroy_sandbox":
            return vmctl.destroy_sandbox()
        if name == "sandbox_status":
            return vmctl.status_sandbox()
        if name == "shell":
            a = dict(args)
            a.setdefault("language", "sh")
            a["code"] = a.pop("command", a.get("code", ""))
            return dispatch("exec", a)
        if name == "exec":
            # Be tolerant of models that pass cmd= or -c style args.
            if "code" not in args and "cmd" in args:
                cmd = args.pop("cmd")
                if isinstance(cmd, list):
                    args["code"] = " ".join(str(p) for p in cmd)
                else:
                    args["code"] = str(cmd)
                args.setdefault("language", "sh")
            lang, code = args["language"], args["code"]
            if lang == "sh":
                code = f"cd {_state['cwd']} && {code}"
            res = sandbox.execute(lang, code, args.get("timeout_ms"))
            _record(f"{lang}: {code[:80]!r} -> exit {res.get('exit_code')}")
            return json.dumps(res)
        if name == "read_file":
            return sandbox.read_file(_resolve(args["path"]))
        if name == "write_file":
            sandbox.write_file(_resolve(args["path"]), args["content"])
            return f"wrote {_resolve(args['path'])}"
        if name == "list_dir":
            return sandbox.list_dir(_resolve(args.get("path", ".")))
        if name == "set_cwd":
            _state["cwd"] = _resolve(args["path"])
            return f"cwd={_state['cwd']}"
        if name == "clone_repo":
            import shlex
            url = args["url"]
            branch = args.get("branch")
            cmd = f"rm -rf /workspace/repo && mkdir -p /workspace && git clone --depth 1 {shlex.quote(url)} /workspace/repo"
            if branch:
                cmd += f" --branch {shlex.quote(branch)}"
            res = sandbox.execute("sh", cmd, timeout_ms=120000)
            _record(f"clone_repo: {url} -> exit {res.get('exit_code')}")
            if res.get("exit_code") == 0:
                _state["cwd"] = "/workspace/repo"
                _state["env"] = None
            return json.dumps(res)
        if name == "detect_env":
            detect = (
                f"cd {_state['cwd']} && for f in package.json go.mod pyproject.toml requirements.txt Cargo.toml Dockerfile README.md; do "
                "[ -e \"$f\" ] && echo \"FOUND:$f\"; done"
            )
            res = sandbox.execute("sh", detect)
            found = {line.split(":", 1)[1] for line in (res.get("stdout") or "").splitlines() if line.startswith("FOUND:")}
            stack = "unknown"
            steps: list[str] = []
            if "package.json" in found:
                stack = "node"
                steps = ["npm ci || npm install"]
            elif "go.mod" in found:
                stack = "go"
                steps = ["go mod download"]
            elif "requirements.txt" in found:
                stack = "python"
                steps = ["pip install -r requirements.txt"]
            elif "pyproject.toml" in found:
                stack = "python"
                steps = ["pip install -e ."]
            elif "Cargo.toml" in found:
                stack = "rust"
                steps = ["cargo fetch"]
            _state["env"] = {"stack": stack, "setup_steps": steps, "files": sorted(found)}
            _record(f"detect_env: {stack} ({len(found)} manifests)")
            return json.dumps(_state["env"])
        if name == "setup_env":
            env = _state.get("env")
            if not env:
                return "error: run detect_env first"
            results = []
            for step in env["setup_steps"]:
                res = sandbox.execute("sh", f"cd {_state['cwd']} && {step}", timeout_ms=300000)
                _record(f"setup: {step} -> exit {res.get('exit_code')}")
                results.append({"step": step, "exit_code": res.get("exit_code"),
                                "stdout": (res.get("stdout") or "")[-500:],
                                "stderr": (res.get("stderr") or "")[-500:]})
            return json.dumps(results)
        if name == "git_commit":
            import shlex
            paths = args.get("paths") or ["."]
            path_args = " ".join(shlex.quote(p) for p in paths)
            code = (
                f"cd {_state['cwd']} && git add {path_args} && "
                f"git commit -m {shlex.quote(args['message'])}"
            )
            res = sandbox.execute("sh", code)
            _record(f"git_commit: {args['message'][:60]!r} -> exit {res.get('exit_code')}")
            return json.dumps(res)
        if name == "history":
            return "\n".join(_state["history"]) or "(no commands yet)"
        if name == "finish":
            raise Finish(args["summary"])
        raise ToolError(f"unknown tool: {name}")
    except vmctl.VMMError as e:
        raise ToolError(str(e))
    except (ToolError, Finish):
        raise
    except Exception as e:
        raise ToolError(str(e))
