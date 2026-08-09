// Route registration, one module per file mirroring app/papi/routes/
// in the Python implementation.

import type { App } from "../server";
import { registerAuth } from "./auth";
import { registerOther } from "./other";
import { registerCollections } from "./collections";
import { registerStudies } from "./studies";
import { registerSeries } from "./series";
import { registerFiles } from "./files";
import { registerIECs } from "./iecs";
import { registerDump } from "./dump";
import { registerDownload } from "./download";
import { registerVRStatus } from "./vrstatus";
import { registerDashboard } from "./dashboard";
import { registerROIs } from "./rois";
import { registerImporter } from "./importer";
import { registerSendToPublicStatus } from "./send_to_public_status";
import { registerDicomRoots } from "./dicom_roots";
import { registerWorker } from "./worker";
import { registerPathology } from "./pathology";
import { registerWork } from "./work";
import { registerDeface } from "./deface";
import { registerEdits } from "./edits";
import { registerNifti } from "./nifti";
import { registerSysStatus } from "./sysstatus";
import { registerMasking } from "./masking";
import { registerWadoRS } from "./wadors";
import { registerSegs } from "./segs";
import { registerActivities } from "./activities";
import { registerVisualReviews } from "./visualreviews";
import { registerDocs } from "./docs";

export function registerAll(app: App): void {
  registerDocs(app);
  registerAuth(app);
  registerOther(app);
  registerCollections(app);
  registerStudies(app);
  registerSeries(app);
  registerFiles(app);
  registerIECs(app);
  registerDump(app);
  registerDownload(app);
  registerVRStatus(app);
  registerDashboard(app);
  registerROIs(app);
  registerImporter(app);
  registerSendToPublicStatus(app);
  registerDicomRoots(app);
  registerWorker(app);
  registerPathology(app);
  registerWork(app);
  registerDeface(app);
  registerEdits(app);
  registerNifti(app);
  registerSysStatus(app);
  registerMasking(app);
  registerWadoRS(app);
  registerSegs(app);
  registerActivities(app);
  registerVisualReviews(app);
}
