"""Helpers for validating user-supplied filesystem paths."""

import os


def path_is_within_root(path: str, root: str) -> bool:
    """Return True iff path resolves to root or a descendant of root.

    Uses os.path.realpath on both sides so symlinks can't be used to escape
    the configured root.
    """
    try:
        real_path = os.path.realpath(path)
        real_root = os.path.realpath(root)
    except OSError:
        return False
    try:
        return os.path.commonpath([real_path, real_root]) == real_root
    except ValueError:
        # Raised when the paths share no common prefix at all (e.g. different
        # drives on Windows).
        return False
