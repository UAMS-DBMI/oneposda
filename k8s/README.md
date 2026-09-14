# Ingest pipeline on Kubernetes

The DICOM ingest pipeline runs as three independently scaled Deployments,
one process per pod:

| Deployment | Role | Replicas |
|---|---|---|
| `posda-ingest-daemon` | Fills the Redis `files` list from the database | **exactly 1** |
| `posda-ingest-file-worker` | Parses and imports each file | scale freely |
| `posda-ingest-pixel-worker` | Records where the pixel data lives | scale freely |

They coordinate only through Redis: the daemon LPUSHes onto `files`, file
workers BRPOP it and RPUSH onto `pixel_location`, pixel workers BRPOP that.
No tier knows how many of any other there are, so scaling is just:

```sh
kubectl scale deploy/posda-ingest-file-worker --replicas=20
```

## Applying

```sh
kubectl apply -f k8s/
```

Before you do, edit `ingest-config.yaml`: `PGHOST`, `PGUSER` and
`POSDA_REDIS_HOST` are placeholders pointing at service names, the `Secret`
holds the compose default password, and the `PersistentVolumeClaim` has no
`storageClassName`.

> **The image tags in these manifests need rebuilding.**
> `registry.dbmi.cloud/posda:1.1.6` predates the `file-worker-py` and
> `pixel-worker-py` entrypoint commands. Build and push `posda/Dockerfile`,
> then set the three `image:` fields to that tag.

## Storage

All three tiers open the file by the path recorded in `file_storage_root`,
so they must mount the same volume at `/home/posda/cache` and the claim has
to be **ReadWriteMany** — workers land on whatever node has room. The
supplied PVC requests RWX but leaves the class unset; pick whichever your
cluster provides (NFS, CephFS, Filestore, EFS).

The `securityContext` in each Deployment matches the image's `posda` user
(uid 1000, gid 2123). An RWX volume that ignores `fsGroup`, which is common
for NFS, needs its export to grant that uid write access instead.

## Shutdown

Each pod stops on its own SIGTERM: it finishes the file it is holding, then
exits 0. Nothing is broadcast, so restarting one tier leaves the others
running.

**This is the main behavioural change from the previous architecture.** The
Perl pipeline — and the Python port before this change — signalled shutdown
by setting a `quit` key in Redis that every process polled. A daemon
receiving SIGTERM set it, which stopped every worker; on startup the daemon
deleted it again. Under Kubernetes that meant a rolling update of the daemon
took down the entire pipeline, and the delete raced with workers still
draining. The key is gone. Scaling a Deployment to zero is how you stop a
tier now.

A consequence: if you still run the Perl `FastFileProcessWorker.pl` anywhere,
nothing sets `quit` any more, so the Python daemon will no longer stop it.
Stop it directly.

`terminationGracePeriodSeconds` needs to exceed one BRPOP timeout (5s) plus
the slowest single file's processing time. The manifests use 60s. Watch for
pods being SIGKILLed at the deadline; see the durability note below for why
that costs more on the pixel tier than the file tier.

## Tuning

`POSDA_INGEST_BATCH_SIZE`, `POSDA_INGEST_IDLE_SLEEP` and
`POSDA_INGEST_TICK` in the ConfigMap control the daemon's refill loop; the
defaults (1000 / 10s / 1s) are the Perl's. The `POSDA_INGEST_FIX_*` flags
are documented in `posda/posdatools/docs/programming/Ingest-Fixes.md` —
`ATOMIC_IMPORT` is the one to consider first: it stops a failed file
leaving partial rows behind.

All of these are read once at startup, so a ConfigMap edit needs
`kubectl rollout restart deploy/<name>` to take effect.

### Autoscaling on queue depth

Queue length is the honest signal, and it is not something the HPA can read
without an adapter. With KEDA installed:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: posda-ingest-file-worker
spec:
  scaleTargetRef:
    name: posda-ingest-file-worker
  minReplicaCount: 1
  maxReplicaCount: 40
  cooldownPeriod: 300
  triggers:
    - type: redis
      metadata:
        address: posda-redis:6379
        listName: files
        listLength: "200"
```

Keep `cooldownPeriod` well above the grace period so scale-down does not
churn pods through partially processed files.

## Known limits

Two pre-existing behaviours matter more once pods are cattle. Neither is
introduced by this change and neither is fixed here.

**A lost pixel job is not recovered.** If a file worker's pod dies mid-file,
the file stays `is_dicom_file is null` and the daemon re-queues it on the
next refill — it self-heals. The pixel queue has no equivalent: nothing ever
re-derives `pixel_location` from the database, so a pixel worker killed
mid-file leaves that file's `dicom_file` pixel columns NULL permanently.
Routine eviction turns this into a slow trickle. `dicom_file.has_pixel_data
is null` identifies the affected rows exactly, and would be the basis of a
reconciliation query if you want one.

**The daemon can queue a file twice.** It refills whenever `files` is empty,
but files popped and still being processed are also still
`is_dicom_file null`, so they match the refill query again. `dicom_file` has
no primary key on `file_id`, so the second import silently writes duplicate
rows rather than erroring. More workers drain the list faster, which makes
the window more frequent, not less.
