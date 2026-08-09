// Runtime configuration from the environment, mirroring the variables
// used by the Python and Go implementations.

function getenv(key: string, fallback: string): string {
  const v = process.env[key];
  return v !== undefined && v !== "" ? v : fallback;
}

function getenvInt(key: string, fallback: number): number {
  const v = process.env[key];
  if (v === undefined || v === "") return fallback;
  const n = Number.parseInt(v, 10);
  return Number.isNaN(n) ? fallback : n;
}

export interface Config {
  /** Port the HTTP server listens on (API_PORT). */
  apiPort: number;
  /** Externally-visible URL of this API (POSDA_API_URL); embedded in
   * OHIF viewer configs and dicomweb URLs. */
  apiUrl: string;
  /** Hostname of the redis server used for login tokens (POSDA_REDIS_HOST). */
  redisHost: string;
  /** Static token that authenticates as the "system" user
   * (POSDA_API_SYSTEM_TOKEN). */
  systemToken: string;
  /** Where newly imported files are stored (FILE_STORAGE_PATH). */
  fileStoragePath: string;
  /** Where uploads are spooled before being moved into place
   * (TEMP_STORAGE_PATH). */
  tempStoragePath: string;
  /** file_storage_root_id corresponding to fileStoragePath
   * (FILE_STORAGE_ROOT). */
  fileStorageRootId: number;
  /** Script used to render DICOM dumps (see /v1/dump/{file_id}). The
   * default matches the path hard-coded in the Python docker image. */
  dumpScript: string;
}

export function loadConfig(): Config {
  return {
    apiPort: getenvInt("API_PORT", 8087),
    apiUrl: process.env.POSDA_API_URL ?? "",
    redisHost: getenv("POSDA_REDIS_HOST", "redis"),
    systemToken: getenv("POSDA_API_SYSTEM_TOKEN", "nologinallowed"),
    fileStoragePath: getenv("FILE_STORAGE_PATH", "/home/posda/cache/created"),
    tempStoragePath: getenv("TEMP_STORAGE_PATH", "/home/posda/cache/temp"),
    fileStorageRootId: getenvInt("FILE_STORAGE_ROOT", 3),
    dumpScript: getenv("DUMP_SCRIPT", "/fastapi/dump_dicom.sh"),
  };
}
