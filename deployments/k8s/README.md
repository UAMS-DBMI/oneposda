# Posda on Kubernetes (RKE2)

Kustomize-based conversion of `docker-compose.prod.yaml`. The compose file in
the repo root remains the *dev* setup; this directory is the source of truth
for production.

## Architecture decisions

- **No code is baked into images.** The `tcia/posda` image is too large to
  rebuild routinely, so the live code trees are rsynced to the NAS
  (`/nas/public/posda/deploy/`) and mounted into pods, replacing the compose
  bind mounts of the local checkout.
- **`/nas/public` is a real NFS PersistentVolume** (mounted by k8s itself),
  mounted at both `/nas/public` and `/nas/new/public` since they are the same
  export and the database references both.
- **The S3 buckets (rclone/goofys FUSE) stay node-managed.** Each node runs
  systemd units mounting them at the same paths as the old prod host; pods
  get them as `hostPath` volumes with `mountPropagation: HostToContainer`,
  so a host-side remount after a FUSE crash becomes visible to running pods
  (files already open will still error; restart the pod if that happens).
- **The database stays external** (`PGHOST=tcia-posdadb-al.ad.uams.edu` in
  `config/database.env`). No database runs in the cluster.
- **The old `posda_cache_alpine` docker volume** is replaced by
  `/nas/public/posda/k8s-data/legacy-cache`, mounted at `/home/posda/cache`.
  The real cache is `$POSDA_CACHE_ROOT` (already on the NAS); this path only
  needs to hold the `POSDA_VERSION` marker so the image entrypoint skips
  `setup()`.
- **GELF logging is gone.** Kubernetes has no per-container log drivers.
  Install Rancher's Logging app (or a Fluent Bit DaemonSet) with a GELF
  output pointed at tcia-graylog-1 to restore shipping to Graylog.

## One-time setup

### 1. Node prerequisites (every node)

systemd units for the FUSE mounts, at the same paths as the old prod host:

    /nas/posda-archive                    (s3)
    /nas/faspex                           (s3)
    /nas/pathology                        (s3)
    /nas/ross/faspex                      (s3)
    /nas/ross/posda-pathology             (s3)
    /nas/ross/posda-intermediate-archive  (s3)

`/mnt/intake2-data` (the old `POSDA_SUBMISSION_ROOT`) is no longer used and
was intentionally not converted.

The node-level `/nas/public` mount is NOT required (k8s mounts the NFS
export itself), but it does no harm.

### 2. Confirm the hostname

`ingress.yaml`: confirm the hostname (see open questions).

### 3. Stage code and data on the NAS

    /nas/public/posda/deploy/
        posdatools/           <- rsync of posda/posdatools
        lanterna/             <- rsync of lanterna (thumbs.py, magicka.py, ...)
        fastapi-app/          <- rsync of posda/fastapi/app
        steve/                <- rsync of steve
        ream/                 <- rsync of ream
        kaleidoscope-server/  <- rsync of kaleidoscope/kaleidoscope/server
        web/
            posda-error.html
            www/import.html
            www/upload.html
            root-mapping/     <- symlinks: file_storage_root id -> path.
                                 Copy from the prod host, but make sure the
                                 targets are container-valid paths
                                 (e.g. 16 -> /nas/new/public/posda/storage)
    /nas/public/posda/k8s-data/
        legacy-cache/         <- `echo 2 > legacy-cache/POSDA_VERSION`
        kaleidoscope-files/   <- copy contents of the kaleidoscope_files
                                 docker volume from the old prod host

Ownership must match the container users (posda is uid 1000; web runs as
1000:2123).

### 4. Secrets / env files

`config/*.env` are gitignored (they contain credentials). Before building,
copy the real prod env files into `config/`:

    api.env  common.env  database.env  nbia.env  posda.env  ream.env
    posda-old.env   (the export-style copy mounted over posdatools/posda.env)

Also `config/nginx.crt` / `config/nginx.key` for TLS.

`config/default.conf` was taken from `web/default.conf` (dev). **Diff it
against `web/default.conf.prod` on the prod host** and reconcile before go-live.

### 5. Deploy

    kubectl apply -k .
    kubectl apply -f dicom-tcp.yaml   # DICOM port 11112 (kube-system, separate)

Kustomize hashes the generated ConfigMaps/Secrets, so editing an env file or
default.conf and re-applying automatically rolls the affected pods.

## Service map (compose -> k8s)

| compose service          | k8s                                    | notes                              |
|--------------------------|----------------------------------------|------------------------------------|
| db                       | none                                   | external host                      |
| redis                    | Deployment + Service `redis`           | no longer published externally     |
| posda                    | Deployment + Service `posda` (x1)      | DICOM via dicom-tcp.yaml           |
| posda-worker-low         | Deployment (x3)                        | `POSDA_WORKER_PRIORITY=0`          |
| posda-worker-high        | Deployment (x4)                        | `POSDA_WORKER_PRIORITY=1`          |
| posda-fast-file-process  | Deployment (x1)                        |                                    |
| posda-api                | Deployment + Service `posda-api`       |                                    |
| thumbs                   | Deployment (x4)                        |                                    |
| magicka                  | Deployment (x1)                        | was on second prod node            |
| steve                    | Deployment (x1)                        | was on second prod node            |
| ream                     | Deployment (x1)                        | was on second prod node            |
| kaleidoscope             | Deployment (x1), no Service            | writes static files only           |
| web                      | Deployment + Service `web` + Ingress   | TLS at ingress                     |
| exodus                   | not converted                          | wasn't in the required list        |

## Open questions

- **`default.conf.prod`** only exists on the prod host; the ConfigMap
  currently holds the dev version.
- **DNS/hostname**: `POSDA_EXTERNAL_HOSTNAME` is baked into common.env,
  posda.env, and ingress.yaml; all three must agree.
