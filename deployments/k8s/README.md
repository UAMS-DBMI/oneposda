# Posda on Kubernetes (RKE2)

Kustomize-based conversion of `docker-compose.prod.yaml`. The compose file in
the repo root remains the *dev* setup; this directory is the source of truth
for production.

## Architecture decisions

- **No code is baked into images.** The `tcia/posda` image is too large to
  rebuild routinely. The live code is a blobless partial clone of the oneposda repo
  (`https://code.imphub.org/scm/pt/oneposda.git`, **master = production**)
  on the `posda-deploy` Longhorn RWX PVC, mounted read-only into the pods
  and updated by `jobs/sync-deploy.yaml`. (The pods originally ran code
  straight off the NAS, but its small-file read latency made interpreter
  startup painfully slow. Longhorn RWX is also NFS behind the scenes — a
  share-manager pod exports the volume — but it is cluster-local and much
  faster.)
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
  `/nas/public/posda/k8s/data/legacy-cache`, mounted at `/home/posda/cache`.
  The real cache is `$POSDA_CACHE_ROOT` (already on the NAS); this path only
  needs to hold the `POSDA_VERSION` marker so the image entrypoint skips
  `setup()`.
- **GELF logging is gone.** Kubernetes has no per-container log drivers.
  Install Rancher's Logging app (or a Fluent Bit DaemonSet) with a GELF
  output pointed at tcia-graylog-1 to restore shipping to Graylog.

## Resource requests/limits

Values (2026-07-19) were measured with Rancher Monitoring (Prometheus,
`cattle-monitoring-system`) during a representative ingest: memory requests
near steady-state, memory limits comfortably above the observed working-set
peak (DICOM processing is spiky; an OOM-kill loop mid-ingest is worse than
temporary overuse), CPU requests near sustained (not peak) usage. There are
deliberately **no CPU limits** — throttling would only slow ingests;
requests already guarantee fair shares under contention.

To re-measure after workload changes, run these against Prometheus as
*instant* queries with the lookback window covering the run:

    # peak memory (Mi) per pod -- what limits are judged against
    sort_desc(max by (pod) (max_over_time(
        container_memory_working_set_bytes{namespace="posda", container!=""}[6h]
    )) / 1024 / 1024)

    # sustained CPU (cores) per pod -- basis for requests
    sort_desc(max by (pod) (avg_over_time(
        rate(container_cpu_usage_seconds_total{namespace="posda", container!=""}[5m])[6h:5m]
    )))

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

### 3. Code on the PVC, data on the NAS

Code deploys from git: `jobs/sync-deploy.yaml` clones (or hard-resets) the
oneposda repo's master branch to `oneposda/` on the `posda-deploy` PVC
(a blobless clone — full history and tags, so `git describe --tags` works —
which the Job writes to `posda/posdatools/versionInfo.txt`), and
the pods mount subPaths of that checkout (`posda/posdatools`, `lanterna`,
`steve`, `ream`, `posda/fastapi/app`, `kaleidoscope/kaleidoscope/server`,
`web/...`). To ship code: merge to master, then

    make sync    # re-runs jobs/sync-deploy.yaml and follows its logs

To inspect the PVC by hand, `make debug` drops you into a shell on it
(`make debug-clean` removes the pod).

The `file_storage_root id -> path` mapping lives in the nginx config
(`config/web.conf`) as one `location /files/<id>/` block per root; make
sure the paths are valid inside the web container (e.g. `/files/16/` ->
`/nas/new/public/posda/storage`).

Data dirs stay on the NAS (pods write to them):

    /nas/public/posda/k8s/data/
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

`config/web.conf` was taken from `web/default.conf` (dev). **Diff it
against `web/default.conf.prod` on the prod host** and reconcile before go-live.

### 5. Deploy

    kubectl apply -k .
    make sync                         # seed the code PVC
    kubectl apply -f dicom-tcp.yaml   # DICOM port 11112 (kube-system, separate)

A freshly created `posda-deploy` PVC is empty, so the app pods crash-loop
until the first sync Job finishes; they recover on their next restart.

Kustomize hashes the generated ConfigMaps/Secrets, so editing an env file or
web.conf and re-applying automatically rolls the affected pods.

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
