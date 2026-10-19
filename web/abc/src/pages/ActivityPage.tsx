import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import { ApiError } from "../api/client";
import type { Activity, TimelineEvent } from "../api/types";
import { TaskStatusPanel } from "../components/TaskStatusPanel";
import { ThirdPartyControls } from "../components/ThirdPartyControls";
import { TimelineTable } from "../components/TimelineTable";
import { ErrorMessage, Loading } from "../components/ui";
import { useCurrentActivity } from "../hooks/useCurrentActivity";
import { formatTimestamp } from "../lib/format";

export function ActivityPage() {
  const navigate = useNavigate();
  const params = useParams<{ activityId: string }>();
  const activityId = Number(params.activityId);
  const { activityId: selectedId, select, isLoading: bindingsLoading } = useCurrentActivity();
  const { data: activity, error, mutate } = useSWR<Activity>(
    Number.isInteger(activityId) ? paths.activity(activityId) : null,
  );
  const timeline = useSWR<TimelineEvent[]>(
    Number.isInteger(activityId) ? paths.timeline(activityId) : null,
    { refreshInterval: 15000 },
  );

  // Opening an activity's URL selects it, as the Perl dropdown did.
  useEffect(() => {
    if (activity && selectedId !== activity.activity_id) {
      void select(activity.activity_id);
    }
  }, [activity, selectedId, select]);

  // A bound activity can vanish (closed, deleted, or a binding copied from
  // another database); drop the binding rather than trapping the user here.
  const missing = error instanceof ApiError && error.status === 404;
  const handledMissing = useRef(false);
  useEffect(() => {
    // Wait for the bindings: on a direct page load the 404 can arrive first,
    // and deciding then would leave the dangling binding in place.
    if (!missing || bindingsLoading || handledMissing.current) return;
    handledMissing.current = true;
    const forget = selectedId === activityId ? select(null) : Promise.resolve();
    void forget.then(() =>
      navigate("/activities", {
        replace: true,
        state: { notice: `Activity ${activityId} no longer exists.` },
      }),
    );
  }, [missing, bindingsLoading, selectedId, activityId, select, navigate]);

  async function chooseAnother() {
    await select(null);
    navigate("/activities");
  }

  if (!Number.isInteger(activityId)) return <ErrorMessage>Bad activity id.</ErrorMessage>;
  if (missing) return <Loading>Activity {activityId} not found…</Loading>;
  if (error) return <ErrorMessage error={error} />;
  if (!activity) return <Loading />;

  return (
    <div>
      <p className="mb-1 text-sm">
        <Link to="/activities" className="link">Activities</Link>
        <span className="mx-1 text-slate-400">/</span>
        <span className="text-slate-600">#{activity.activity_id}</span>
      </p>
      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="card">
          <div className="flex flex-wrap items-start gap-3">
            <div className="min-w-0 flex-1">
              <h1>
                <span className="mr-2 text-slate-400">#{activity.activity_id}</span>
                {activity.brief_description}
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                Created {formatTimestamp(activity.when_created)} by {activity.who_created}
                {activity.when_closed && <> · closed {formatTimestamp(activity.when_closed)}</>}
              </p>
            </div>
            <div className="toolbar">
              <Link to="/workflow" className="btn btn-sm" title="Curation steps for this activity">Workflow</Link>
              <Link to="/queries" className="btn btn-sm">Queries</Link>
              <button type="button" className="btn btn-sm" onClick={chooseAnother}>
                Choose another…
              </button>
            </div>
          </div>
          <ThirdPartyControls activity={activity} onChanged={() => mutate()} />
        </section>
        <TaskStatusPanel activityId={activity.activity_id} />
      </div>
      {timeline.error && <ErrorMessage error={timeline.error} />}
      {timeline.data && (
        <TimelineTable
          events={timeline.data}
          activityId={activity.activity_id}
          onRefresh={() => timeline.mutate()}
        />
      )}
    </div>
  );
}
