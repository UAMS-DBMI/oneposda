/**
 * Links from result cells to the Mirabelle and Kohlrabi viewers.
 *
 * The Perl GUI opened these in a child window from ``openMirabelle`` and
 * ``openKohlrabi``; the other column button classes were in-process popups
 * and have no equivalent here, so ``viewerUrl`` returns null for them.
 */
import type { ColumnButton } from "../api/types";

type Row = Record<string, unknown>;

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function present(value: unknown): boolean {
  const t = text(value);
  return t !== "" && t.toLowerCase() !== "null";
}

function mirabellePath(cls: string, row: Row): string | null {
  const iec = row.image_equivalence_class_id;
  switch (cls) {
    case "MirabelleMaskIEC":
      return `mask/iec/${text(iec)}`;
    case "MirabelleMaskVR":
      return present(iec)
        ? `mask/vr/${text(row.visual_review_instance_id)}/${text(iec)}`
        : `mask/vr/${text(row.visual_review_instance_id)}`;
    case "MirabelleMaskReviewIEC":
      return `mask/review/iec/${text(iec)}`;
    case "MirabelleMaskReviewVR":
      return present(iec)
        ? `mask/review/vr/${text(row.visual_review_instance_id)}/${text(iec)}`
        : `mask/review/vr/${text(row.visual_review_instance_id)}`;
    case "MirabelleReviewDICOMIEC":
      return `review/dicom/iec/${text(iec)}`;
    case "MirabelleReviewDICOMVR": {
      const status = present(row.review_status) ? text(row.review_status) : "Unreviewed";
      const fileType = present(row.dicom_file_type) ? text(row.dicom_file_type) : "All";
      return `review/dicom/vr/${text(row.id)}/${present(iec) ? text(iec) : "*"}/${status}/${fileType}`;
    }
    case "MirabelleReviewNiftiFile":
      return `review/nifti/file/${text(row.nifti_review_file_id)}`;
    case "MirabelleReviewNiftiVR":
      return present(row.nifti_review_file_id)
        ? `review/nifti/vr/${text(row.nifti_visual_review_instance_id)}/${text(row.nifti_review_file_id)}`
        : `review/nifti/vr/${text(row.nifti_visual_review_instance_id)}`;
    default:
      return null;
  }
}

/** Absolute URL for a viewer button on this row, or null if it is not a viewer. */
export function viewerUrl(button: ColumnButton, row: Row, origin = window.location.origin): string | null {
  if (button.obj === "Posda::PathologyViewer" || button.obj === "PathologyViewerLauncher") {
    const id = row.pathology_visual_review_instance_id;
    return present(id) ? `${origin}/kohlrabi/${text(id)}` : null;
  }
  if (button.obj.startsWith("Mirabelle")) {
    const path = mirabellePath(button.obj, row);
    return path === null ? null : `${origin}/mira/${path}`;
  }
  return null;
}

export function isViewerButton(button: ColumnButton): boolean {
  return (
    button.obj.startsWith("Mirabelle") ||
    button.obj === "Posda::PathologyViewer" ||
    button.obj === "PathologyViewerLauncher"
  );
}
