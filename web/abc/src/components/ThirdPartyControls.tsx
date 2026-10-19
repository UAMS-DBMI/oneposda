import { useEffect, useState } from "react";
import { setThirdPartyUrl } from "../api/abc";
import type { Activity } from "../api/types";

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

  function chooseNo() {
    setIsThirdParty(false);
    if (stored !== null) void save(null);
  }

  return (
    <div className="mt-1 text-sm">
      Is third party:{" "}
      <label className="mr-2">
        <input
          type="radio"
          name="third-party"
          checked={isThirdParty}
          onChange={() => setIsThirdParty(true)}
        />{" "}
        Yes
      </label>
      <label>
        <input
          type="radio"
          name="third-party"
          checked={!isThirdParty}
          onChange={chooseNo}
        />{" "}
        No
      </label>
      {isThirdParty && (
        <div className="mt-1">
          third party analysis url:{" "}
          <input
            className="input w-96"
            placeholder="enter url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={() => {
              const trimmed = url.trim();
              if (trimmed !== (stored ?? "")) void save(trimmed || null);
            }}
          />
        </div>
      )}
      {error && <p className="text-red-700">{error}</p>}
    </div>
  );
}
