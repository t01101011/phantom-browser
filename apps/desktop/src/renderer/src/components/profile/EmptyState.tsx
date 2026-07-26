import type { JSX } from "react";
import { Boxes } from "lucide-react";
import { Kbd } from "../atoms";

interface Props {
  onCreate: () => void;
}

export function ProfilesEmptyState({ onCreate }: Props): JSX.Element {
  return (
    <div className="flex-1 flex items-center justify-center" style={{ padding: 48 }}>
      <div
        className="phantom-empty-state text-center"
      >
        <div
          className="mx-auto flex items-center justify-center"
          style={{
            width: 48,
            height: 48,
            borderRadius: 12,
            background: "rgba(66,245,141,0.10)",
            color: "#42f58d",
            boxShadow: "inset 0 0 0 1px rgba(66,245,141,0.2)",
          }}
        >
          <Boxes size={22} strokeWidth={1.5} />
        </div>
        <div className="text-[14px] font-semibold text-slate-100 mt-3.5">No profiles yet</div>
        <div className="text-[12px] text-slate-500 mt-1.5 leading-relaxed">
          Each profile is its own browser — cookies, login, fingerprint, proxy. Create one to get started.
        </div>
        <div className="flex items-center justify-center gap-2 mt-4">
          <button
            type="button"
            onClick={onCreate}
            className="btn-brand text-[12px] px-3.5 py-2 rounded-[10px]"
          >
            New profile
          </button>
          <Kbd>⌘ N</Kbd>
        </div>
      </div>
    </div>
  );
}
