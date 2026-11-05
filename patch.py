#!/usr/bin/env python3
"""Recolor monochrome tray icons to the Omarchy bar foreground.

The Omarchy tray recolors an icon only when its *name* ends in the freedesktop
"-symbolic" suffix. Plenty of apps ship a perfectly monochrome glyph that misses
that convention, so it is drawn with whatever fill it happens to carry and sits
in the bar looking nothing like its neighbours:

  * Remmina advertises `org.remmina.Remmina-status`; Yaru (inherited by every
    Yaru-* theme) bakes `#3d3d3d` into its panel icon — near-invisible on a
    dark bar.
  * lerd writes a white PNG to /tmp and advertises that path as its icon name.

Such an icon's alpha channel is already the glyph, so pouring the bar
foreground through it follows any theme exactly, live, with no replacement icon
and nothing baked in.

Only ever list icons that are *monochrome*. A full-color status icon — Mullvad's
red-when-disconnected padlock, say — carries meaning in its color, and flattening
it to a silhouette throws that meaning away.

The patch is anchored surgery on whatever tray version is installed, not a
frozen fork, so re-running it after an `omarchy update` re-applies to the new
upstream code. Every anchor is required: a miss aborts without touching the file
rather than half-patching the tray.

Two shapes, chosen automatically:

  standalone  the stock tray. Installs the silhouette machinery itself.
  layered     a tray already carrying dropbox-extended's patch, which installs
              equivalent machinery. Reuses it and only adds this predicate, so
              the two coexist without fighting over the same code.
"""

import argparse
import re
import sys
from pathlib import Path

MARKER = "tray-recolor:begin"
HEADER = "// tray-recolor:patched — https://github.com/tdhftw/omarchy-tray-recolor\n"

# Set by dropbox-extended's tray patch. Its presence means the silhouette
# machinery is already in place and must not be installed a second time.
LAYERED_ANCHOR = "readonly property bool themed:"

MODEL_BLOCK = '''// --- tray-recolor:begin -----------------------------------------------------
// Tray items whose icon is a monochrome glyph carrying a fixed fill, rather
// than a freedesktop "-symbolic" one the shell recolors on sight. The bar
// foreground is poured through the glyph's own alpha instead.
//
// Matched against each item's id, title and tooltip — never its icon name, so
// an app that regenerates its icon under a fresh /tmp path every run still
// matches. Substring match, lowercased: "remmina" catches "remmina-icon".
var RECOLORED_ITEMS = [%s]

function recoloredItem(item) {
  for (var i = 0; i < RECOLORED_ITEMS.length; i++) {
    if (itemNamed(item, RECOLORED_ITEMS[i])) return true
  }
  return false
}
// --- tray-recolor:end -------------------------------------------------------

'''

QML_FUNCTION = '''  // --- tray-recolor:begin ---
  // Items recolored to the bar foreground even though their icon name carries
  // no "-symbolic" suffix. This feeds the icon rendering only, never
  // classifyItem(), so a recolored item keeps its normal pinned/drawer/hidden
  // placement.
  function iconIsRecolored(item) {
    if (!item) return false
    return TrayModel.recoloredItem(item)
  }
  // --- tray-recolor:end ---

'''

# --- standalone mode: the silhouette machinery, installed on a stock tray -----

STOCK_SYMBOLIC = "    readonly property bool symbolic: root.iconIsSymbolic(icon)"

STANDALONE_SYMBOLIC = '''    // --- tray-recolor:begin ---
    // The tray item behind this icon, so a recolored item can be drawn as a
    // silhouette the way a symbolic one is tinted.
    property var item: null
    readonly property bool recolored: root.iconIsRecolored(item)
    // --- tray-recolor:end ---
    readonly property bool symbolic: root.iconIsSymbolic(icon) || recolored'''

STOCK_EFFECT = """    MultiEffect {
      anchors.fill: trayIconImage
      source: trayIconImage
      visible: trayIconRoot.symbolic
      colorization: 1.0
      colorizationColor: root.foreground
    }"""

