include $(TOPDIR)/rules.mk

PKG_NAME:=giwifi-auth
PKG_VERSION:=2.1.4
PKG_RELEASE:=1

PKG_MAINTAINER:=yangxingyu <1767274678@qq.com>
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE
PKG_URL:=https://github.com/shihao618/openwrt-giwifi

# Pure script package, architecture independent.
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/giwifi-auth
  SECTION:=net
  CATEGORY:=Network
  TITLE:=GiWiFi campus auto-login (Web authLogin)
  DEPENDS:=+python3-light +python3-urllib +python3-openssl +ip-full
  PKGARCH:=all
endef

define Package/giwifi-auth/description
  Automatically logs the OpenWrt router into the GiWiFi campus portal
  using the Web authLogin flow (AES-128-CBC + ZeroPadding).
  Checks online state via /gportal/web/queryAuthState and re-logs in
  when the session drops. The LuCI user interface is provided by the
  separate luci-app-giwifi package.
endef

define Build/Compile
endef

# User configuration is preserved across apk upgrades.
define Package/giwifi-auth/conffiles
/etc/config/giwifi-auth
endef

# Start policy: a fresh apk install does not start the service; post-upgrade
# preserves the previous enabled state and restarts the instance.
define Package/giwifi-auth/postinst
#!/bin/sh
[ "$${IPKG_NO_SCRIPT:-0}" = "1" ] && exit 0
[ -n "$${IPKG_INSTROOT}" ] && [ "$${IPKG_INSTROOT}" != "/" ] && exit 0
if [ "$${PKG_UPGRADE:-0}" = "1" ]; then
    if [ "$$(uci get giwifi-auth.main.enabled 2>/dev/null)" = "1" ]; then
        /etc/init.d/giwifi-auth enable 2>/dev/null || true
        if uci show giwifi-auth 2>/dev/null | grep -q "^giwifi-auth\..*=account"; then
            /etc/init.d/giwifi-auth restart 2>/dev/null || true
        fi
    fi
fi
exit 0
endef

# Stop and disable the service before removal/upgrade to avoid stale rc.d links.
define Package/giwifi-auth/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && [ "$${IPKG_INSTROOT}" != "/" ] && exit 0
/etc/init.d/giwifi-auth stop 2>/dev/null || true
/etc/init.d/giwifi-auth disable 2>/dev/null || true
exit 0
endef

define Package/giwifi-auth/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/usr/bin/giwifi-auth $(1)/usr/bin/giwifi-auth
	find $(1)/usr/bin -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/usr/sbin/giwifi-policy $(1)/usr/sbin/giwifi-policy
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/etc/init.d/giwifi-auth $(1)/etc/init.d/giwifi-auth
	$(INSTALL_DIR) $(1)/etc/hotplug.d/iface
	$(INSTALL_BIN) ./files/etc/hotplug.d/iface/90-giwifi-policy $(1)/etc/hotplug.d/iface/90-giwifi-policy
	$(INSTALL_DIR) $(1)/etc/sysctl.d
	$(INSTALL_DATA) ./files/etc/sysctl.d/99-giwifi-ecmp.conf $(1)/etc/sysctl.d/99-giwifi-ecmp.conf
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/etc/config/giwifi-auth $(1)/etc/config/giwifi-auth
endef

$(eval $(call BuildPackage,giwifi-auth))
