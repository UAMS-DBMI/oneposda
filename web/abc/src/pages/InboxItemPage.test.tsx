import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Linkified } from "./InboxItemPage";

describe("Linkified", () => {
  it("links bare URLs and report anchors but never renders other HTML", () => {
    render(
      <pre>
        <Linkified
          text={'See https://posda.example/x and Report: <a href="/papi/file/11/abc">downloaded_file_11</a> <b>bold</b>'}
        />
      </pre>,
    );
    expect(screen.getByRole("link", { name: "https://posda.example/x" })).toHaveAttribute("href", "https://posda.example/x");
    expect(screen.getByRole("link", { name: "downloaded_file_11" })).toHaveAttribute("href", "/papi/file/11/abc");
    expect(screen.getByText(/<b>bold<\/b>/)).toBeInTheDocument();
  });
});
