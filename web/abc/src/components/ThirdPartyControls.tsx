import { useEffect, useState } from "react";
import { setThirdPartyUrl } from "../api/abc";
import type { Activity } from "../api/types";
import { SegmentedControl } from "./ui";

const CHOICES = [
  { value: "no", label: "No" },
  { value: "yes", label: "Yes" },
] as const;

/** Perl: "Is third party: Yes/No" radios, plus a URL box while Yes. */
export function ThirdPartyControls({
  activity,
  onChanged,
}: {
  activity: Activity;
  onChanged: () => void;
}) {
  const stored = activity.third_party_analysis_url;
  const [isThirdParty, setIsThirdParty] = useState(stored !== null);
  const [url, setUrl] = useState(stored ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsThirdParty(stored !== null);
    setUrl(stored ?? "");
  }, [stored]);

  async function save(value: string | null) {
    setError(null);
    try {
      await setThirdPartyUrl(activity.activity_id, value);
      onChanged();
    } catch (err) {
      setError(String(err));
    }
  }

  function choose(value: "yes" | "no") {
    setIsThirdParty(value === "yes");
    if (value === "no" && stored !== null) void save(null);
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
      <span className="text-slate-600" title="Is this activity a third-party analysis of existing data?">
        Third-party analysis
      </span>
      <SegmentedControl size="sm" label="Third-party analysis" options={CHOICES} value={isThirdParty ? "yes" : "no"} onChange={choose} />
      {isThirdParty && (
        <input
          className="input w-96 max-w-full py-0.5"
          placeholder="analysis URL (saved when you leave the box)"
          aria-label="third party analysis url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onBlur={() => {
            const trimmed = url.trim();
            if (trimmed !== (stored ?? "")) void save(trimmed || null);
          }}
        />
      )}
      {error && <span className="text-red-700">{error}</span>}
    </div>
  );
}
