import { Navigate } from "react-router-dom";
import { useCurrentActivity } from "../hooks/useCurrentActivity";

/** Like the Perl app: land on the selected activity if there is one. */
export function HomeRedirect() {
  const { activityId, isLoading } = useCurrentActivity();
  if (isLoading) return null;
  const to = activityId === null ? "/activities" : `/activities/${activityId}`;
  return <Navigate to={to} replace />;
}
