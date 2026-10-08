/**
 * Typed client for the agent harness backend (FastAPI, port 8787).
 * The backend is owned by ../backend/agent_harness — never modified here.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env?.BUN_PUBLIC_API_BASE) ||
  "http://localhost:8787";

export type TaskStatus = "queued" | "working" | "completed" | "failed";

export interface Task {
  id: string;
  prompt: string;
  status: TaskStatus;
  result: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
}

export interface TaskEvent {
  id: number;
  task_id: string;
  type: string; // task_created | tool_call | task_completed | task_failed
  message: string;
  meta: string | null; // JSON string, e.g. {"result": "..."}
  created_at: number;
}

export interface GithubStatus {
  connected: boolean;
  github_username: string | null;
  scopes?: string;
}

export interface Repo {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
  description?: string | null;
  language?: string | null;
}

export interface Health {
  harness: string;
  envd: unknown; // sandbox /health payload or an error string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (e) {
    throw new ApiError(0, `Cannot reach harness at ${API_BASE} (${String(e)})`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  base: API_BASE,

  health: () => request<Health>("/health"),

  tasks: (limit = 50) => request<{ tasks: Task[] }>(`/tasks?limit=${limit}`),

  events: (taskId: string) =>
    request<{ events: TaskEvent[] }>(`/tasks/${taskId}/events`),

  /**
   * POST /run blocks until the agent loop finishes (potentially minutes),
   * so callers should not await it for UI state — poll /tasks instead.
   */
  run: (prompt: string) =>
    request<{ task_id?: string; result?: string; error?: string }>("/run", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),

  githubStatus: () => request<GithubStatus>("/github/status"),
  githubConnect: () => request<{ url: string }>("/github/connect"),
  githubDisconnect: () => request<{ deleted: boolean }>("/github/disconnect", { method: "DELETE" }),
  githubRepos: () => request<{ repos: Repo[] }>("/github/repos"),
};

/** Event types emitted by the harness, in display groups. */
export const EVENT_ICONS: Record<string, string> = {
  task_created: "◆",
  tool_call: "›",
  task_completed: "✓",
  task_failed: "✕",
};
