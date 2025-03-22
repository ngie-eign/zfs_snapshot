"""zfs_snapshot: CLI test."""
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: DTZ011, FBT003, INP001, S101, UP031

from typing import Self
from unittest import mock

import pytest
from dateutil.relativedelta import relativedelta

from zfs_snapshot.__main__ import (
    DEFAULT_SNAPSHOT_PERIOD,
    DEFAULT_SNAPSHOT_PREFIX,
    NOW,
    SNAPSHOT_CATEGORIES,
    compute_cutoff,
    compute_vdevs,
    parse_args,
    period_type,
)
from zfs_snapshot import zfs_snapshot


def patch_zfs_snapshot(rel_path: str) -> mock._patch:
    return mock.patch(f"{zfs_snapshot.__name__}.{rel_path}")


class TestArguments:
    vdevs = ["bogus-vdev", "bogus-vdev/nested", "another/bogus/vdev"]

    def test_lifetime(self: Self) -> None:
        parse_args(argv=["--lifetime", "1"])
        parse_args(argv=["--lifetime", "42"])
        with pytest.raises(SystemExit):
            parse_args(argv=["--lifetime", "-1"])
        with pytest.raises(SystemExit):
            parse_args(argv=["--lifetime", "apple"])

    def test_snapshot_period(self: Self) -> None:
        for i, snapshot_category in enumerate(SNAPSHOT_CATEGORIES):
            name = snapshot_category.name
            opts = parse_args(argv=["--snapshot-period", name])
            assert opts.snapshot_period == i

            # Minor optimization: since here, we might as well test the default
            # case instead of trying to precompute the index out-of-band
            # somehow.
            if name == DEFAULT_SNAPSHOT_PERIOD:
                opts = parse_args(argv=[])
                assert opts.snapshot_period == i

        with pytest.raises(SystemExit):
            parse_args(argv=["--snapshot-period", "bogus"])

    def test_snapshot_prefix(self: Self) -> None:
        opts = parse_args(argv=[])
        assert opts.snapshot_prefix == DEFAULT_SNAPSHOT_PREFIX
        opts = parse_args(argv=["--snapshot-prefix", "bogus"])
        assert opts.snapshot_prefix == "bogus"
        with pytest.raises(SystemExit):
            opts = parse_args(argv=["--snapshot-prefix", ""])

    def test_vdev(self: Self) -> None:
        vdevs = self.vdevs

        test_inputs_outputs_positive = [
            # __main__.main(..) will fill in the blanks later.
            [[], []],
            # Single option/argument pair.
            [["--vdev", vdevs[0]], [vdevs[0]]],
            # Multiple option/argument pair (accumulator).
            [["--vdev", vdevs[0], "--vdev", vdevs[-1]], [vdevs[0], vdevs[-1]]],
        ]
        test_inputs_outputs_negative = [
            ["--vdev", "doesnotexist"],
            ["--vdev", vdevs[0] + " "],
        ]

        with patch_zfs_snapshot("list_vdevs") as list_vdevs:
            list_vdevs.return_value = vdevs
            for args, test_output in test_inputs_outputs_positive:
                opts = parse_args(argv=args)
                assert opts.vdevs == test_output

            for args in test_inputs_outputs_negative:
                with pytest.raises(SystemExit):
                    parse_args(argv=args)


class TestMain:
    def test_compute_cutoff(self: Self) -> None:
        default_snapshot_type_index = period_type(DEFAULT_SNAPSHOT_PERIOD)
        default_snapshot_category = SNAPSHOT_CATEGORIES[default_snapshot_type_index]
        assert compute_cutoff(default_snapshot_category, 42) == NOW - relativedelta(
            **{default_snapshot_category.name: 42},
        )
        assert (
            compute_cutoff(default_snapshot_category, None)
            == NOW - default_snapshot_category.lifetime
        )

    def test_compute_vdevs(self: Self) -> None:
        all_vdevs = ["bogus-vdev", "bogus-vdev/nested", "another/bogus/vdev"]

        with (
            patch_zfs_snapshot("list_vdevs") as list_vdevs,
            patch_zfs_snapshot("zfs") as zfs,
        ):
            list_vdevs.return_value = all_vdevs

            zfs.side_effect = ["bogus-vdev\nbogus-vdev/nested\n"]
            # Recursive with --vdev
            assert compute_vdevs(["bogus-vdev"], True) == [
                "bogus-vdev",
                "bogus-vdev/nested",
            ]
            zfs.assert_has_calls([mock.call("list -H -o name -r %s" % ("bogus-vdev"))])
            zfs.reset_mock()

            # Recursive with --vdev, redux
            zfs.side_effect = [
                "bogus-vdev\nbogus-vdev/nested\n",
                "another/bogus/vdev\n",
            ]
            assert compute_vdevs(["bogus-vdev", "another/bogus/vdev"], True) == [
                "bogus-vdev",
                "bogus-vdev/nested",
                "another/bogus/vdev",
            ]
            zfs.assert_has_calls(
                [
                    mock.call("list -H -o name -r %s" % ("bogus-vdev")),
                    mock.call("list -H -o name -r %s" % ("another/bogus/vdev")),
                ],
            )
            zfs.reset_mock()

            # Non-recursive with --vdev
            assert compute_vdevs(["bogus-vdev", "another/bogus/vdev"], False) == [
                "bogus-vdev",
                "another/bogus/vdev",
            ]

            # Non-recursive with --vdev
            assert compute_vdevs(["bogus-vdev"], False) == ["bogus-vdev"]

            # All vdevs
            assert compute_vdevs([], False) == all_vdevs
