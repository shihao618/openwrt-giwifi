#!/bin/sh
# =============================================================================
# GiWiFi 校园网自动登录 —— OpenWrt 一键安装脚本
#
# 用法:
#   sh install.sh                     只安装（不收集账号，装完提示配置方式）
#   GIWIFI_USERNAME=xx GIWIFI_PASSWORD=xx sh install.sh   安装并配置账号后启动
#   sh install.sh --check             只检查环境/依赖/服务/在线状态
#   sh install.sh --uninstall         停止并卸载服务与脚本（保留配置）
#
# 环境变量（可选）:
#   GIWIFI_BASE_URL  GIWIFI_INTERVAL  GIWIFI_INTERFACE
#   GIWIFI_DEVICE_TYPE  GIWIFI_DEVICE_UA  GIWIFI_AUTO_REBIND
#   GIWIFI_IFACE_RESTART_ENABLED  GIWIFI_IFACE_RESTART_TIME  GIWIFI_SYNC_UA3F
#
# 说明: 认证脚本/守护/配置从 giwifi-auth/files/ 复制，LuCI 界面从
#       luci-app-giwifi/ 复制（与官方包结构一致，单一事实来源）。
#       装完 LuCI 界面后菜单如未出现，执行: /etc/init.d/uhttpd restart
# =============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$ROOT_DIR/giwifi-auth/files"
UI_DIR="$ROOT_DIR/luci-app-giwifi"
CONFIG=/etc/config/giwifi-auth

is_openwrt() {
    [ -x /sbin/uci ] && [ -d /etc/config ] && [ -f /etc/openwrt_release ]
}

say() { echo "$@"; }
warn() { echo "$@" >&2; }
die() { echo "[ERROR] $*" >&2; exit 1; }

# 复制单个文件并设置权限（不依赖 install 命令，OpenWrt/busybox 均可）
install_file() {
    src="$1"; dst="$2"; mode="$3"
    [ -f "$src" ] || die "缺少文件: $src"
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    chmod "$mode" "$dst"
}

# 让 LuCI 立即发现新菜单 / 新 ACL
refresh_luci() {
    rm -f /tmp/luci-indexcache /tmp/luci-indexcache.* 2>/dev/null || true
    rm -rf /tmp/luci-modulecache 2>/dev/null || true
    /etc/init.d/rpcd restart 2>/dev/null || true
    /etc/init.d/uhttpd reload 2>/dev/null || true
}

# 返回第一个 account 段的引用（匿名段用 @account[0] 形式，可被 uci set 使用）
first_account() {
    uci -q show giwifi-auth 2>/dev/null \
        | sed -n 's/^giwifi-auth\.\([^.=]*\)=account$/\1/p' \
        | head -n 1
}

