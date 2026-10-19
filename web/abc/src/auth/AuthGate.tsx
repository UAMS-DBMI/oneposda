import { createContext, useContext, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import useSWR from "swr";
import { ForbiddenError, UnauthorizedError } from "../api/client";
import { paths } from "../api/abc";
import type { Me } from "../api/types";
import { Loading } from "../components/ui";

const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(MeContext);
  if (me === null) throw new Error("useMe used outside AuthGate");
  return me;
}

/** Renders children only for a signed-in user allowed to use ABC. */
export function AuthGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { data, error, isLoading } = useSWR<Me>(paths.me, {
    shouldRetryOnError: false,
  });

  if (isLoading) return <div className="p-4"><Loading /></div>;
  if (error instanceof UnauthorizedError) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (error instanceof ForbiddenError) {
    return (
      <p className="notice notice-danger m-4">
        Your account may not use Activity Based Curation. {error.detail}
      </p>
    );
  }
  if (error || !data) {
    return <p className="notice notice-danger m-4">Could not load your account: {String(error)}</p>;
  }
  return <MeContext.Provider value={data}>{children}</MeContext.Provider>;
}
