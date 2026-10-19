import { useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import useSWR from "swr";
import { createActivity, paths } from "../api/abc";
import type { Activity } from "../api/types";
import { Badge, EmptyState, ErrorMessage, Loading, Notice, PageHeader, errorText } from "../components/ui";
import { useCurrentActivity } from "../hooks/useCurrentActivity";
import { formatTimestamp } from "../lib/format";

/** Case-insensitive regex like the Perl filter box; literal on a bad pattern. */
export function matchesFilter(description: string, filter: string): boolean {
  if (!filter) return true;
  try {
    return new RegExp(filter, "i").test(description);
  } catch {
    return description.toLowerCase().includes(filter.toLowerCase());
  }
}

export function ActivitiesPage() {
  const navigate = useNavigate();
  const notice = (useLocation().state as { notice?: string } | null)?.notice;
  const { activityId: currentId, select } = useCurrentActivity();
  const [includeClosed, setIncludeClosed] = useState(false);
  const { data: activities, error, mutate } = useSWR<Activity[]>(paths.activities(includeClosed));
  const [filter, setFilter] = useState("");
  const [description, setDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const visible = useMemo(
    () => (activities ?? []).filter((a) => matchesFilter(a.brief_description, filter)),
    [activities, filter],
  );

  async function choose(id: number) {
    await select(id);
    navigate(`/activities/${id}`);
  }

  async function submitNew(event: FormEvent) {
    event.preventDefault();
    if (!description.trim()) return;
    setCreateError(null);
    try {
      const id = await createActivity(description);
      setDescription("");
      await mutate();
      await choose(id);
    } catch (err) {
      setCreateError(errorText(err));
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        title="Activities"
        subtitle="Choose the activity you are curating. It pre-fills activity_id for every query and operation."
        actions={
          <button type="button" className={showNew ? "btn" : "btn-primary"} onClick={() => setShowNew(!showNew)}>
            {showNew ? "Cancel" : "New activity"}
          </button>
        }
      />
      {notice && <Notice tone="warning">{notice}</Notice>}
      {showNew && (
        <form onSubmit={submitNew} className="card mb-4 flex flex-wrap items-end gap-2">
          <label className="field min-w-0 flex-1">
            <span>Description of the new activity</span>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Collection-X intake, round 2"
              autoFocus
            />
          </label>
          <button type="submit" className="btn-primary" disabled={!description.trim()}>
            Create and select
          </button>
          {createError && <span className="w-full text-sm text-red-700">{createError}</span>}
        </form>
      )}
      <div className="toolbar mb-2">
        <input
          className="input w-72"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by description (regex)"
          aria-label="Filter activities"
          autoFocus={!showNew}
        />
        <label className="flex items-center gap-1 text-slate-600">
          <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} />
          include closed
        </label>
        <span className="ml-auto text-slate-500">
          {visible.length} of {activities?.length ?? 0} activities
        </span>
      </div>
      {error && <ErrorMessage error={error} />}
      {!activities && !error && <Loading />}
      {activities && (
        <div className="table-wrap">
          <table className="table-grid">
            <thead>
              <tr>
                <th className="num">id</th>
                <th>description</th>
                <th>created</th>
                <th>by</th>
                <th>third party</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((activity) => {
                const current = activity.activity_id === currentId;
                return (
                  <tr
                    key={activity.activity_id}
                    className={`row-link ${current ? "is-selected" : ""}`}
                    onClick={() => choose(activity.activity_id)}
                  >
                    <td className="num">{activity.activity_id}</td>
                    <td className="font-medium">
                      {activity.brief_description}
                      {current && <Badge tone="info">selected</Badge>}
                      {activity.when_closed && <Badge tone="neutral">closed</Badge>}
                    </td>
                    <td className="whitespace-nowrap tabular-nums text-slate-600">{formatTimestamp(activity.when_created)}</td>
                    <td className="text-slate-600">{activity.who_created}</td>
                    <td>
                      {activity.third_party_analysis_url && (
                        <a
                          className="link"
                          href={activity.third_party_analysis_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                        >
                          yes
                        </a>
                      )}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          void choose(activity.activity_id);
                        }}
                      >
                        {current ? "Open" : "Select"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {visible.length === 0 && (
            <EmptyState>{filter ? "No activity matches the filter." : "No open activities. Create one above."}</EmptyState>
          )}
        </div>
      )}
    </div>
  );
}
