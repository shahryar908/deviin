import { useEffect, useState } from "react";
import { api, type GithubStatus, type Health, type Repo } from "../api";

interface ContextPanelProps {
  health: Health | null;
  github: GithubStatus | null;
  onGithubConnect: () => void;
  onGithubDisconnect: () => void;
}

/**
 * Right-hand context panel: sandbox/envd health, GitHub connection + repos.
 * Mirrors Devin's context sidebar.
 */
export function ContextPanel({ health, github, onGithubConnect, onGithubDisconnect }: ContextPanelProps) {
  const [repos, setRepos] = useState<Repo[] | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);

  useEffect(() => {
    if (!github?.connected) {
      setRepos(null);
      setReposError(null);
      return;
    }
    let cancelled = false;
    api
      .githubRepos()
      .then(d => {
        if (!cancelled) setRepos(d.repos);
      })
      .catch(e => {
        if (!cancelled) setReposError(String(e instanceof Error ? e.message : e));
      });
    return () => {
      cancelled = true;
    };
  }, [github?.connected]);

  const envdOk = health?.envd !== undefined && typeof health.envd === "object";

  return (
    <aside
      className="w-72 shrink-0 border-l hidden lg:flex flex-col overflow-y-auto"
      style={{ background: "#0f1115", borderColor: "#232a36" }}
    >
      {/* Sandbox */}
      <section className="p-4 border-b" style={{ borderColor: "#232a36" }}>
        <h3 className="text-[11px] uppercase tracking-wide text-neutral-500 mb-3">Sandbox</h3>
        <Row label="Harness" value={health ? health.harness : "…"} ok={health?.harness === "ok"} />
        <Row label="envd" value={envdOk ? "healthy" : health ? "unavailable" : "…"} ok={envdOk} />
        {health && !envdOk && typeof health.envd === "string" && (
          <pre className="mt-2 text-[11px] text-red-400 whitespace-pre-wrap break-all font-mono">{health.envd}</pre>
        )}
      </section>

      {/* GitHub */}
      <section className="p-4 border-b" style={{ borderColor: "#232a36" }}>
        <h3 className="text-[11px] uppercase tracking-wide text-neutral-500 mb-3">GitHub</h3>
        {github?.connected ? (
          <>
            <Row label="Account" value={github.github_username ?? "connected"} ok />
            <button
              onClick={onGithubDisconnect}
              className="mt-3 w-full rounded-lg py-1.5 text-[13px] border text-neutral-400 hover:text-red-300 hover:border-red-900 transition-colors"
              style={{ borderColor: "#2a3140" }}
            >
              Disconnect
            </button>
            <div className="mt-4 space-y-1.5">
              <div className="text-[11px] uppercase tracking-wide text-neutral-500">Repositories</div>
              {reposError && <div className="text-[12px] text-red-400">{reposError}</div>}
              {!repos && !reposError && <div className="text-[12px] text-neutral-600">Loading…</div>}
              {repos?.slice(0, 12).map(r => (
                <a
                  key={r.id}
                  href={r.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-[13px] text-neutral-300 hover:text-sky-300 truncate"
                >
                  <span className="truncate">{r.full_name}</span>
                  {r.private && <span className="text-[10px] text-neutral-600 shrink-0">priv</span>}
                </a>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="text-[13px] text-neutral-500 mb-3">
              Connect GitHub to let Devin clone repos and open pull requests.
            </p>
            <button
              onClick={onGithubConnect}
              className="w-full rounded-lg py-1.5 text-[13px] font-medium border text-neutral-300 hover:bg-[#1a2030] transition-colors"
              style={{ borderColor: "#2a3140" }}
            >
              Connect GitHub
            </button>
          </>
        )}
      </section>

      <div className="p-4 text-[11px] text-neutral-600">
        Backend: <span className="font-mono">{api.base}</span>
      </div>
    </aside>
  );
}

function Row({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1 text-[13px]">
      <span className="text-neutral-500">{label}</span>
      <span className="flex items-center gap-1.5 text-neutral-300">
        <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-lime-400" : "bg-neutral-600"}`} />
        {value}
      </span>
    </div>
  );
}
