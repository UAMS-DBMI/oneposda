"""Command line for the worker node.

WorkerNode.py                 legacy: BRPOP work ids from Redis, run inline
WorkerNode.py dispatch        create one Kueue Job per work id
WorkerNode.py run <work_id>   process a single work item (the Job's entrypoint)
"""

from __future__ import annotations

import argparse
import logging

from posda.worker import dispatch, legacy, run

LOG_FORMAT = "[%(levelname).4s|%(asctime)s|%(module)-15.15s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d/%H:%M:%S"


def configure_logging() -> None:
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, datefmt=LOG_DATEFMT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="WorkerNode.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    modes = parser.add_subparsers(dest="mode")
    modes.add_parser("dispatch", help="dispatch queued work as Kubernetes Jobs")
    run_parser = modes.add_parser("run", help="process one work item and exit")
    run_parser.add_argument("work_id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)

    if args.mode is None:
        legacy.run_legacy()
        return 0
    if args.mode == "dispatch":
        dispatch.run_dispatcher()
        return 0
    return run.run_single(args.work_id)
