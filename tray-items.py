#!/usr/bin/env python3
"""List the tray items currently on the bar, to help pick names to recolor.

Names are matched as lowercased substrings of an item's id, title or tooltip,
so the shortest fragment that is unique to the app is usually the right choice.
"""

import re
import subprocess
import sys

BUS = "org.kde.StatusNotifierItem"
WATCHER = ("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
           "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems")


def prop(service, path, name):
  try:
    out = subprocess.run(
      ["busctl", "--user", "get-property", service, path, BUS, name],
      capture_output=True, text=True, timeout=5).stdout.strip()
  except (subprocess.SubprocessError, OSError):
    return ""
  match = re.match(r'^s\s+"(.*)"$', out, re.S)
  return match.group(1) if match else ""


def main():
  try:
    out = subprocess.run(["busctl", "--user", "get-property", *WATCHER],
                         capture_output=True, text=True, timeout=10).stdout
  except (subprocess.SubprocessError, OSError):
    print("tray-recolor: could not reach the StatusNotifierWatcher", file=sys.stderr)
    return 1
  items = re.findall(r'"([^"]+)"', out)
  if not items:
    print("No tray items are currently registered.")
    return 0

  print("%-14s %-24s %-18s %s" % ("SUGGESTED", "ID", "TITLE", "ICON"))
  for entry in sorted(items):
    service, _, path = entry.partition("/")
    path = "/" + path
    ident = prop(service, path, "Id")
    title = prop(service, path, "Title")
    icon = prop(service, path, "IconName")
    # The shortest useful handle. Prefer the title: ids are often generic
    # ("systray") or carry a pid, while the title names the app. Take the first
    # token so "lerd-tray" suggests "lerd" and a pid-bearing id loses the pid.
    name = re.split(r"[-_.\s]", (title or ident).strip())[0].lower()
    note = ""
    if icon.endswith("-symbolic"):
      note = "   (already recolored by the shell)"
    elif not icon:
      note = "   (pixmap — check it is monochrome before adding)"
    print("%-14s %-24s %-18s %s%s" % (name or "?", ident or "-", title or "-",
                                      icon or "-", note))
  print("\nOnly add icons that are monochrome. A full-color status icon carries\n"
        "meaning in its color, and recoloring it throws that meaning away.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