STANDALONE_EFFECT = """    // --- tray-recolor:begin ---
    // A recolored icon is drawn as a silhouette — the bar foreground poured
    // through the icon's own alpha — rather than tinted. Colorization preserves
    // luminance, which is right for a symbolic icon (already near-white) but
    // leaves a darker glyph muddy.
    Rectangle {
      id: recolorFill
      anchors.fill: trayIconImage
      color: root.foreground
      // Never drawn directly; it exists to be sampled as the effect's texture,
      // the same way trayIconImage is for a symbolic icon.
      visible: false
      layer.enabled: trayIconRoot.recolored
    }
    // --- tray-recolor:end ---

    MultiEffect {
      anchors.fill: trayIconImage
      source: trayIconRoot.recolored ? recolorFill : trayIconImage
      visible: trayIconRoot.symbolic
      maskEnabled: trayIconRoot.recolored
      maskSource: trayIconImage
      // Colorization is luminance-preserving, so running it over the solid fill
      // would darken the silhouette by the foreground's own luminance.
      colorization: trayIconRoot.recolored ? 0.0 : 1.0
      colorizationColor: root.foreground
    }"""

# Appends to whatever expression the binding already carries, so an upstream or
# dropbox-extended rewrite of it does not break this patch.
LAYERED_BINDING = re.compile(
  r"^([ \t]*)readonly property bool themed: (?!.*iconIsRecolored)(.+)$", re.M)

BLOCK = re.compile(
  r"^[ \t]*// --- tray-recolor:begin.*?^[ \t]*// --- tray-recolor:end[^\n]*\n(\n)?",
  re.S | re.M)


def fail(message):
  print("tray-recolor: " + message, file=sys.stderr)
  sys.exit(1)


def js_list(items):
  return ", ".join('"%s"' % i.replace("\\", "\\\\").replace('"', '\\"') for i in items)


def patch_tray_model(text, items):
  anchor = 'if (typeof module !== "undefined") {'
  if anchor not in text:
    fail("TrayModel.js: could not find the module.exports guard")
  text = text.replace(anchor, MODEL_BLOCK % js_list(items) + anchor, 1)

  exports = "  module.exports = {\n"
  if exports not in text:
    fail("TrayModel.js: could not find `module.exports = {`")
  return text.replace(exports, exports + "    recoloredItem: recoloredItem,\n", 1)


def patch_tray_qml(text):
  anchor = "  function trayTooltip(item) {"
  if anchor not in text:
    fail("Tray.qml: could not find `function trayTooltip(item)`")
  text = text.replace(anchor, QML_FUNCTION + anchor, 1)

  if LAYERED_ANCHOR in text:
    if not LAYERED_BINDING.search(text):
      fail("Tray.qml: found a `themed` binding but could not parse it")
    return LAYERED_BINDING.sub(
      lambda m: "%sreadonly property bool themed: %s || root.iconIsRecolored(item)"
                % (m.group(1), m.group(2)), text, count=1), "layered"

  if STOCK_SYMBOLIC not in text:
    fail("Tray.qml: could not find TrayIcon's `symbolic` binding")
  text = text.replace(STOCK_SYMBOLIC, STANDALONE_SYMBOLIC, 1)

  if STOCK_EFFECT in text:
    # Omarchy < 4.5 tinted symbolic icons, which leaves a darker glyph muddy;
    # swap in a silhouette for recolored items.
    text = text.replace(STOCK_EFFECT, STANDALONE_EFFECT, 1)
  elif "maskSource: trayIconImage" not in text:
    # 4.5+ already draws every symbolic icon as a silhouette, so a recolored
    # item needs nothing beyond counting as symbolic. Anything else is unknown.
    fail("Tray.qml: could not find TrayIcon's recoloring effect")

  # Feed each TrayIcon the item its icon came from. Both call sites already have
  # `modelData` in scope; indentation is copied from the icon line.
  for holder in ("rowRoot", "trayItemRoot"):
    call = re.compile(r"^([ \t]*)icon: %s\.modelData\.icon$" % holder, re.M)
    if not call.search(text):
      fail("Tray.qml: could not find `icon: %s.modelData.icon`" % holder)
    text = call.sub(lambda m: "%sicon: %s.modelData.icon\n%sitem: %s.modelData"
                    % (m.group(1), holder, m.group(1), holder), text, count=1)
  return text, "standalone"


