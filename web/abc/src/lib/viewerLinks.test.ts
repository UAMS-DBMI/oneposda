import { describe, expect, it } from "vitest";
import type { ColumnButton } from "../api/types";
import { isViewerButton, viewerUrl } from "./viewerLinks";

function button(obj: string): ColumnButton {
  return { button_id: "b", caption: "c", column: "x", obj, col_to_param: {}, operation: null };
}

describe("viewerUrl", () => {
  const origin = "https://posda.example";

  it("builds Mirabelle mask and review links like openMirabelle", () => {
    expect(
      viewerUrl(button("MirabelleMaskVR"), { visual_review_instance_id: 5, image_equivalence_class_id: "" }, origin),
    ).toBe("https://posda.example/mira/mask/vr/5");
    expect(
      viewerUrl(button("MirabelleMaskVR"), { visual_review_instance_id: 5, image_equivalence_class_id: 9 }, origin),
    ).toBe("https://posda.example/mira/mask/vr/5/9");
    expect(
      viewerUrl(button("MirabelleReviewDICOMVR"), { id: 3, image_equivalence_class_id: null, review_status: "null" }, origin),
    ).toBe("https://posda.example/mira/review/dicom/vr/3/*/Unreviewed/All");
  });

  it("builds Kohlrabi links and refuses non-viewer buttons", () => {
    expect(
      viewerUrl(button("Posda::PathologyViewer"), { pathology_visual_review_instance_id: 4 }, origin),
    ).toBe("https://posda.example/kohlrabi/4");
    expect(viewerUrl(button("Posda::PopupCompare"), { sop_instance_uid: "1.2" }, origin)).toBeNull();
    expect(isViewerButton(button("Posda::PopupCompare"))).toBe(false);
    expect(isViewerButton(button("MirabelleMaskIEC"))).toBe(true);
  });
});
