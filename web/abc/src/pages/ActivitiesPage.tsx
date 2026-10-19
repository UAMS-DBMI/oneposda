import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import useSWR from "swr";
import { createActivity, paths } from "../api/abc";
import { ApiError } from "../api/client";
import type { Activity } from "../api/types";
import { useCurrentActivity } from "../hooks/useCurrentActivity";

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
  const { select } = useCurrentActivity();
  const { data: activities, error, mutate } = useSWR<Activity[]>(paths.activities());
  const [filter, setFilter] = useState("");
  const [description, setDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

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
      await createActivity(description);
      setDescription("");
      await mutate();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold">Activities</h1>
      <div className="my-3 flex items-end gap-3">
        <label className="text-sm">
          Filter:{" "}
          <input
            className="input"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="description regex"
          />
        </label>
        <span className="text-sm text-gray-600">
          {visible.length} of {activities?.length ?? 0} open activities
        </span>
      </div>
      {error && <p className="text-red-700">{String(error)}</p>}
      <table className="table-grid max-w-4xl">
        <thead>
          <tr>
            <th>id</th>
            <th>description</th>
            <th>created by</th>
            <th>third party</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {visible.map((activity) => (
            <tr key={activity.activity_id}>
              <td>{activity.activity_id}</td>
              <td>{activity.brief_description}</td>
              <td>{activity.who_created}</td>
              <td>{activity.third_party_analysis_url ? "yes" : ""}</td>
              <td>
                <button
                  type="button"
                  className="btn"
                  onClick={() => choose(activity.activity_id)}
                >
                  select
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <hr className="my-4" />
      <form onSubmit={submitNew} className="flex items-end gap-2">
        <label className="text-sm">
          New activity description:{" "}
          <input
            className="input w-96"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <button type="submit" className="btn-primary" disabled={!description.trim()}>
          Create
        </button>
        {createError && <span className="text-sm text-red-700">{createError}</span>}
      </form>
    </div>
  );
}
