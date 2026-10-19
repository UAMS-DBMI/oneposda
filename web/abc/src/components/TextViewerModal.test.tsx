import { fireEvent, render, screen } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { swrFetcher } from "../api/client";
import { TextViewerModal } from "./TextViewerModal";

describe("TextViewerModal", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the file text and closes on Escape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ text: "hello report", truncated: false, size: 12 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const onClose = vi.fn();

    render(
      <SWRConfig value={{ fetcher: swrFetcher, provider: () => new Map() }}>
        <TextViewerModal fileId={7} title="Email for 4" onClose={onClose} />
      </SWRConfig>,
    );

    expect(await screen.findByText("hello report")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
