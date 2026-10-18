include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-giwifi
PKG_VERSION:=1.4.0
PKG_RELEASE:=11

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=yangxingyu <1767274678@qq.com>

LUCI_TITLE:=LuCI Support for GiWiFi Authentication
LUCI_DESCRIPTION:=Web interface for the GiWiFi campus portal auto-login daemon
LUCI_DEPENDS:=+giwifi-auth +luci-base +luci-mod-network
LUCI_PKGARCH:=all
LUCI_MAINTAINER:=yangxingyu <1767274678@qq.com>
LUCI_URL:=https://github.com/shihao618/openwrt-giwifi

# The LuCI build framework provides the standard post-install hook (menu/ACL
# cache invalidation and rpcd reload) unless a custom one is defined. Define
# one here only to additionally remove legacy Lua CBI files from old releases.
define Package/luci-app-giwifi/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && [ "$${IPKG_INSTROOT}" != "/" ] && exit 0
rm -f /usr/lib/lua/luci/model/cbi/giwifi.lua
rm -f /usr/lib/lua/luci/controller/giwifi.lua
rm -f /usr/lib/lua/luci/view/cbi/giwifi_add.htm
rm -f /usr/lib/lua/luci/view/cbi/giwifi_tblsection.htm
rm -f /usr/lib/lua/luci/view/cbi/giwifi_form_section.htm
# Create the UI-only status/log sections on upgrades from older configs.
if command -v uci >/dev/null 2>&1 && [ -f /etc/config/giwifi-auth ]; then
	uci -q show giwifi-auth 2>/dev/null | grep -q '^giwifi-auth\.status=' || uci set giwifi-auth.status=status
	uci -q show giwifi-auth 2>/dev/null | grep -q '^giwifi-auth\.log=' || uci set giwifi-auth.log=log
	uci commit giwifi-auth
fi
rm -f /tmp/luci-indexcache /tmp/luci-indexcache.* 2>/dev/null || true
rm -rf /tmp/luci-modulecache/ 2>/dev/null || true
/etc/init.d/rpcd reload 2>/dev/null || true
exit 0
endef

# The official LuCI feed Makefile include. When building a standalone package
# with the OpenWrt SDK, the LuCI feed must be installed at feeds/luci.
include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