# Standalone mode installs the `recolored` property; layered mode never does.
# Decided before the marked blocks are stripped, because the tell lives in one.
STANDALONE_TELL = "readonly property bool recolored: root.iconIsRecolored(item)"


def unpatch(text):
  standalone = STANDALONE_TELL in text
  text = text.replace(HEADER, "", 1)
  while BLOCK.search(text):
    text = BLOCK.sub("", text, count=1)
  text = text.replace("    recoloredItem: recoloredItem,\n", "", 1)
  text = text.replace(" || root.iconIsRecolored(item)", "", 1)
  if not standalone:
    # Layered mode borrowed the machinery underneath rather than installing it.
    # Undoing any of it here would tear out the patch this one layered onto.
    return text
  text = text.replace(
    "    readonly property bool symbolic: root.iconIsSymbolic(icon) || recolored",
    STOCK_SYMBOLIC, 1)
  text = text.replace(STANDALONE_EFFECT_BODY, STOCK_EFFECT, 1)
  return re.sub(r"^([ \t]*)icon: (rowRoot|trayItemRoot)\.modelData\.icon\n[ \t]*item: \2\.modelData$",
                lambda m: "%sicon: %s.modelData.icon" % (m.group(1), m.group(2)),
                text, flags=re.M)


# The effect block minus its marked comment header, which unpatch() has already
# stripped by the time the body is put back.
STANDALONE_EFFECT_BODY = STANDALONE_EFFECT.split("// --- tray-recolor:end ---\n\n", 1)[1]


def load(plugin_dir):
  model = plugin_dir / "TrayModel.js"
  qml = plugin_dir / "Tray.qml"
  for path in (model, qml):
    if not path.is_file():
      fail("missing %s — is %s a clone of omarchy.tray?" % (path.name, plugin_dir))
  return model, qml


def apply(plugin_dir, items):
  if not items:
    fail("no items configured — nothing to recolor")
  model, qml = load(plugin_dir)
  model_text = model.read_text(encoding="utf-8")
  qml_text = qml.read_text(encoding="utf-8")
  if MARKER in model_text or MARKER in qml_text:
    print("already patched — revert first to change the item list")
    return

  model_out = HEADER + patch_tray_model(model_text, items)
  qml_out, mode = patch_tray_qml(qml_text)
  model.write_text(model_out, encoding="utf-8")
  qml.write_text(HEADER + qml_out, encoding="utf-8")
  print("patched %s (%s mode): %s" % (plugin_dir, mode, ", ".join(items)))


def revert(plugin_dir):
  model, qml = load(plugin_dir)
  model_text = model.read_text(encoding="utf-8")
  qml_text = qml.read_text(encoding="utf-8")
  if MARKER not in model_text and MARKER not in qml_text:
    print("not patched — nothing to do")
    return
  model.write_text(unpatch(model_text), encoding="utf-8")
  qml.write_text(unpatch(qml_text), encoding="utf-8")
  print("reverted %s" % plugin_dir)


def main():
  parser = argparse.ArgumentParser(description="Recolor monochrome tray icons.")
  parser.add_argument("action", choices=("apply", "revert"))
  parser.add_argument("plugin_dir", type=Path)
  parser.add_argument("--items", default="",
                      help="comma-separated names to match (apply only)")
  args = parser.parse_args()
  if args.action == "apply":
    apply(args.plugin_dir, [i.strip() for i in args.items.split(",") if i.strip()])
  else:
    revert(args.plugin_dir)


if __name__ == "__main__":
  main()
