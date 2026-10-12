#!/usr/bin/python3 -u
"""
Posda Worker Node management program.

This program interfaces with the Posda API and Redis queue
in order to accept work items and process them.

It must have access to the shared storage and configuration of
the main Posda installation, and it must be able to connect directly
to the Redis instance, as well as the api.

Those settings are read from the environment variables:
    * POSDA_INTERNAL_API_URL
    * POSDA_REDIS_HOST
    * POSDA_WORKER_PRIORITY
    * POSDA_WORKER_NAME

Three modes, chosen by the command line:

    WorkerNode.py                 pull work ids from Redis and run them here
    WorkerNode.py dispatch        pull work ids from Redis, create a Kueue
                                  Job per id (needs the posda-scheduler
                                  ServiceAccount and POD_NAME)
    WorkerNode.py run <work_id>   run one work item and exit; what the Job
                                  pods execute

The implementation lives in the posda.worker package.
"""
import sys

from posda.worker.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
