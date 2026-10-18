# -*- coding: utf-8 -*-
"""Static checks for the LuCI application package.

These tests do not need a router or a JavaScript runtime. They protect the
layout and the official LuCI API usage that the view depends on.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "luci-app-giwifi"
VIEW = UI / "htdocs" / "luci-static" / "resources" / "view" / "network" / "giwifi.js"
MENU = UI / "root" / "usr" / "share" / "luci" / "menu.d" / "luci-app-giwifi.json"
ACL = UI / "root" / "usr" / "share" / "rpcd" / "acl.d" / "luci-app-giwifi.json"


def pkg_version(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*PKG_VERSION\s*:?=\s*(\S+)", line)
        if m:
            return m.group(1)
    raise AssertionError("PKG_VERSION not found in %s" % path)


class LuCIPackageTest(unittest.TestCase):
    def test_package_layout(self):
        self.assertTrue((ROOT / "giwifi-auth" / "Makefile").is_file())
        self.assertTrue((UI / "Makefile").is_file())
        self.assertTrue((UI / "htdocs").is_dir())
        self.assertTrue((UI / "root").is_dir())
        self.assertTrue((UI / "po" / "templates" / "giwifi.pot").is_file())
        self.assertTrue((UI / "po" / "zh_Hans" / "giwifi.po").is_file())
        self.assertTrue((UI / "htdocs" / "luci-static" / "resources" / "icons" / "giwifi.svg").is_file())
        self.assertIn("luci.mk", (UI / "Makefile").read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "giwifi-auth" / "files" / "www").exists())
        config = (ROOT / "giwifi-auth" / "files" / "etc" / "config" / "giwifi-auth").read_text(encoding="utf-8")
        self.assertIn("config status 'status'", config)
        self.assertIn("config log 'log'", config)

    def test_versions_are_consistent(self):
        backend = pkg_version(ROOT / "giwifi-auth" / "Makefile")
        ui = pkg_version(UI / "Makefile")
        view = re.search(r"const VERSION = '([^']+)'", VIEW.read_text(encoding="utf-8")).group(1)
        self.assertEqual(backend, ui)
        self.assertEqual(ui, view)

    def test_official_makefile_markers(self):
        ui_makefile = (UI / "Makefile").read_text(encoding="utf-8")
        backend_makefile = (ROOT / "giwifi-auth" / "Makefile").read_text(encoding="utf-8")
        # The OpenWrt package scanner only discovers a Makefile when it
        # contains one of these markers; the LuCI feed template has the
        # commented marker below the luci.mk include.
        self.assertIn("call BuildPackage", ui_makefile)
        self.assertIn("include $(TOPDIR)/feeds/luci/luci.mk", ui_makefile)
        self.assertIn("PKGARCH:=all", backend_makefile)

    def test_menu_action_path_exists(self):
        menu = json.loads(MENU.read_text(encoding="utf-8"))
        entry = menu["admin/network/giwifi"]
        self.assertEqual(entry["action"], {"type": "view", "path": "network/giwifi"})
        self.assertTrue((UI / "htdocs" / "luci-static" / "resources" / "view" /
                         (entry["action"]["path"] + ".js")).is_file())
        self.assertEqual(entry["depends"]["acl"], ["luci-app-giwifi"])

    def test_acl_covers_used_rpcs(self):
        acl = json.loads(ACL.read_text(encoding="utf-8"))["luci-app-giwifi"]
        self.assertIn("giwifi-auth", acl["read"]["uci"])
        self.assertIn("network", acl["read"]["uci"])
        self.assertIn("firewall", acl["read"]["uci"])
        self.assertIn("giwifi-auth", acl["write"]["uci"])
        self.assertIn("list", acl["read"]["ubus"]["file"])
        self.assertIn("list", acl["read"]["ubus"]["service"])
        self.assertIn("exec", acl["write"]["file"]["/usr/bin/giwifi-auth"])
        self.assertIn("exec", acl["write"]["ubus"]["file"])

    def test_single_named_section_and_cfgvalue(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertEqual(text.count("form.NamedSection, 'main'"), 1)
        self.assertEqual(text.count("o.textvalue"), 2)  # two GridSection preview cells
        self.assertIn("o.cfgvalue = function()", text)
        self.assertIn("this.super('renderRowActions', [ section_id, _('Edit') ])", text)
        for option in ("_version", "_daemon", "_switch", "_status", "_log"):
            self.assertIn("form.DummyValue, '%s'" % option, text)

    def test_dynamic_strings_are_text_nodes(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertIn("dom.content(body, [ _('Detecting…') ])", text)
        self.assertIn("dom.content(body, [ text ])", text)
        self.assertIn("E('pre', {}, [ logText ])", text)
        self.assertIn("E('pre', {}, [ out ])", text)
        self.assertIn("E('span', {}, [ _('Login result'), ' - ', target ])", text)
        self.assertNotIn("dom.content(body, text)", text)
        self.assertNotIn("E('pre', {}, logText)", text)
        self.assertNotIn("E('pre', {}, out)", text)

    def test_no_custom_css_or_theme_overrides(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertEqual(list(ROOT.rglob("*.css")), [])
        self.assertNotIn("<style", text)
        self.assertNotIn("stylesheet", text)
        self.assertNotIn("innerHTML", text)
        self.assertNotIn("'style':", text)

        # Only stock LuCI/Bootstrap classes are used; no theme-specific
        # selectors or custom class names are introduced by the view.
        allowed = {
            "btn", "cbi-button", "cbi-button-action", "cbi-button-apply",
            "cbi-button-neutral", "cbi-button-edit", "button-row", "cbi-modal",
            "ifacebox", "ifacebox-head", "ifacebox-body",
            "ifacebadge", "middle"
        }
        used = set()
        for value in re.findall(r"'class':\s*'([^']+)'", text):
            used.update(value.split())
        if "'cbi-modal'" in text:
            used.add("cbi-modal")
        self.assertEqual(used - allowed, set())

    def test_po_catalog_covers_view_strings(self):
        text = VIEW.read_text(encoding="utf-8")
        msgs = []
        for m in re.findall(r"_\('((?:[^'\\]|\\.)*)'\)", text):
            s = m.replace("\\'", "'")
            if s not in msgs:
                msgs.append(s)

        po = (UI / "po" / "zh_Hans" / "giwifi.po").read_text(encoding="utf-8")
        raw = re.findall(r'^msgid "((?:[^"\\]|\\.)*)"$', po, re.M)
        po_msgs = [m.replace('\\"', '"').replace("\\\\", "\\") for m in raw if m]
        self.assertEqual([m for m in msgs if m not in po_msgs], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
