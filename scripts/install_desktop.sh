#!/bin/sh
# Install menu launchers and executable icons for this unpacked Linux release.
set -eu
release_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$release_dir/recharge-ai-task" --install-desktop "$@"
