#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
startup_script="$script_dir/scripts/icar_startup.sh"

# ROS 2 console-script processes normally have their executable name (for
# example `velocity_mux_node`), not `python`, in ps's comm column.  The
# startup guard must identify the requested executable path without assuming
# a Python interpreter process name.
if rg -q '\$2 ~ /\^python/' "$startup_script"; then
  echo "startup process guard incorrectly requires a python comm name" >&2
  exit 1
fi

# The singleton count must not include the shell or grep command that performs
# the inspection; otherwise one live node is reported as multiple processes.
if rg -q 'ps -eo stat=,args= \| grep -F' "$startup_script"; then
  echo "startup process guard counts its own grep/shell inspector" >&2
  exit 1
fi

echo "startup process guard accepts ROS console-script process names"
