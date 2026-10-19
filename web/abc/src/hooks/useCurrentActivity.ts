import useSWR from "swr";
import { paths, setBinding } from "../api/abc";
import type { Bindings } from "../api/types";

/**
 * The selected activity, stored server-side in the user's bindings so it
 * survives reloads and pre-fills activity_id for queries and operations.
 */
export function useCurrentActivity() {
  const { data, mutate, isLoading } = useSWR<Bindings>(paths.bindings);
  const raw = data?.activity_id ?? null;
  const parsed = raw === null ? NaN : Number(raw);
  const activityId = Number.isInteger(parsed) ? parsed : null;

  async function select(id: number | null): Promise<void> {
    await setBinding("activity_id", id === null ? null : String(id));
    await mutate({ ...(data ?? {}), activity_id: id === null ? null : String(id) });
  }

  return { activityId, select, isLoading };
}
