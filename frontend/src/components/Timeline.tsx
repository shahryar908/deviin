import { useEffect, useRef } from "react";
import type { Task, TaskEvent } from "../api";

/** Parse `name({...})` tool_call messages into a name + pretty args. */
function parseToolCall(message: string): { name: string; args: string } {
  const m = /^([a-z_]+)\((.*)\)$/s.exec(message.trim());
  if (!m) return { name: "tool", args: message };
  const name = m[1] ?? "tool";
  const rawArgs = m[2] ?? "";
  try {
    return { name, args: JSON.stringify(JSON.parse(rawArgs), null, 2) };
  } catch {
    // Harness truncates args at 200 chars, so JSON is often cut mid-object.
    return { name, args: rawArgs };
  }
}

function metaResult(event: TaskEvent): string | null {
  if (!event.meta) return null;
  try {
    const parsed = JSON.parse(event.meta) as { result?: string };
    return parsed.result ?? null;
  } catch {
    return event.meta;
  }
}

function clock(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface TimelineProps {
  task: Task;
  events: TaskEvent[];
}

/**
 * Devin-style session view: prompt at top, agent steps in the middle
 * (expandable tool calls), final answer / error at the bottom.
 */
export function Timeline({ task, events }: TimelineProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const stepCount = events.filter(e => e.type === "tool_call").length;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length, task.status]);

  const toolEvents = events.filter(e => e.type !== "task_created");

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-6 flex flex-col gap-5">
      {/* User prompt */}
      <div className="flex gap-3">
        <div className="w-7 h-7 shrink-0 rounded-md bg-[#2a3140] grid place-items-center text-[11px] font-semibold text-neutral-300">
          You
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] text-neutral-500 mb-1">Session started · {clock(task.created_at)}</div>
          <div className="text-[15px] leading-relaxed whitespace-pre-wrap break-words text-neutral-100">
            {task.prompt}
          </div>
        </div>
      </div>

      {/* Plan / step counter */}
      {stepCount > 0 && (
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-neutral-500">
          <span>Plan</span>
          <span className="h-px flex-1" style={{ background: "#232a36" }} />
          <span>{stepCount} step{stepCount === 1 ? "" : "s"}</span>
        </div>
      )}

      {/* Agent steps */}
      {toolEvents.map(ev => {
        if (ev.type === "tool_call") {
          const { name, args } = parseToolCall(ev.message);
          const result = metaResult(ev);
          return <StepCard key={ev.id} name={name} args={args} result={result} ts={ev.created_at} />;
        }
        if (ev.type === "task_completed" || ev.type === "task_failed") {
          return null; // final answer rendered from task.result / task.error below
        }
        return (
          <div key={ev.id} className="text-[13px] text-neutral-500">
            {ev.message}
          </div>
        );
      })}

      {/* Live status */}
      {(task.status === "working" || task.status === "queued") && (
        <div className="flex items-center gap-2.5 text-[13px] text-amber-300/90">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          {task.status === "queued" ? "Waiting for the sandbox…" : "Devin is working…"}
        </div>
      )}

      {/* Final answer */}
      {task.status === "completed" && task.result && (
        <div className="flex gap-3">
          <div className="w-7 h-7 shrink-0 rounded-md bg-[#1d4ed8] grid place-items-center text-[11px] font-bold text-white">
            D
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] text-neutral-500 mb-1">Devin · {clock(task.updated_at)}</div>
            <div className="text-[15px] leading-relaxed whitespace-pre-wrap break-words text-neutral-100">
              {task.result}
            </div>
          </div>
        </div>
      )}

      {task.status === "failed" && (
        <div
          className="rounded-lg border p-3 text-[13px] whitespace-pre-wrap break-words"
          style={{ borderColor: "#7f1d1d", background: "#1a1010", color: "#fca5a5" }}
        >
          {task.error ?? "Task failed."}
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}

interface StepCardProps {
  name: string;
  args: string;
  result: string | null;
  ts: number;
}

function StepCard({ name, args, result, ts }: StepCardProps) {
  return (
    <details className="group rounded-lg border" style={{ background: "#12151c", borderColor: "#232a36" }}>
      <summary className="cursor-pointer list-none px-3 py-2.5 flex items-center gap-2.5 hover:bg-[#161a21] rounded-lg">
        <span className="text-neutral-500 text-xs transition-transform group-open:rotate-90">›</span>
        <code className="text-[13px] text-sky-300 font-medium">{name}</code>
        <span className="text-[12px] text-neutral-500 truncate flex-1 font-mono">{args.replace(/\s+/g, " ").slice(0, 90)}</span>
        <span className="text-[11px] text-neutral-600 shrink-0">{clock(ts)}</span>
      </summary>
      <div className="px-3 pb-3 pt-1 space-y-2 border-t" style={{ borderColor: "#1c2230" }}>
        <pre className="text-[12px] text-neutral-400 whitespace-pre-wrap break-all font-mono mt-2">{args}</pre>
        {result && (
          <pre
            className="text-[12px] whitespace-pre-wrap break-all font-mono rounded p-2 max-h-64 overflow-y-auto"
            style={{ background: "#0b0e13", color: "#a3e635" }}
          >
            {result}
          </pre>
        )}
      </div>
    </details>
  );
}
