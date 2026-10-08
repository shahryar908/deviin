"""The LLM tool-use loop with proper handling."""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

import tools
import store

load_dotenv()

MAX_STEPS = int(os.environ.get("DEVIN_MAX_STEPS", "20"))


def _client() -> OpenAI:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return OpenAI(
        api_key=key,
        base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    )


def _model() -> str:
    return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def run(user_prompt: str, task_id: str | None = None) -> str:
    client = _client()
    messages = [
        {
            "role": "system",
            "content": (
                "You are Devin, a coding agent that works inside a Linux microVM sandbox.\n"
                f"Workspace root: {tools.get_cwd()}\n"
                "\n"
                "How to work:\n"
                "- Inspect first: list_dir '.' when you don't know the layout, then read_file the likely entry points.\n"
                "- To work on a repo, call clone_repo, then detect_env, then setup_env, then list_dir/read_file.\n"
                "- A sandbox is usually already running. Only call create_sandbox if envd is unreachable; never boot a second sandbox while one is alive.\n"
                "- Prefer read_file/write_file/list_dir over shell for file work.\n"
                "- Use exec(sh) for builds, installs, tests, git status/diff.\n"
                "- Never read or edit node_modules, .next, dist, target, __pycache__, or vendor trees.\n"
                "- Install dependencies with the repo's package manager before importing them.\n"
                "- Never run unbounded servers in the foreground; use background + logs.\n"
                "- Paths are absolute or relative to the tracked cwd; call set_cwd when you move.\n"
                "\n"
                "Quality bar:\n"
                "- Replace scaffold placeholders with a real, working implementation — no hero-CTA-only pages, no /health-only backends.\n"
                "- Change at least one focused thing per step; verify with a command before finishing.\n"
                "- When satisfied, call finish with a short summary of what you did.\n"
                "\n"
                "Git:\n"
                "- After changing code, call git_commit with a Conventional Commit message:\n"
                "  type(context): lowercase imperative summary, then up to 4 '- ' bullets.\n"
                "  Allowed types: feat, fix, refactor, perf, docs, test, build, ci, chore, style, revert.\n"
                "  Never add Co-authored-by or attribute work to any AI assistant."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    last_call = None
    same_call_count = 0

    for step in range(MAX_STEPS):
        try:
            resp = client.chat.completions.create(
                model=_model(),
                messages=messages,
                tools=tools.TOOL_SCHEMAS,
                timeout=60,
            )
        except Exception as e:
            return f"[agent] LLM call failed at step {step}: {e}"

        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "[agent] no response"

        messages.append(msg)

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": f"error: bad tool args: {e}"}
                )
                continue

            signature = (name, json.dumps(args, sort_keys=True))
            if signature == last_call:
                same_call_count += 1
                if same_call_count >= 3:
                    return f"[agent] aborted: same tool call {name} repeated 3 times"
            else:
                last_call = signature
                same_call_count = 0

            print(f"[tool] {name}({json.dumps(args)[:120]})")
            try:
                result = tools.dispatch(name, args)
            except tools.Finish as f:
                return f.summary
            except tools.ToolError as e:
                result = f"error: {e}"
            if task_id:
                try:
                    store.add_event(task_id, "tool_call", f"{name}({json.dumps(args)[:200]})", {"result": result[:500]})
                except Exception:
                    pass
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return f"[agent] max steps ({MAX_STEPS}) reached"
