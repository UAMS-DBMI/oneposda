import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { swrFetcher } from "../api/client";
import { ActivitiesPage } from "./ActivitiesPage";
import { ActivityPage } from "./ActivityPage";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ActivityPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("clears a dangling activity binding and falls back to the list", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const body = typeof init?.body === "string" ? ` ${init.body}` : "";
        calls.push(`${init?.method ?? "GET"} ${url}${body}`);
        if (url === "/papi/v1/abc/me/bindings") {
          // Arrive after the activity 404, as happens on a direct page load.
          await new Promise((resolve) => setTimeout(resolve, 30));
          return json(200, { activity_id: "42" });
        }
        if (url === "/papi/v1/abc/activities/42") {
          return json(404, { detail: "activity 42 does not exist" });
        }
        if (url === "/papi/v1/abc/activities/42/timeline") return json(200, []);
        if (url.startsWith("/papi/v1/abc/me/bindings/")) {
          return new Response(null, { status: 204 });
        }
        if (url.startsWith("/papi/v1/abc/activities?")) return json(200, []);
        throw new Error(`unexpected request ${url}`);
      }),
    );

    render(
      <SWRConfig value={{ fetcher: swrFetcher, provider: () => new Map() }}>
        <MemoryRouter initialEntries={["/activities/42"]}>
          <Routes>
            <Route path="/activities" element={<ActivitiesPage />} />
            <Route path="/activities/:activityId" element={<ActivityPage />} />
          </Routes>
        </MemoryRouter>
      </SWRConfig>,
    );

    expect(await screen.findByText("Activity 42 no longer exists.")).toBeInTheDocument();
    expect(calls).toContain('PUT /papi/v1/abc/me/bindings/activity_id {"value":null}');
    expect(calls.filter((c) => c.startsWith("PUT"))).toHaveLength(1);
  });
});
