#!/bin/bash
#
# Recolor monochrome tray icons to the Omarchy bar foreground.
#
#   ./install.sh            patch the tray using the configured item list
#   ./install.sh --list     show the tray items currently on the bar
#   ./install.sh --items a,b   patch using this list instead of the config file
#   ./install.sh --revert   remove this patch, leaving any others intact
#
# Items are configured in ~/.config/omarchy/tray-recolor.conf, one name per
# line. A name is matched as a lowercased substring of a tray item's id, title
# or tooltip, so "remmina" catches the item whose id is "remmina-icon".
#
# The packaged tray under /usr/share/omarchy is never touched — only the local
# clone of omarchy.tray that `omarchy plugin clone` makes. Re-running is safe
# and is how you pick up a changed item list.

set -euo pipefail

PLUGINS_DIR="$HOME/.config/omarchy/plugins"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/tray-recolor.conf"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="apply"
ITEMS=""

fail() {
  echo "tray-recolor: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
  --revert) MODE="revert" ;;
  --list)
    exec python3 -B "$HERE/tray-items.py"
    ;;
  --items)
    [[ $# -ge 2 ]] || fail "--items needs a comma-separated list"
    ITEMS="$2"
    shift
    ;;
  --items=*) ITEMS="${1#--items=}" ;;
  -h | --help)
     sed -n '3,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *) fail "unknown option: $1" ;;
  esac
  shift
done

command -v jq >/dev/null || fail "jq is required"
command -v omarchy >/dev/null || fail "this is not an Omarchy system"

# Strip comments and blanks, join to a comma-separated list.
read_config() {
  [[ -f $CONFIG ]] || return 0
  sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$CONFIG" |
    grep -v '^$' | paste -sd, -
}

if [[ $MODE == "apply" && -z $ITEMS ]]; then
  ITEMS="$(read_config)"
  [[ -n $ITEMS ]] || fail "no items configured.
            Run './install.sh --list' to see what is on your bar, then list the
            ones to recolor in $CONFIG (one per line),
            or pass them directly with --items remmina,lerd"
fi

# A tray clone is any user plugin whose manifest records omarchy.tray as its
# source. Matching on clonedFrom rather than a directory name keeps this working
# whatever the clone ended up being called.
tray_dir=""
for manifest in "$PLUGINS_DIR"/*/manifest.json; do
  [[ -f $manifest ]] || continue
  if [[ $(jq -r '.omarchy.clonedFrom // ""' "$manifest") == "omarchy.tray" ]]; then
    tray_dir="$(dirname "$manifest")"
    break
  fi
done

if [[ -z $tray_dir ]]; then
  [[ $MODE == "apply" ]] || fail "no clone of omarchy.tray found — nothing to revert"
  echo "Cloning omarchy.tray..."
  omarchy plugin clone omarchy.tray
  for manifest in "$PLUGINS_DIR"/*/manifest.json; do
    [[ -f $manifest ]] || continue
    if [[ $(jq -r '.omarchy.clonedFrom // ""' "$manifest") == "omarchy.tray" ]]; then
      tray_dir="$(dirname "$manifest")"
      break
    fi
  done
  [[ -n $tray_dir ]] || fail "clone succeeded but the plugin was not found"
fi

echo "Tray plugin: $tray_dir"

if [[ $MODE == "revert" ]]; then
  python3 -B "$HERE/patch.py" revert "$tray_dir"
else
  # Revert first: a no-op when unpatched, and it is what lets a re-run pick up
  # an edited item list rather than refusing as already patched.
  python3 -B "$HERE/patch.py" revert "$tray_dir" >/dev/null
  python3 -B "$HERE/patch.py" apply "$tray_dir" --items "$ITEMS"
fi

# Widget code hot-reloads, but the tray builds its item list in a function the
# reload does not re-run, so give it a clean start.
omarchy restart shell
echo "Done."
