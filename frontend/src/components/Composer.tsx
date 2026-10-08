import { useState, type KeyboardEvent } from "react";

interface ComposerProps {
  onSend: (prompt: string) => void;
  busy: boolean;
  placeholder?: string;
}

/** Devin-style bottom prompt box: Enter sends, Shift+Enter newline. */
export function Composer({ onSend, busy, placeholder }: ComposerProps) {
  const [value, setValue] = useState("");

  const send = () => {
    const prompt = value.trim();
    if (!prompt || busy) return;
    setValue("");
    onSend(prompt);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 pb-6">
      <div
        className="rounded-xl border p-3 focus-within:border-[#1d4ed8]/70 transition-colors"
        style={{ background: "#161a21", borderColor: "#2a3140" }}
      >
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder={placeholder ?? "Ask Devin to build features, fix bugs, or work on your code"}
          className="w-full bg-transparent outline-none resize-none text-[15px] placeholder:text-neutral-500 text-neutral-100"
        />
        <div className="flex items-center justify-between mt-2 pt-2 border-t" style={{ borderColor: "#232a36" }}>
          <span className="text-[11px] text-neutral-600">
            Enter to send · Shift+Enter for newline
          </span>
          <button
            onClick={send}
            disabled={busy || !value.trim()}
            className="px-4 py-1.5 rounded-lg bg-[#1d4ed8] hover:bg-[#2563eb] disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
          >
            {busy ? "Running…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
