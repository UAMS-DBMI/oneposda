import { useState } from "react";
import useSWR from "swr";
import { deleteDownload, paths } from "../api/abc";
import type { DownloadDir } from "../api/types";
import { EmptyState, ErrorMessage, Loading, PageHeader, errorText } from "../components/ui";
import { formatTimestamp } from "../lib/format";

export function DownloadsPage() {
  const { data, error, mutate } = useSWR<DownloadDir[]>(paths.downloads, { refreshInterval: 30000 });
  const [failure, setFailure] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  async function remove(dir: DownloadDir) {
    if (!window.confirm(`Delete the download directory ${dir.name}? This cannot be undone.`)) return;
    setFailure(null);
    setRemoving(dir.name);
    try {
      await deleteDownload(dir.name);
      await mutate();
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="max-w-4xl">
      <PageHeader title="Download" subtitle="Directories that operations have prepared for you. Each downloads as a tar archive." />
      {error && <ErrorMessage error={error} />}
      {failure && <ErrorMessage>{failure}</ErrorMessage>}
      {!data && !error && <Loading />}
      {data && (
        <div className="table-wrap">
          <table className="table-grid">
            <thead>
              <tr>
                <th>directory</th>
                <th className="num">entries</th>
                <th>modified</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((dir) => (
                <tr key={dir.name}>
                  <td className="font-medium">{dir.name}</td>
                  <td className="num">{dir.entries}</td>
                  <td className="whitespace-nowrap tabular-nums text-slate-600">{formatTimestamp(dir.modified)}</td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    <a className="btn-primary btn-sm" href={paths.downloadTar(dir.name)} title={`Download ${dir.name}.tar`}>
                      Download tar
                    </a>
                    <button type="button" className="btn-danger btn-sm" onClick={() => remove(dir)} disabled={removing === dir.name}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.length === 0 && <EmptyState>There are no directories ready for download.</EmptyState>}
        </div>
      )}
    </div>
  );
}
