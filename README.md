# zfs_snapshot

Mini ZFS snapshot tool written in python.

## Installation

`pipx install .`

## Use

This is best used in a crontab, similar to the following:

```
@hourly         zfs_snapshot --snapshot-period hours --recursive
@daily          zfs_snapshot --snapshot-period days --recursive
@monthly        zfs_snapshot --snapshot-period months --recursive
```

This schedule will snapshot all ZFS vdevs on an hourly, daily, and monthly
basis, and preen any old snapshots as need be according to the policy set in
the package.
