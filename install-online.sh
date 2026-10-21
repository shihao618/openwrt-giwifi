#!/bin/sh
# GiWiFi one-click installer for OpenWrt 25.12 (apk).
#
# Usage:
#   wget -qO- https://raw.githubusercontent.com/shihao618/openwrt-giwifi/main/install-online.sh | sh
#
# Optional overrides:
#   GIWIFI_REF=v2.0.0   Git branch/tag whose artifacts/ directory is used
#   GIWIFI_BASE=...     Mirror prefix that contains the three apk files
set -eu

REPO="${GIWIFI_REPO:-shihao618/openwrt-giwifi}"
REF="${GIWIFI_REF:-main}"
BASE="${GIWIFI_BASE:-https://raw.githubusercontent.com/$REPO/$REF/artifacts}"

PACKAGES="
giwifi-auth-2.0.0-r2.apk
luci-app-giwifi-2.0.0-r1.apk
luci-i18n-giwifi-zh-cn-0.261018.31637.apk
"

TMP="${TMPDIR:-/tmp}/giwifi-install.$$"
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

fail() {
    echo "[ERROR] $*" >&2
    exit 1
}

[ "$(id -u)" = "0" ] || fail "请用 root 运行。"
command -v apk >/dev/null 2>&1 || fail "当前固件没有 apk，请使用 OpenWrt 25.12 / apk 系统。"

fetch() {
    if command -v wget >/dev/null 2>&1; then
        wget -q -O "$2" "$1" || fail "下载失败: $1"
    elif command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1" -o "$2" || fail "下载失败: $1"
    else
        fail "缺少 wget/curl，无法从 GitHub 下载。"
    fi
}

mkdir -p "$TMP"

echo "== 从 GitHub 下载 GiWiFi 安装包 ($REF) =="
for pkg in $PACKAGES; do
    echo "  -> $pkg"
    fetch "$BASE/$pkg" "$TMP/$pkg"
done

echo "== 安装 =="
apk add --allow-untrusted "$TMP"/*.apk

rm -f /tmp/luci-indexcache*
rm -rf /tmp/luci-modulecache
/etc/init.d/rpcd reload 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

echo ""
echo "安装完成。"
echo "打开 LuCI: 网络 -> GiWiFi 认证"
echo "首次安装默认不启动服务，请配置账号后打开“启用守护”。"
