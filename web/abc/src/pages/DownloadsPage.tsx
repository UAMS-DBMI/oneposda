import { useState } from "react";
import useSWR from "swr";
import { deleteDownload, paths } from "../api/abc";
import type { DownloadDir } from "../api/types";
import { formatTimestamp } from "../lib/format";

export function DownloadsPage() {
  const { data, error, mutate } = useSWR<DownloadDir[]>(paths.downloads);
  const [selected, setSelected] = useState<string>("");
  const [failure, setFailure] = useState<string | null>(null);
  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;
  const current = data.find((d) => d.name === selected) ?? data[0];

  async function remove() {
    if (!current) return;
    if (!window.confirm(`Delete the download directory ${current.name}?`)) return;
    setFailure(null);
    try {
      await deleteDownload(current.name);
      setSelected("");
      await mutate();
    } catch (err) {
      setFailure(String(err));
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold">Download</h1>
      {data.length === 0 ? (
        <p className="mt-2 text-sm">There are no directories ready for download</p>
      ) : (
        <div className="mt-2 text-sm">
          <label>
            Select sub directory:{" "}
            <select className="input" value={current?.name ?? ""} onChange={(e) => setSelected(e.target.value)}>
              {data.map((d) => (
                <option key={d.name} value={d.name}>
                  {d.name} ({d.entries} entries, {formatTimestamp(d.modified)})
                </option>
              ))}
            </select>
          </label>
          {current && (
            <p className="mt-3 space-x-2">
              <span>Selected Directory: {current.name}</span>
              <a className="btn-primary" href={paths.downloadTar(current.name)}>Download This Directory as Tar</a>
              <button type="button" className="btn" onClick={remove}>Delete This Directory</button>
            </p>
          )}
          {failure && <p className="mt-2 text-red-700">{failure}</p>}
        </div>
      )}
    </div>
  );
}
