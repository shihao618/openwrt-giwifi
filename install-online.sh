#!/bin/sh
# GiWiFi one-click installer for OpenWrt 25.12 (apk).
#
# Usage:
#   wget -qO- https://raw.githubusercontent.com/shihao618/openwrt-giwifi/main/install-online.sh | sh
#
# Optional overrides:
#   GIWIFI_REF=v2.1.2   Git branch/tag whose artifacts/ directory is used
#   GIWIFI_BASE=...     Mirror prefix that contains the three apk files
set -eu

REPO="${GIWIFI_REPO:-shihao618/openwrt-giwifi}"
REF="${GIWIFI_REF:-main}"
DEFAULT_BASE="https://raw.githubusercontent.com/$REPO/$REF/artifacts"
MIRROR_BASES="https://ghproxy.net/https://raw.githubusercontent.com/$REPO/$REF/artifacts https://gh-proxy.com/https://raw.githubusercontent.com/$REPO/$REF/artifacts"
if [ -n "${GIWIFI_BASE:-}" ]; then
    BASES="$GIWIFI_BASE"
else
    BASES="$DEFAULT_BASE $MIRROR_BASES"
fi

PACKAGES="
giwifi-auth-2.1.2-r1.apk
luci-app-giwifi-2.1.2-r1.apk
luci-i18n-giwifi-zh-cn-0.261021.47922.apk
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
        wget -q -O "$2" "$1" || return 1
    elif command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1" -o "$2" || return 1
    else
        return 1
    fi
}

mkdir -p "$TMP"

echo "== 从 GitHub 下载 GiWiFi 安装包 ($REF) =="
for pkg in $PACKAGES; do
    echo "  -> $pkg"
    ok=0
    for base in $BASES; do
        if fetch "$base/$pkg" "$TMP/$pkg"; then
            ok=1
            break
        fi
        echo "     下载失败，尝试下一个镜像..."
    done
    [ "$ok" = "1" ] || fail "所有下载源均失败: $pkg"
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
