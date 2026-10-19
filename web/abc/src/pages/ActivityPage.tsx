import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { paths } from "../api/abc";
import { ApiError } from "../api/client";
import type { Activity, TimelineEvent } from "../api/types";
import { TaskStatusPanel } from "../components/TaskStatusPanel";
import { ThirdPartyControls } from "../components/ThirdPartyControls";
import { TimelineTable } from "../components/TimelineTable";
import { useCurrentActivity } from "../hooks/useCurrentActivity";

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

  if (!Number.isInteger(activityId)) return <p>Bad activity id.</p>;
  if (missing) return <p className="text-gray-500">Activity {activityId} not found…</p>;
  if (error) return <p className="text-red-700">{String(error)}</p>;
  if (!activity) return <p className="text-gray-500">Loading…</p>;

  return (
    <div>
      <div className="flex flex-wrap items-start gap-6">
        <div>
          <h1 className="text-xl font-semibold">
            Activity {activity.activity_id}: {activity.brief_description}
          </h1>
          <ThirdPartyControls activity={activity} onChanged={() => mutate()} />
          <button type="button" className="btn mt-2" onClick={chooseAnother}>
            Choose Another Activity
          </button>
        </div>
        <TaskStatusPanel activityId={activity.activity_id} />
      </div>
      <hr className="my-4" />
      {timeline.error && <p className="text-red-700">{String(timeline.error)}</p>}
      {timeline.data && (
        <TimelineTable events={timeline.data} onRefresh={() => timeline.mutate()} />
      )}
      <p className="mt-3 text-sm">
        <Link to="/activities" className="text-blue-700">
          All activities
        </Link>
      </p>
    </div>
  );
}
