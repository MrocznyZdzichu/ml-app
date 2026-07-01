#!/bin/sh
set -eu

data_root=/app/data
permission_marker="$data_root/.app-user-permissions-v1"

mkdir -p "$data_root"

# One-time migration for data directories created by older root-based images.
# Only directory ownership changes: large dataset files are not traversed by
# chown, and subsequent starts skip the migration entirely.
if [ ! -f "$permission_marker" ]; then
    find "$data_root" -type d -exec chown app:app {} +
    touch "$permission_marker"
    chown app:app "$permission_marker"
fi

exec setpriv --reuid=app --regid=app --init-groups "$@"
