import type { JSX } from "react";
import { Search, Settings as SettingsIcon } from "lucide-react";
import { Cube, Pill, Kbd } from "../atoms";

interface Props {
  totalCount: number;
  runningCount: number;
  mcpUrl: string | null;
  platform: string | null;
  onCmdK: () => void;
  onSettings: () => void;
}

export function TopBar({ totalCount, runningCount, mcpUrl, platform, onCmdK, onSettings }: Props): JSX.Element {
  const leadingInset = platform === "darwin" ? 72 : 0;
  const captionInset = platform === "win32" ? 148 : 0;

  return (
    <div
      className="drag-region flex items-center gap-3.5 relative flex-shrink-0"
      style={{
        height: 44,
        paddingLeft: 14 + leadingInset,
        paddingRight: 14 + captionInset,
        background: "var(--ph-canvas)",
        borderBottom: "1px solid var(--ph-border-subtle)",
      }}
    >
      {/* Brand — non-interactive decoration: pointer-events:none so the label
          isn't selectable and pointer events fall through to the drag region. */}
      <div className="flex items-center gap-2 pointer-events-none min-w-[154px]">
        <Cube size={22} />
        <span className="font-semibold text-[13px] leading-none tracking-[-0.01em] text-[#e8f0eb] whitespace-nowrap">
          Phantom Browser
        </span>
      </div>

      {/* Search trigger — center, opens command palette */}
      <button
        type="button"
        onClick={onCmdK}
        className="no-drag flex-1 flex items-center gap-2.5 cursor-pointer"
        style={{
          maxWidth: 540,
          margin: "0 auto",
          padding: "6px 12px",
          borderRadius: 6,
          background: "rgba(220,255,232,0.025)",
          boxShadow: "inset 0 0 0 1px rgba(220,255,232,0.07)",
        }}
      >
        <Search size={14} className="text-[#66736b]" />
        <span className="flex-1 text-left text-[13px] text-[#66736b]">
          Search profiles, tags, urls…
        </span>
        <Kbd>⌘ K</Kbd>
      </button>

      {/* Right cluster */}
      <div className="no-drag flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-[11px] text-[#66736b]">
          <span className="mono text-[#a2afa7] text-[12px]">{runningCount}</span>
          <span>running</span>
          <span className="text-slate-600">·</span>
          <span className="mono text-[#a2afa7] text-[12px]">{totalCount}</span>
          <span>total</span>
        </div>
        <Pill kind={mcpUrl ? "running" : "idle"} dot={!!mcpUrl}>
          MCP {mcpUrl ? `· :${new URL(mcpUrl).port}` : "off"}
        </Pill>
        <button
          type="button"
          onClick={onSettings}
          className="w-7 h-7 rounded-md flex items-center justify-center text-[#66736b] hover:bg-[#131a16] hover:text-[#a2afa7] transition-colors"
          aria-label="Settings"
        >
          <SettingsIcon size={14} />
        </button>
      </div>
    </div>
  );
}
