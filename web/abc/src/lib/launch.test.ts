import { describe, expect, it } from "vitest";
import { expandCommand } from "./launch";

describe("expandCommand", () => {
  it("replaces every occurrence and leaves meta args alone", () => {
    expect(
      expandCommand('Op.pl <?bkgrnd_id?> <activity_id> "<comment>" <activity_id>', {
        activity_id: "7",
        comment: "",
      }),
    ).toBe('Op.pl <?bkgrnd_id?> 7 "" 7');
  });
});
