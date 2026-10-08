import type { GithubStatus, Task, TaskStatus } from "../api";

const STATUS_DOT: Record<TaskStatus, string> = {
  queued: "bg-neutral-500",
  working: "bg-amber-400 animate-pulse",
  completed: "bg-lime-400",
  failed: "bg-red-400",
};

const STATUS_LABEL: Record<TaskStatus, string> = {
  queued: "Queued",
  working: "Working",
  completed: "Done",
  failed: "Failed",
};

export function statusDot(status: TaskStatus) {
  return STATUS_DOT[status] ?? "bg-neutral-500";
}

export function statusLabel(status: TaskStatus) {
  return STATUS_LABEL[status] ?? status;
}

function timeAgo(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

interface SidebarProps {
  tasks: Task[];
  selectedId: string | null;
  github: GithubStatus | null;
  connected: boolean;
  onSelect: (id: string) => void;
  onNewSession: () => void;
  onGithubConnect: () => void;
}

export function Sidebar({
  tasks,
  selectedId,
  github,
  connected,
  onSelect,
  onNewSession,
  onGithubConnect,
}: SidebarProps) {
  return (
    <aside className="w-64 shrink-0 border-r flex flex-col" style={{ background: "#0f1115", borderColor: "#232a36" }}>
      {/* Brand */}
      <div className="h-12 px-4 flex items-center gap-2 border-b" style={{ borderColor: "#232a36" }}>
        <span className="w-6 h-6 rounded bg-[#1d4ed8] inline-grid place-items-center text-[11px] font-bold text-white">D</span>
        <span className="font-semibold text-sm tracking-tight">Devin</span>
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded border text-neutral-400" style={{ borderColor: "#232a36" }}>
          local
        </span>
      </div>

      {/* New session */}
      <div className="p-3">
        <button
          onClick={onNewSession}
          className="w-full rounded-lg py-2 flex items-center justify-center gap-2 text-sm font-medium border transition-colors hover:bg-[#1a2030]"
          style={{ background: "#161a21", borderColor: "#2a3140" }}
        >
          <span className="text-neutral-400">＋</span> New session
        </button>
      </div>

      {/* Sessions */}
      <div className="px-4 pt-2 pb-1 text-[11px] uppercase tracking-wide text-neutral-500">Sessions</div>
      <nav className="flex-1 overflow-y-auto px-2 space-y-0.5 pb-3">
        {tasks.length === 0 && (
          <div className="px-2 py-3 text-xs text-neutral-500">No sessions yet — start one below.</div>
        )}
        {tasks.map(t => (
          <button
            key={t.id}
            onClick={() => onSelect(t.id)}
            className={`w-full text-left px-2 py-2 rounded-md group transition-colors ${
              selectedId === t.id ? "bg-[#1a2030]" : "hover:bg-[#141922]"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusDot(t.status)}`} />
              <span className="text-[13px] truncate flex-1 text-neutral-200">
                {t.prompt.length > 44 ? t.prompt.slice(0, 44) + "…" : t.prompt}
              </span>
            </div>
            <div className="mt-0.5 pl-3.5 text-[11px] text-neutral-500 flex items-center gap-1.5">
              <span className={t.status === "failed" ? "text-red-400" : ""}>{statusLabel(t.status)}</span>
              <span>·</span>
              <span>{timeAgo(t.created_at)}</span>
            </div>
          </button>
        ))}
      </nav>

      {/* GitHub */}
      <div className="p-3 border-t" style={{ borderColor: "#232a36" }}>
        {connected && github?.connected ? (
          <div className="flex items-center gap-2 text-[13px] text-neutral-300">
            <svg viewBox="0 0 16 16" className="w-4 h-4 fill-current"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" /></svg>
            <span className="truncate">{github.github_username ?? "connected"}</span>
            <span className="ml-auto w-1.5 h-1.5 rounded-full bg-lime-400" />
          </div>
        ) : (
          <button
            onClick={onGithubConnect}
            className="w-full rounded-lg py-2 text-[13px] font-medium border text-neutral-300 transition-colors hover:bg-[#1a2030]"
            style={{ background: "#161a21", borderColor: "#2a3140" }}
          >
            Connect GitHub
          </button>
        )}
      </div>
    </aside>
  );
}
