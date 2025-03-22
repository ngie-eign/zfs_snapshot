"""zfs_snapshot: CLI."""
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: ANN401, FBT001

from __future__ import annotations

import argparse
import datetime
from dataclasses import dataclass
from typing import Any

from . import zfs_snapshot


@dataclass(frozen=True, init=True, repr=True)
class SnapshotPolicy:
    """Dataclass which defines a snapshot policy.

    Fields:
        name: snapshot policy descriptor, e.g., "years".
        lifetime: snapshot policy lifetime.
        date_format_qualifier: the date format qualifier to use when computing snapshot
                               names.
    """

    name: str
    lifetime: datetime.timedelta
    date_format_qualifier: str


DATE_ELEMENT_SEPARATOR = "."
NOW = datetime.datetime.now()  # noqa: DTZ005
# These are very much approximations of reality.
#
# I really wish `dateutil.relativedelta(..)` actually worked reliably; it
# was screwing up the difference between a datetime and the value in the
# `relativedelta`.
WEEKS_IN_A_MONTH = 4
WEEKS_IN_A_YEAR = 52
# The list order matters. See `main(..)` for more details.
SNAPSHOT_CATEGORIES = [
    SnapshotPolicy(
        name="years",
        lifetime=datetime.timedelta(weeks=2 * WEEKS_IN_A_YEAR),
        date_format_qualifier="Y",
    ),
    SnapshotPolicy(
        name="months",
        lifetime=datetime.timedelta(weeks=1 * WEEKS_IN_A_YEAR),
        date_format_qualifier="m",
    ),
    SnapshotPolicy(
        name="days",
        lifetime=datetime.timedelta(weeks=1 * WEEKS_IN_A_MONTH),
        date_format_qualifier="d",
    ),
    SnapshotPolicy(
        name="hours", lifetime=datetime.timedelta(days=1), date_format_qualifier="H",
    ),
]
DEFAULT_SNAPSHOT_PERIOD = "hours"
DEFAULT_SNAPSHOT_PREFIX = "auto"


def execute_snapshot_policy(*args: Any, **kwargs: Any) -> None:
    """Proxy function for testing."""
    return zfs_snapshot.execute_snapshot_policy(*args, **kwargs)


def list_vdevs(*args: Any, **kwargs: Any) -> list[str]:
    """Proxy function for testing."""
    return zfs_snapshot.list_vdevs(*args, **kwargs)


def lifetime_type(optarg: str) -> int:
    """Validate --lifetime to ensure that it's > 0."""
    value = int(optarg)
    if value <= 0:
        msg = "Lifetime must be an integer value greater than 0"
        raise argparse.ArgumentTypeError(
            msg,
        )
    return value


def period_type(optarg: str) -> int:
    """Validate --snapshot-period to ensure that the value passed is valid."""
    value = optarg.lower()
    for i, mapping_tuple in enumerate(SNAPSHOT_CATEGORIES):
        if mapping_tuple.name == value:
            return i
    raise argparse.ArgumentTypeError("Invalid --snapshot-period: %s" % (optarg))


def prefix_type(optarg: str) -> str:
    """Validate --prefix to ensure that it's a non-nul string."""
    value = optarg
    if value:
        return value
    err_msg = "Snapshot prefix must be a non-zero length string"
    raise argparse.ArgumentTypeError(err_msg)


def vdev_type(optarg: str) -> str:
    """Validate --vdev.

    This ensures that the vdev provided on the CLI exist(ed) at the time the script was
    executed.

    Returns:
        The parsed value corresponding to a valid `vdev`.

    """
    all_vdevs = list_vdevs()
    value = optarg
    if value in all_vdevs:
        return value
    err_msg = f"Virtual device specified, '{value}', does not exist"
    raise argparse.ArgumentTypeError(err_msg)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments.

    Args:
        argv: `sys.argv` in a nutshell.

    Returns:
        A argparse.Namespace corresponding to the parsed arguments.

    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lifetime",
        help=(
            "lifetime (number of snapshots) to keep of a "
            "vdev; the value is relative to the number of "
            '"periods".'
        ),
        type=lifetime_type,
    )
    parser.add_argument(
        "--snapshot-period",
        default=DEFAULT_SNAPSHOT_PERIOD,
        help=("period with which to manage snapshot policies with"),
        type=period_type,
    )
    parser.add_argument(
        "--snapshot-prefix",
        default=DEFAULT_SNAPSHOT_PREFIX,
        help="prefix to add to a snapshot",
        type=prefix_type,
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="create and destroy snapshots recursively",
    )
    parser.add_argument(
        "--vdev",
        action="append",
        default=[],
        dest="vdevs",
        help="dataset or zvol to snapshot",
        type=vdev_type,
    )
    return parser.parse_args(args=argv)


def compute_cutoff(
    policy: SnapshotPolicy,
    lifetime_override: float,
) -> datetime.datetime:
    """Compute the expiration time for a given policy.

    Args:
        policy: the snapshot policy.
        lifetime_override: an override value for the snapshot lifetime.

    Returns:
        A `datetime.datetime` object that corresponds to a snapshot's lifetime.

    """
    if lifetime_override:
        policy_name = policy.name
        if policy_name == "years":
            policy_name = "weeks"
            lifetime_override *= WEEKS_IN_A_YEAR
        elif policy_name == "months":
            policy_name = "weeks"
            lifetime_override *= WEEKS_IN_A_MONTH
        lifetime = datetime.timedelta(**{policy_name: lifetime_override})
    else:
        lifetime = policy.lifetime
    return NOW - lifetime


def compute_vdevs(vdevs: list[str], recursive: bool) -> list[str]:
    """Compute a full ZFS vdev list from input vdevs.

    Args:
        vdevs: a list of ZFS `vdevs` to expand on.
        recursive: get vdevs recursively.

    Returns:
        A list of vdevs that is a superset of the provided vdevs.

    """
    if recursive and vdevs:
        target_vdevs = []
        for vdev in vdevs:
            target_vdevs.extend(
                zfs_snapshot.zfs(f"list -H -o name -r {vdev}").splitlines(),
            )
        return target_vdevs
    return vdevs or list_vdevs()


def main(args: list[str] | None = None) -> int:
    """Eponymous main."""
    args = parse_args(args=args)

    # This builds a hierarchical date string in reverse recursive order, e.g.,
    # "2018.09.01" would be "daily".
    #
    # This depends on the ordering of `SNAPSHOT_CATEGORIES`.
    date_format = DATE_ELEMENT_SEPARATOR.join(
        [
            "%" + SNAPSHOT_CATEGORIES[i].date_format_qualifier
            for i in range(args.snapshot_period + 1)
        ],
    )

    snapshot_category = SNAPSHOT_CATEGORIES[args.snapshot_period]
    snapshot_suffix = snapshot_category.date_format_qualifier
    # ruff: noqa: UP031
    snapshot_name_format = "%s-%s%s" % (
        args.snapshot_prefix,
        date_format,
        snapshot_suffix,
    )
    snapshot_cutoff = compute_cutoff(snapshot_category, args.lifetime)
    vdevs = compute_vdevs(args.vdevs, args.recursive)

    for vdev in sorted(vdevs, reverse=True):
        execute_snapshot_policy(
            vdev,
            NOW.timetuple(),
            snapshot_cutoff.timetuple(),
            snapshot_name_format,
            recursive=args.recursive,
        )

    return 0
