import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type GithubStatus,
  type Health,
  type Task,
  type TaskEvent,
} from "./api";
import { Sidebar } from "./components/Sidebar";
import { Timeline } from "./components/Timeline";
import { Composer } from "./components/Composer";
import { ContextPanel } from "./components/ContextPanel";

const POLL_MS = 2000;
const EVENT_POLL_MS = 1500;

export function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [github, setGithub] = useState<GithubStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

  const refreshTasks = useCallback(async () => {
    try {
      const d = await api.tasks();
      setTasks(d.tasks);
      return d.tasks;
    } catch (e) {
      setBanner(String(e instanceof Error ? e.message : e));
      return null;
    }
  }, []);

  const refreshGithub = useCallback(() => {
    api.githubStatus().then(setGithub).catch(() => setGithub(null));
  }, []);

  // Initial load + GitHub OAuth redirect (?github=connected)
  useEffect(() => {
    refreshTasks().then(list => {
      if (!list?.length) return;
      // Deep link: /?task=<id> selects a session, otherwise open the latest.
      const wanted = new URLSearchParams(window.location.search).get("task");
      const match = wanted ? list.find(t => t.id === wanted) : undefined;
      setSelectedId(match?.id ?? list[0]!.id);
    });
    api.health().then(setHealth).catch(() => setHealth(null));
    refreshGithub();

    const params = new URLSearchParams(window.location.search);
    if (params.has("github")) {
      window.history.replaceState({}, "", window.location.pathname);
      setBanner("GitHub connected.");
      setTimeout(() => setBanner(null), 4000);
    }
  }, [refreshTasks, refreshGithub]);

  // Poll task list (covers status changes for background/other sessions)
  useEffect(() => {
    const t = setInterval(() => refreshTasks(), POLL_MS);
    return () => clearInterval(t);
  }, [refreshTasks]);

  // Poll events for the selected task while it runs
  const selected = tasks.find(t => t.id === selectedId) ?? null;
  const selectedRunning = selected?.status === "working" || selected?.status === "queued";

  useEffect(() => {
    if (!selectedId) {
      setEvents([]);
      return;
    }
    let cancelled = false;
    const load = () => {
      api
        .events(selectedId)
        .then(d => {
          if (!cancelled) setEvents(d.events);
        })
        .catch(() => {});
    };
    load();
    const t = setInterval(load, EVENT_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [selectedId]);

  // Poll health while a task is running so the panel stays fresh
  useEffect(() => {
    if (!selectedRunning) return;
    const t = setInterval(() => {
      api.health().then(setHealth).catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [selectedRunning]);

  // Send a prompt: POST /run blocks server-side until the agent finishes,
  // so we fire it without awaiting and discover the new task via polling.
  const send = useCallback(
    async (prompt: string) => {
      setStarting(true);
      setBanner(null);
      const known = new Set(tasks.map(t => t.id));

      api
        .run(prompt)
        .then(() => refreshTasks())
        .catch(e => setBanner(String(e instanceof Error ? e.message : e)))
        .finally(() => setStarting(false));

      // The task row is created immediately server-side; pick it up on next poll.
      const discover = async () => {
        for (let i = 0; i < 20; i++) {
          await new Promise(r => setTimeout(r, 750));
          const list = await refreshTasks().catch(() => null);
          if (!list) continue;
          const fresh = list.find(t => !known.has(t.id));
          if (fresh) {
            setSelectedId(fresh.id);
            return;
          }
        }
      };
      discover();
    },
    [tasks, refreshTasks],
  );

  const onGithubConnect = useCallback(() => {
    api
      .githubConnect()
      .then(d => {
        window.location.href = d.url;
      })
      .catch(e => setBanner(String(e instanceof Error ? e.message : e)));
  }, []);

  const onGithubDisconnect = useCallback(() => {
    api
      .githubDisconnect()
      .then(() => refreshGithub())
      .catch(e => setBanner(String(e instanceof Error ? e.message : e)));
  }, [refreshGithub]);

  const newSession = useCallback(() => {
    setSelectedId(null);
    setEvents([]);
  }, []);

  const busy = starting || selectedRunning;

  return (
    <div className="h-screen w-screen flex overflow-hidden text-neutral-100" style={{ background: "#0b0e13" }}>
      <Sidebar
        tasks={tasks}
        selectedId={selectedId}
        github={github}
        connected={github?.connected ?? false}
        onSelect={setSelectedId}
        onNewSession={newSession}
        onGithubConnect={onGithubConnect}
      />

      {/* Main column */}
      <main className="flex-1 min-w-0 flex flex-col">
        {/* Header */}
        <header
          className="h-12 shrink-0 px-4 flex items-center gap-3 border-b"
          style={{ background: "#0f1115", borderColor: "#232a36" }}
        >
          <span className="text-sm font-medium truncate">
            {selected ? (selected.prompt.length > 60 ? selected.prompt.slice(0, 60) + "…" : selected.prompt) : "New session"}
          </span>
          {selected && (
            <span
              className={`text-[11px] px-2 py-0.5 rounded-full border ${
                selected.status === "working"
                  ? "border-amber-700 text-amber-300"
                  : selected.status === "completed"
                    ? "border-lime-700 text-lime-300"
                    : selected.status === "failed"
                      ? "border-red-800 text-red-300"
                      : "border-neutral-700 text-neutral-400"
              }`}
            >
              {selected.status}
            </span>
          )}
          <div className="ml-auto flex items-center gap-3 text-[11px] text-neutral-500">
            <span className="hidden sm:inline">{api.base}</span>
            <span className={`w-1.5 h-1.5 rounded-full ${banner?.startsWith("Cannot") ? "bg-red-500" : "bg-lime-400"}`} />
          </div>
        </header>

        {banner && (
          <div className="px-4 py-2 text-[13px] text-amber-200 border-b" style={{ background: "#1c1710", borderColor: "#232a36" }}>
            {banner}
          </div>
        )}

        {/* Body */}
        <div className="flex-1 min-h-0 flex">
          <div className="flex-1 min-w-0 flex flex-col">
            <div className="flex-1 min-h-0 overflow-y-auto">
              {selected ? (
                <Timeline task={selected} events={events} />
              ) : (
                <Welcome onStart={send} busy={starting} />
              )}
            </div>
            <Composer onSend={send} busy={busy} />
          </div>

          <ContextPanel
            health={health}
            github={github}
            onGithubConnect={onGithubConnect}
            onGithubDisconnect={onGithubDisconnect}
          />
        </div>
      </main>
    </div>
  );
}

function Welcome({ onStart, busy }: { onStart: (p: string) => void; busy: boolean }) {
  const suggestions = [
    "Clone my repo and fix the failing tests",
    "Add a dark mode toggle to the settings page",
    "Write unit tests for the payment service",
    "Refactor the API client to use retries",
  ];
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-16 flex flex-col items-center text-center gap-6">
      <span className="w-12 h-12 rounded-xl bg-[#1d4ed8] grid place-items-center text-xl font-bold text-white">D</span>
      <div>
        <h1 className="text-2xl font-semibold">What should Devin work on?</h1>
        <p className="mt-2 text-sm text-neutral-400">
          Describe a task — Devin will plan it, work in a sandbox, and report back.
        </p>
      </div>
      <div className="grid gap-2 w-full">
        {suggestions.map(s => (
          <button
            key={s}
            disabled={busy}
            onClick={() => onStart(s)}
            className="text-left px-4 py-3 rounded-lg border text-sm text-neutral-300 hover:bg-[#161a21] hover:border-[#1d4ed8]/60 transition-colors disabled:opacity-50"
            style={{ background: "#0f1115", borderColor: "#232a36" }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
