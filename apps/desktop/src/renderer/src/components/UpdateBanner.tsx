import { useEffect, useState, type JSX, type ReactNode } from "react";
import { Download, RefreshCw, X } from "lucide-react";
import type { UpdateStatus } from "../types";

/**
 * Full-width, non-intrusive update bar shown under the TopBar. Only renders for
 * actionable states:
 *   - `ready`       (Windows/Linux) → "Restart to update" / Later
 *   - `available`   (macOS, terminal) → "Download" / Dismiss
 *   - `downloading` → slim progress, not dismissible
 * Everything else (idle/checking/up-to-date/error) is surfaced in Settings, not
 * here, to keep the bar quiet. Dismiss hides the current state for this launch;
 * a new version (different key) re-shows it.
 *
 * `suppressed` lets the host hide the bar while the first-run Chromium bootstrap
 * modal is up, so the two never compete.
 */
export function UpdateBanner({ suppressed }: { suppressed?: boolean }): JSX.Element | null {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!window.multizen) return;
    void window.multizen.update.status().then(setStatus);
    return window.multizen.update.onStatus(setStatus);
  }, []);

  if (suppressed || !status) return null;

  const version = "version" in status ? status.version : "";
  const key = `${status.kind}:${version}`;
  if (dismissedKey === key) return null;

  if (status.kind === "downloading") {
    return (
      <Bar tone="info">
        <RefreshCw size={13} className="animate-spin text-[#6dffa7] shrink-0" />
        <span>Downloading Phantom Browser {version}…</span>
        <span className="mono text-[11px] text-slate-400">{status.percent}%</span>
        <div className="flex-1" />
      </Bar>
    );
  }

  if (status.kind === "ready") {
    return (
      <Bar tone="brand">
        <Download size={13} className="text-[#6dffa7] shrink-0" />
        <span>
          Phantom Browser <b className="font-semibold">{version}</b> is ready to install.
        </span>
        <div className="flex-1" />
        <BannerButton primary onClick={() => void window.multizen.update.install()}>
          Restart now
        </BannerButton>
        <BannerButton onClick={() => setDismissedKey(key)}>Later</BannerButton>
      </Bar>
    );
  }

  if (status.kind === "available") {
    // macOS-only terminal state (no in-app install possible).
    return (
      <Bar tone="brand">
        <Download size={13} className="text-[#6dffa7] shrink-0" />
        <span>
          Phantom Browser <b className="font-semibold">{version}</b> is available.
        </span>
        <div className="flex-1" />
        <BannerButton primary onClick={() => void window.multizen.update.download(version)}>
          Download
        </BannerButton>
        <BannerButton aria-label="Dismiss" onClick={() => setDismissedKey(key)}>
          <X size={13} />
        </BannerButton>
      </Bar>
    );
  }

  return null;
}

function Bar({ children, tone }: { children: ReactNode; tone: "brand" | "info" }): JSX.Element {
  return (
    <div
      className={`phantom-update-banner flex items-center gap-2.5 px-4 py-2 text-[12px] text-slate-200 ${tone === "brand" ? "phantom-update-banner-brand" : ""}`}
    >
      {children}
    </div>
  );
}

function BannerButton({
  children,
  primary,
  onClick,
  ...rest
}: {
  children: ReactNode;
  primary?: boolean;
  onClick: () => void;
} & React.ButtonHTMLAttributes<HTMLButtonElement>): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        primary
          ? "px-2.5 h-7 rounded-md text-[12px] font-medium text-white"
          : "px-2 h-7 rounded-md text-[12px] text-slate-300 hover:text-slate-100"
      }
      style={
        primary
          ? { background: "var(--ph-primary)", color: "#07110b" }
          : { boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.12)" }
      }
      {...rest}
    >
      {children}
    </button>
  );
}
