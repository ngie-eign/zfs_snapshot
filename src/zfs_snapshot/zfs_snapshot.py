"""zfs_snapshot: core functionality."""
# SPDX-License-Identifier: BSD-2-Clause

import shlex
import subprocess
import time

SNAPSHOT_SEPARATOR = "@"
ZFS = "/sbin/zfs"


# ruff: noqa: FBT001, FBT002, S603


class VdevNotFoundError(FileNotFoundError):
    """Wrapper exception to aid with filtering out this particular scenario."""


def snapshot_name(vdev: str, date_format: str) -> str:
    """Create a properly formatted snapshot name.

    Args:
        vdev:        name of a vdev to take a snapshot with.
        date_format: strftime(3) compatible date format to assign to the
                     snapshot.

    """
    return f"{vdev}{SNAPSHOT_SEPARATOR}{date_format}"


def zfs(arg_str: str) -> str:
    """Run a zfs subcommand.

    Args:
        arg_str: a flat string with a list of arguments to pass to zfs(8),
                 e.g. -t snapshot.

    Returns:
        The output from zfs(8).

    """
    return subprocess.check_output(
        [ZFS, *shlex.split(arg_str)],
        encoding="utf-8",
        errors="surrogateescape",
    )


def create_snapshot(vdev: str, date_format: str) -> None:
    """Create a snapshot for a vdev with a given date format.

    Args:
        vdev:        name of a vdev to take a snapshot with.
        date_format: strftime(3) compatible date format to assign to the
                     snapshot.

    """
    snap_name = snapshot_name(vdev, date_format)
    zfs(f"snapshot {snap_name}")


def destroy_snapshot(snapshot: str) -> None:
    """Destroy a snapshot.

    Args:
        snapshot: name of the snapshot to destroy.

    """
    zfs(f"destroy {snapshot}")


def list_vdevs() -> list[str]:
    """Return all vdevs.

    Raises:
        VdevNotFoundError: no vdevs could be found.

    Returns:
        A list of available vdevs.

    """
    vdevs = zfs("list -H -t filesystem,volume -o name").split()
    if not vdevs:
        msg = "no vdevs found on system"
        raise VdevNotFoundError(msg)
    return vdevs


def list_snapshots(vdev: str, recursive: bool = True) -> list[str]:
    """Get a list of ZFS snapshots for a given vdev.

    Args:
        vdev:      a vdev to grab snapshots for.
        recursive: list snapshot(s) for the parent and child vdevs.

    Returns:
        A list of zero or more snapshots

    """
    recursive_flag = " -r" if recursive else ""

    return zfs(f"list -H -t snapshot {recursive_flag} -o name {vdev}").splitlines()


def is_destroyable_snapshot(
    vdev: str,
    cutoff: time.struct_time,
    date_format: str,
    snapshot: str,
) -> bool:
    """Determine if a snapshot should be destroyed.

    Take a snapshot string, unmarshall the date, and determine if it's
    eligible for destruction.

    Args:
        vdev:        name of the vdev to execute the snapshotting policy
                     (creation/deletion) on.
        cutoff:      any snapshots created before this time are nuked. This
                     is a tuple, resembling a `time.struct_time` object.
        date_format: a strftime(3) compatible date format to look for/destroy
                     snapshots with.
        snapshot:    snapshot name.

    Returns:
        True if the snapshot is out of date; False otherwise.

    """
    snapshot_formatted = snapshot_name(vdev, date_format)
    try:
        snapshot_time = time.strptime(snapshot, snapshot_formatted)
    except ValueError:
        # Date format does not match
        return False
    return snapshot_time < time.struct_time(cutoff)


def execute_snapshot_policy(
    vdev: str,
    now: time.struct_time,
    cutoff: time.struct_time,
    date_format: str,
    recursive: bool = True,
) -> None:
    """Execute snapshot policy on a vdev.

    Old snapshots which have met or exceeded the `cutoff` time are deleted; new
    snapshots are created afterwards.

    Args:
        vdev:        name of the vdev to execute the snapshotting policy
                     (creation/deletion) on.
        now:         new time to snapshot against. This should be the time
                     that the script execution was started, i.e., a stable
                     value.
        cutoff:      any snapshots created before this time are nuked. This
                     is a tuple, resembling a `time.struct_time` object.
        date_format: a strftime(3) compatible date format to look for/destroy
                     snapshots with.
        recursive:   execute zfs snapshot create recursively.

    """
    snapshots = list_snapshots(vdev, recursive=recursive)

    expired_snapshots = [
        snapshot
        for snapshot in snapshots
        if is_destroyable_snapshot(vdev, cutoff, date_format, snapshot)
    ]
    for snapshot in sorted(expired_snapshots, reverse=True):
        # Destroy snapshots as needed, reverse order so the snapshots will
        # be destroyed in order.
        destroy_snapshot(snapshot)

    create_snapshot(vdev, time.strftime(date_format, now))
