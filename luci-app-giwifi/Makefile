include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-giwifi
PKG_VERSION:=2.0.0
PKG_RELEASE:=1

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=yangxingyu <1767274678@qq.com>

LUCI_TITLE:=LuCI Support for GiWiFi Authentication
LUCI_DESCRIPTION:=Web interface for the GiWiFi campus portal auto-login daemon
LUCI_DEPENDS:=+giwifi-auth +luci-base +luci-mod-network
LUCI_PKGARCH:=all
LUCI_MAINTAINER:=yangxingyu <1767274678@qq.com>
LUCI_URL:=https://github.com/shihao618/openwrt-giwifi

# The official LuCI feed Makefile include. When building a standalone package
# with the OpenWrt SDK, the LuCI feed must be installed at feeds/luci.
include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