check_python() {
    command -v python3 >/dev/null 2>&1 \
        && python3 -c 'import urllib.parse, http.client, ssl, html.parser, json' \
            >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------
do_check() {
    say "== 环境检查 =="
    if is_openwrt; then say "  [OK] OpenWrt 系统"; else
        say "  [FAIL] 不是 OpenWrt（缺 uci/config/openwrt_release）"; exit 1; fi

    if check_python; then
        say "  [OK] python3 及所需标准库模块"
    else
        say "  [WARN] 缺少 python3 或 urllib/ssl 模块，需安装 python3-light python3-urllib python3-openssl"
    fi

    if [ -x /usr/bin/giwifi-auth ]; then
        say "  [OK] giwifi-auth 已安装"
    else
        say "  [WARN] giwifi-auth 未安装"
    fi

    if [ -f /www/luci-static/resources/view/network/giwifi.js ] \
       && [ -f /usr/share/luci/menu.d/luci-app-giwifi.json ] \
       && [ -f /usr/share/rpcd/acl.d/luci-app-giwifi.json ]; then
        say "  [OK] LuCI 界面已安装"
    else
        say "  [WARN] LuCI 界面文件不完整"
    fi

    if [ -f /www/luci-static/resources/form.js ]; then
        say "  [OK] LuCI 基础框架（luci-base）"
    else
        say "  [WARN] 缺少 luci-base/luci-mod-network，LuCI 页面无法加载"
    fi

    if [ -f "$CONFIG" ]; then
        n=$(uci -q show giwifi-auth 2>/dev/null | grep -c '=account$' || true)
        say "  [INFO] 账号段数量: ${n:-0}"
        if [ "${n:-0}" -eq 0 ]; then
            say "  [WARN] 尚未配置账号（见 --help 或 README）"
        fi
    else
        say "  [WARN] 配置 $CONFIG 不存在"
    fi

    if /etc/init.d/giwifi-auth status >/dev/null 2>&1; then
        say "  [OK] 服务运行中"
    else
        say "  [WARN] 服务未运行"
    fi

    if [ -x /usr/bin/giwifi-auth ] && [ -f "$CONFIG" ]; then
        say "  [INFO] 当前在线状态:"
        /usr/bin/giwifi-auth check 2>&1 | sed 's/^/          /' || true
    fi
}

# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------
do_uninstall() {
    say "== GiWiFi 卸载 =="
    /etc/init.d/giwifi-auth stop 2>/dev/null || true
    /etc/init.d/giwifi-auth disable 2>/dev/null || true

    rm -f /usr/bin/giwifi-auth /etc/init.d/giwifi-auth
    rm -rf /usr/bin/__pycache__ 2>/dev/null || true
    rm -f /www/luci-static/resources/view/network/giwifi.js
    rm -f /usr/share/luci/menu.d/luci-app-giwifi.json
    rm -f /usr/share/rpcd/acl.d/luci-app-giwifi.json
    # 旧版 Lua CBI 界面残留
    rm -f /usr/lib/lua/luci/controller/giwifi.lua
    rm -f /usr/lib/lua/luci/model/cbi/giwifi.lua
    rm -rf /usr/lib/lua/luci/giwifi 2>/dev/null || true
    rm -rf /usr/lib/lua/luci/view/giwifi 2>/dev/null || true
    rm -f /usr/lib/lua/luci/view/cbi/giwifi_*.htm 2>/dev/null || true

    refresh_luci
    say "  已停止并删除服务、脚本与 LuCI 界面。"
    say "  配置 $CONFIG 已保留，如需彻底删除: rm -f $CONFIG"
}

# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------
do_install() {
    say "== GiWiFi 一键安装 =="

    is_openwrt || die "这看起来不是 OpenWrt 系统（缺 uci 或 /etc/openwrt_release）。"
    [ -f "$PKG_DIR/usr/bin/giwifi-auth" ] \
        || die "找不到 $PKG_DIR/usr/bin/giwifi-auth。请把 install.sh 与 giwifi-auth/ 目录放在一起后重试。"
    [ -f "$UI_DIR/htdocs/luci-static/resources/view/network/giwifi.js" ] \
        || die "找不到 $UI_DIR/htdocs/luci-static/resources/view/network/giwifi.js。请把 install.sh 与 luci-app-giwifi/ 目录放在一起后重试。"

    say "[1/6] 安装依赖 python3-light python3-urllib python3-openssl ..."
    # 25.12/snapshot 已切换到 apk；老版本仍用 opkg。
    if check_python; then
        say "       python3 及所需模块已存在，跳过"
    elif command -v apk >/dev/null 2>&1; then
        apk update || true
        apk add python3-light python3-urllib python3-openssl
    elif command -v opkg >/dev/null 2>&1; then
        opkg update || true
        opkg install python3-light python3-urllib python3-openssl
    else
        warn "  [WARN] 未找到 apk/opkg，请手动安装 python3-light python3-urllib python3-openssl"
    fi

    if [ ! -f /www/luci-static/resources/form.js ]; then
        warn "  [WARN] 未检测到 luci-base/luci-mod-network，LuCI 页面可能无法加载，请先安装这两个包"
    fi

    say "[2/6] 写入认证脚本 /usr/bin/giwifi-auth ..."
    install_file "$PKG_DIR/usr/bin/giwifi-auth" /usr/bin/giwifi-auth 755

    say "[3/6] 写入守护脚本 /etc/init.d/giwifi-auth ..."
    install_file "$PKG_DIR/etc/init.d/giwifi-auth" /etc/init.d/giwifi-auth 755

    say "[4/6] 写入 UCI 配置 /etc/config/giwifi-auth ..."
    if [ -f "$CONFIG" ]; then
        say "       已存在，保留原配置"
    else
        install_file "$PKG_DIR/etc/config/giwifi-auth" "$CONFIG" 644
    fi

    say "[5/6] 写入 LuCI 界面 ..."
    install_file "$UI_DIR/htdocs/luci-static/resources/view/network/giwifi.js" \
        /www/luci-static/resources/view/network/giwifi.js 644
    install_file "$UI_DIR/root/usr/share/luci/menu.d/luci-app-giwifi.json" \
        /usr/share/luci/menu.d/luci-app-giwifi.json 644
    install_file "$UI_DIR/root/usr/share/rpcd/acl.d/luci-app-giwifi.json" \
        /usr/share/rpcd/acl.d/luci-app-giwifi.json 644

    # 清理旧版 Lua CBI 界面残留（新界面为 LuCI JS 视图）
    rm -f /usr/lib/lua/luci/model/cbi/giwifi.lua
    rm -f /usr/lib/lua/luci/controller/giwifi.lua
    rm -f /usr/lib/lua/luci/view/cbi/giwifi_add.htm
    rm -f /usr/lib/lua/luci/view/cbi/giwifi_tblsection.htm
    rm -f /usr/lib/lua/luci/view/cbi/giwifi_form_section.htm

    say "[6/6] 配置账号并启动 ..."
    # 账号密码是运行配置，不由安装步骤收集：
    #   有 GIWIFI_USERNAME/PASSWORD -> 写入（或更新）第一个 account 段并启动；
    #   否则只应用可选参数，保留已有配置；账号为空则不启动，给出配置指引。
    [ -f "$CONFIG" ] || : > "$CONFIG"
    uci -q get giwifi-auth.main >/dev/null 2>&1 \
        || uci set giwifi-auth.main=giwifi

    if [ -n "$GIWIFI_BASE_URL" ]; then
        uci set "giwifi-auth.main.base_url=$GIWIFI_BASE_URL"
    fi
    if [ -n "$GIWIFI_INTERVAL" ]; then
        uci set "giwifi-auth.main.interval=$GIWIFI_INTERVAL"
    fi
    if [ -n "$GIWIFI_IFACE_RESTART_ENABLED" ]; then
        uci set "giwifi-auth.main.iface_restart_enabled=$GIWIFI_IFACE_RESTART_ENABLED"
    fi
    if [ -n "$GIWIFI_IFACE_RESTART_TIME" ]; then
        uci set "giwifi-auth.main.iface_restart_time=$GIWIFI_IFACE_RESTART_TIME"
    elif [ -n "$GIWIFI_IFACE_RESTART_CRON" ]; then
        # 兼容旧环境变量：cron 仍由后端作为回退读取
        uci set "giwifi-auth.main.iface_restart_cron=$GIWIFI_IFACE_RESTART_CRON"
    fi
    if [ -n "$GIWIFI_SYNC_UA3F" ]; then
        uci set "giwifi-auth.main.ua3f_sync_ua=$GIWIFI_SYNC_UA3F"
    fi

    if [ -n "$GIWIFI_USERNAME" ]; then
        if [ -z "$GIWIFI_PASSWORD" ]; then
            die "设置了 GIWIFI_USERNAME 但没有 GIWIFI_PASSWORD。"
        fi
        section=$(first_account)
        if [ -z "$section" ]; then
            section=$(uci add giwifi-auth account)
            say "       已创建账号段: $section"
        fi
        uci set "giwifi-auth.$section.enabled=1"
        uci set "giwifi-auth.$section.username=$GIWIFI_USERNAME"
        uci set "giwifi-auth.$section.password=$GIWIFI_PASSWORD"
        if [ -n "$GIWIFI_INTERFACE" ]; then
            uci set "giwifi-auth.$section.interface=$GIWIFI_INTERFACE"
        fi
        if [ -n "$GIWIFI_DEVICE_TYPE" ]; then
            uci set "giwifi-auth.$section.device_type=$GIWIFI_DEVICE_TYPE"
        fi
        if [ -n "$GIWIFI_DEVICE_UA" ]; then
            uci set "giwifi-auth.$section.device_ua=$GIWIFI_DEVICE_UA"
        fi
        if [ -n "$GIWIFI_AUTO_REBIND" ]; then
            uci set "giwifi-auth.$section.auto_rebind=$GIWIFI_AUTO_REBIND"
        fi
        uci set giwifi-auth.main.enabled=1
    fi
    # LuCI 的“运行状态 / 日志”选项卡使用两个空段作为占位。
    uci -q show giwifi-auth 2>/dev/null | grep -q '^giwifi-auth\.status=' \
        || uci set giwifi-auth.status=status
    uci -q show giwifi-auth 2>/dev/null | grep -q '^giwifi-auth\.log=' \
        || uci set giwifi-auth.log=log
    uci commit giwifi-auth

    refresh_luci

    # 「启用」开关是最终闸门：仅当 enabled=1 且至少一个账号有用户名时才启动
    if [ "$(uci -q get giwifi-auth.main.enabled 2>/dev/null)" = "1" ] && \
       uci -q show giwifi-auth 2>/dev/null | grep -q '\.username='; then
        /etc/init.d/giwifi-auth enable
        /etc/init.d/giwifi-auth start
        say ""
        say "== 完成 =="
        say "  服务已启用并启动。日志: logread -f | grep giwifi-auth"
        say "  立即登录一次: /usr/bin/giwifi-auth login"
        say "  查看状态:   sh install.sh --check"
        say "  卸载:       sh install.sh --uninstall"
        say "  LuCI 界面:  网络 → GiWiFi 认证（未出现则重启 uhttpd）"
    else
        say ""
        say "== 安装完成（未启用或未配置账号，服务未启动） =="
        say "  配置方式任选其一："
        say "  1) LuCI 界面: 网络 → GiWiFi 认证 → 账号列表 → 添加账号，"
        say "     填写绑定接口/账号/密码；再到「全局配置」勾选「启用守护进程」→ 保存并应用"
        say "  2) 命令行:"
        say "       uci add giwifi-auth account"
        say "       uci set giwifi-auth.@account[0].username='你的账号'"
        say "       uci set giwifi-auth.@account[0].password='你的密码'"
        say "       uci set giwifi-auth.@account[0].interface='eth0'"
        say "       uci set giwifi-auth.main.enabled='1'"
        say "       uci commit giwifi-auth"
        say "       /etc/init.d/giwifi-auth enable && /etc/init.d/giwifi-auth start"
        say "  3) 重跑安装并带账号（可同时指定 GIWIFI_INTERFACE）:"
        say "       GIWIFI_USERNAME=xx GIWIFI_PASSWORD=xx sh install.sh"
    fi
}

case "$1" in
    --check)
        do_check
        ;;
    --uninstall)
        do_uninstall
        ;;
    -h|--help)
        sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    *)
        do_install
        ;;
esac
