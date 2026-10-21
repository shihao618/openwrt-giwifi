# GiWiFi 校园网自动登录 — OpenWrt 插件

在 OpenWrt 路由器上自动登录校园网（GiWiFi Web Portal，`authLogin` 流），掉线自动重登。
路由器登录后，其 WAN 侧会话即被校园网认证，**整个内网（电脑/手机）都能上网**。

> 2.0.0 起仅面向全新安装（OpenWrt 25.12 / apk），不提供 1.x 旧配置和旧界面的迁移逻辑。

## 目录结构

```
openwrt-giwifi/
├── artifacts/                    # 随代码发布的预构建 apk / 源码包
├── install.sh                    # 一键安装脚本（分别复制后端与 LuCI 界面）
├── install-online.sh             # GitHub 在线一键安装（下载 artifacts 后 apk add）
├── giwifi-auth/                  # 后端包：认证程序 + 守护 + UCI 配置
│   ├── Makefile                  # OpenWrt 包定义（PKGARCH:=all）
│   └── files/
│       ├── etc/
│       │   ├── init.d/giwifi-auth          # procd 守护进程 + UCI 变更触发器
│       │   ├── config/giwifi-auth          # UCI 配置模板
│       │   └── hotplug.d/iface/90-giwifi-policy  # 接口变化时重建策略路由
│       ├── usr/bin/giwifi-auth             # 认证脚本（纯标准库 Python3）
│       └── usr/sbin/giwifi-policy          # 每账号路由表 + 原生 ECMP 管理器
├── luci-app-giwifi/              # LuCI 界面包（官方 luci.mk / htdocs / root / po 结构）
│   ├── Makefile                  # LUCI_TITLE / LUCI_DEPENDS + luci.mk
│   ├── htdocs/luci-static/resources/view/network/giwifi.js
│   ├── root/usr/share/luci/menu.d/luci-app-giwifi.json
│   ├── root/usr/share/rpcd/acl.d/luci-app-giwifi.json
│   └── po/
│       ├── templates/giwifi.pot
│       └── zh_Hans/giwifi.po
├── scripts/build_release.py      # 用 OpenWrt SDK 编译打包（apk/ipk + 源码 zip）
└── test/
    ├── test_openwrt_auth.py      # 后端单元 + 端到端测试（本地 mock Portal）
    └── test_luci_ui.py           # LuCI 包结构 / i18n / 安全写法静态检查
```

后端与 LuCI 界面按官方惯例拆成**两个包**：`giwifi-auth` 提供守护与 UCI 配置，
`luci-app-giwifi` 提供界面并依赖 `giwifi-auth`。这样可以使用 LuCI 官方的
`luci.mk`、`htdocs`/`root` 目录、`po` 翻译和 `luci-i18n-*` 打包机制。

## 功能

- 多账号：每个 `account` 段绑定一个网络接口，独立轮询、独立认证；
- 掉线自动重登：TCP 链路探测 + Portal 会话探测，连续失败指数退避（30s 起、封顶 5min）；
- 热点/共享风控（reasoncode=55）退避 15 分钟、「今天时长已用完」退避 30 分钟；
- 自动换绑：`auto_rebind=1` 时遇绑定冲突（reasoncode=43 / 设备数超限提示）自动 `reBindMac`；
  密码错误(27)、热点风控(55)、封禁类提示**不会**触发换绑；
- 可选用 iPad / iPhone / Windows / Android UA，或自定义 UA；
- 可选每天定时重启接口（界面直接选择时间）；
- 可选把全局 UA 同步给 UA3F（`ua3f_sync_ua`）；
- 多网口自动负载均衡：启用多个账号并绑定不同 WAN 接口后，插件自动为每个账号建立
  独立路由表 + 源地址规则，并用这些接口生成原生 ECMP 默认路由；无需手工写
  `ip rule`/`ip route`，也不依赖 mwan3（ECMP 模式要求停用 mwan3）；
  认证请求仍同时绑定出接口与源 IP，多 WAN 下不会走错出口；绑定接口无地址时提前提示并退避；
- LuCI 页面：运行状态、账号在线状态、最近认证日志、账号增删改、手动登录。

## 依赖

OpenWrt 的 python3 标准库按模块拆包，本插件需要三个包（纯标准库实现 AES-128-CBC、
HTTP、JSON，无第三方库）：

- `python3-light`：解释器 + 常用模块（json/html/http/base64 等）
- `python3-urllib`：提供 `urllib`
- `python3-openssl`：提供 `_ssl`（HTTPS 连接支持）

LuCI 界面需要：`luci-base`、`luci-mod-network`（通常固件自带），由
`luci-app-giwifi` 包自动声明依赖。

安装（OpenWrt 25.12 / apk）：

```sh
apk add giwifi-auth luci-app-giwifi luci-i18n-giwifi-zh-cn
```

如果只用 `install.sh` 手动安装，脚本会自动处理后端 Python 依赖；LuCI 基础包需固件自带。

## GitHub 一键安装（OpenWrt 25.12 / apk）

在路由器上直接执行：

```sh
wget -q -O - https://raw.githubusercontent.com/shihao618/openwrt-giwifi/main/install-online.sh | sh
```

或：

```sh
curl -fsSL https://raw.githubusercontent.com/shihao618/openwrt-giwifi/main/install-online.sh | sh
```

脚本会从仓库 `artifacts/` 下载三个 apk 并安装。固定版本或使用镜像：

```sh
# 固定使用 v2.1.0 的 artifacts
wget -q -O - https://raw.githubusercontent.com/shihao618/openwrt-giwifi/main/install-online.sh | GIWIFI_REF=v2.1.0 sh

# 自定义 artifact 镜像前缀
wget -q -O - https://raw.githubusercontent.com/shihao618/openwrt-giwifi/main/install-online.sh | GIWIFI_BASE=https://your-mirror/giwifi sh
```

> 这是 `apk` 系统专用的一键安装，适用于 OpenWrt 25.12；执行前可以先下载脚本查看内容。

## 快速安装（免编译，直接传文件）

把整个 `openwrt-giwifi` 目录传到路由器（或任意可访问位置），然后：

```sh
cd openwrt-giwifi
sh install.sh                       # 只安装（不收集账号）
GIWIFI_USERNAME=xx GIWIFI_PASSWORD=xx [GIWIFI_INTERFACE=eth0] sh install.sh  # 安装并配置后启动
```

脚本会分别从 `giwifi-auth/files/` 复制脚本与配置、从 `luci-app-giwifi/` 复制界面
（单一事实来源，不会多副本漂移）。安装过程**不会要求输入账号密码**（那是运行配置）；
账号为空时服务不启动，装完后通过 LuCI 或 `uci` 配置即可。

可选环境变量：`GIWIFI_BASE_URL`、`GIWIFI_INTERVAL`、`GIWIFI_INTERFACE`、
`GIWIFI_DEVICE_TYPE`（`ipad`/`iphone`/`windows`/`android`）、`GIWIFI_DEVICE_UA`、
`GIWIFI_AUTO_REBIND`、`GIWIFI_IFACE_RESTART_ENABLED`、`GIWIFI_IFACE_RESTART_TIME`、
`GIWIFI_SYNC_UA3F`。

安装完成后：

```sh
logread -f | grep giwifi-auth     # 查看日志
/usr/bin/giwifi-auth login        # 立即登录一次（全部账号）
/usr/bin/giwifi-auth log          # 查看认证日志（最新在上，50 条）
sh install.sh --check             # 环境/依赖/服务/在线状态自检
sh install.sh --uninstall         # 卸载（保留 /etc/config/giwifi-auth）
```

> `GIWIFI_INTERFACE` / 页面里的「绑定接口」是 **Linux 网卡名**（如 `eth0`、`wan`，
> 或 mwan3 成员 `mwan1`/`mwan2`、macvlan 虚拟口），不是 UCI interface 段名；
> 留空则不绑定接口（单 WAN 路由器通常也可用）。

## 命令行用法（路由器上）

```sh
/usr/bin/giwifi-auth login [标识]       # 登录一次（标识=段名/用户名/绑定接口，省略=全部）
/usr/bin/giwifi-auth logout [标识]      # 注销下线（同上）
/usr/bin/giwifi-auth status             # 在线状态 + 在线时长
/usr/bin/giwifi-auth check              # 0=在线 1=掉线 2=网络异常
/usr/bin/giwifi-auth log                # 查看认证日志（最新在上，50 条）
/usr/bin/giwifi-auth sync-ua3f          # 把全局 UA3F UA 同步给 ua3f 插件
/usr/bin/giwifi-auth check-config       # 接口唯一性校验（0=通过 1=重复绑定）
/usr/bin/giwifi-auth run                # 循环监控 + 掉线自动登录
```

配置在**每次认证前动态重读 UCI**，因此 LuCI 保存后即时生效（守护进程会按新配置重启）。

## UCI 配置

`/etc/config/giwifi-auth`：

```sh
config giwifi 'main'
	option enabled '1'                  # 启用守护（新装默认 0）
	option base_url 'http://10.189.1.3' # Portal 基地址
	option interval '30'                # 轮询间隔秒（下限 10）
	option iface_restart_enabled '0'    # 定时重启接口
	option iface_restart_time '04:00'   # 每天重启时间 HH:MM
	option ua3f_sync_ua ''              # 同步给 UA3F 的终端类型，空=不改
	option ecmp_enabled '1'             # 根据账号绑定接口自动做 ECMP 负载均衡

# 以下两个空段仅用于 LuCI 的“运行状态 / 日志”选项卡，无配置项
config status 'status'
config log 'log'

config account 'name'                   # 可多个（LuCI 添加的为匿名段）
	option enabled '1'
	option interface 'eth0'             # 绑定网卡（认证请求从此接口发出）
	option username '...'
	option password '...'
	option device_type 'windows'        # ipad/iphone/windows/android
	option device_ua ''                 # 非空时优先于 device_type
	option auto_rebind '0'
```

| 配置 | 含义 | 默认 |
| --- | --- | --- |
| `enabled` | 是否启用守护 | `0` |
| `base_url` | Portal 基地址 | `http://10.189.1.3` |
| `interval` | 轮询间隔秒（加 0~20% 随机抖动） | `30` |
| `ecmp_enabled` | 根据账号绑定接口自动构建原生 ECMP 默认路由 | `1` |
| `device_type` | `ipad`/`iphone`/`windows`/`android` | `windows` |
| `device_ua` | 自定义 UA（非空时优先） | 空 |
| `auto_rebind` | 绑定冲突自动换绑 | `0` |

同一网络接口只能被一个账号绑定：页面保存时会校验，运行期守护也会跳过后来者。

## 自动 ECMP 负载均衡

插件会自动读取所有已启用账号的 `interface`，为每个接口生成：

- 独立路由表：`table 100 + ifindex`；
- 源地址规则：`from <接口 IPv4> lookup <table> priority 1000`；
- 所有接口的 ECMP 默认路由：`nexthop via <网关> dev <接口> weight 1`。

LAN 侧的新连接会按 Linux ECMP 哈希分摊到各 WAN；单个 TCP 连接仍然只走一条
WAN，因此这是**多连接/多线程总带宽叠加**，不是单连接带宽叠加。

注意事项：

- **必须停用 mwan3**：mwan3 的 fwmark 策略路由与 fwmark 规则会和本方案冲突；
  `giwifi-policy` 检测到 mwan3 进程时会清理本插件生成的路由并跳过 ECMP 配置；
- 接口 up/down、DHCP 续租、账号增删改、插件保存并应用时都会自动重建；
- 账号接口必须已经取得 IPv4 地址和默认网关，否则该接口暂不参与 ECMP；
- 权重默认均为 1；如需调整，可在账号 section 中加 `option weight '2'`（1~100）。

## LuCI 界面

安装后进入 **网络 → GiWiFi 认证**（`luci-app-giwifi` 包）：

- **运行状态**：插件版本、守护状态、账号在线状态（显示用户名+接口）；
- **设置**：启用、Portal 地址、轮询间隔、自动 ECMP 负载均衡、定时重启时间、UA3F 同步终端类型；
- **账号列表**：左侧接口图标+用户名，中间显示终端类型、账号状态、自动换绑状态，右侧操作按钮；操作列提供 **登录 / 停止或启用 / 编辑 / 删除**；
- **日志**：最近认证日志；
- 「添加账号」弹窗内填写绑定接口、账号、密码、终端类型、自定义 UA、自动换绑；
- 绑定接口下拉框只列出 **WAN 防火墙区域** 内的接口（区域名不要求是 `wan`，按 masq / wan 类名称 / wan 网络识别）；
- **保存** 只写配置不生效；**保存并应用** 提交后由 procd 配置触发器
  （`/etc/init.d/giwifi-auth reload`）按新配置重启守护进程，并同步 UA3F UA；
- 账号的启用/停止走同一条「保存并应用」通道；
- 界面文本以英文 msgid 编写，`po/zh_Hans/giwifi.po` 提供简体中文翻译；英文环境正常显示英文；
- 手动 `install.sh` 不编译 `.po`；需要中文界面时请安装 `luci-i18n-giwifi-zh-cn` 包；
- 若菜单未出现：`/etc/init.d/uhttpd restart`（或重启 rpcd）。

## 编译安装（OpenWrt SDK / ImageBuilder）

把 `giwifi-auth/` 与 `luci-app-giwifi/` 放入 SDK 的 `package/`，并确保 LuCI feed 已安装
（`./scripts/feeds update luci && ./scripts/feeds install -a -p luci`），然后：

```sh
make package/giwifi-auth/compile \
     package/luci-app-giwifi/compile \
     package/luci-i18n-giwifi-zh-cn/compile V=s
```

生成 `giwifi-auth-<版本>-r<发布号>-all.apk`、
`luci-app-giwifi-<版本>-r<发布号>-all.apk` 以及由 `po/` 生成的
`luci-i18n-giwifi-zh-cn-*.apk`。
把三个包都传到路由器安装：

```sh
apk add --allow-untrusted giwifi-auth-*.apk luci-app-giwifi-*.apk luci-i18n-giwifi-zh-cn-*.apk
```

三个包均为 noarch（`PKGARCH:=all` / `LUCI_PKGARCH:=all`），所有架构通用；`/etc/config/giwifi-auth` 已声明为
conffiles，升级不会覆盖你的配置。`luci-app-giwifi` 由官方 `luci.mk` 构建，
`luci-i18n-giwifi-*` 翻译包也由同一 Makefile 生成。

## 打包发布（OpenWrt SDK）

`scripts/build_release.py` 走 **OpenWrt 官方打包流程**：调用 OpenWrt SDK 编译后端包、
LuCI 界面包和中文翻译包，产物与手动 `make package/.../compile` 完全一致。

```sh
python3 scripts/build_release.py --sdk /path/to/openwrt-sdk
# 或
OPENWRT_SDK=/path/to/openwrt-sdk python3 scripts/build_release.py [--dist dist] [--clean]
```

脚本会：校验两个源包的 `PKG_VERSION` 与 LuCI 视图 `VERSION` 一致 → 检查 SDK 的 LuCI feed →
把 `giwifi-auth/`、`luci-app-giwifi/` 同步进 SDK 的 `package/` → 编译（含 `po/` 翻译包）→
收集产物到 `dist/` → 打包源码 zip。

产物：

- `dist/giwifi-auth-<ver>-r<rel>.apk`；
- `dist/luci-app-giwifi-<ver>-r<rel>.apk`；
- `dist/luci-i18n-giwifi-zh-cn-*.apk`（简体中文翻译）；
- `dist/openwrt-giwifi-<ver>.zip`：源码包。

> Windows 原生环境无法运行 SDK 构建，请在 Linux / WSL 中执行。
> LuCI 包使用官方 `luci.mk`，SDK 中必须先安装 LuCI feed，否则构建会明确报错。

安装后是否自启由配置决定：新装默认不启动，配置好账号并打开「启用守护」后才会启动。

## 仓库内预构建包

`artifacts/` 存放随代码一起发布的 OpenWrt 25.12 apk 包，可直接下载安装：

- `artifacts/giwifi-auth-2.1.0-r1.apk`
- `artifacts/luci-app-giwifi-2.1.0-r1.apk`
- `artifacts/luci-i18n-giwifi-zh-cn-*.apk`
- `artifacts/openwrt-giwifi-2.1.0.zip`

## 测试

```sh
python test/test_openwrt_auth.py     # 直接运行后端测试
python test/test_luci_ui.py          # LuCI 包结构 / 版本 / i18n / 安全写法静态检查
python -m pytest test -q             # pytest（收集全部测试）
```

后端测试会在本地起 mock Portal，覆盖登录页解析、AES 加密表单、`queryAuthState`、
终端类型 UA，以及 reasoncode 43/41 的换绑行为。

## 安全说明

- 认证协议本身为**明文 HTTP + 固定密钥 AES-128-CBC**（密钥 `1234567887654321` 在 Portal
  前端 JS 中可见，属协议设计，并非保密措施）。
- 账号密码以明文存储在路由器的 `/etc/config/giwifi-auth` 中，请勿将配置/备份文件外传。
- 建议仅在受信任的校园网内使用；如需加密传输，可将 `base_url` 配置为 Portal 的 HTTPS 地址
  （脚本已支持，且绑定接口时 HTTPS 仍会正常完成 TLS 握手）。

## 说明与限制

- 认证协议：Web `authLogin` JS 流（GET 登录页 → 序列化 `#frmLogin` → AES-128-CBC +
  ZeroPadding → POST `/gportal/web/authLogin?round=N`）。
- 在线判定：POST `/gportal/web/queryAuthState {userIp, sign}`，`status==1` 为在线，
  并返回 `onlineTime`（秒）用于显示在线时长。
- 自动换绑：`auto_rebind=1` 时，遇绑定冲突（reasoncode=43 或设备数超限提示）调
  `reBindMac` 换绑到当前设备并重新认证（换绑成功有 6 秒冷却）；密码错误(27)、
  热点风控(55)、封禁类提示**不会**触发换绑，日志保留原始失败原因。- 本包面向「路由器直接拨入校园网（WAN 侧被认证）」的场景；若 Portal 变体不同，
  `base_url` 与 `authLogin` 端点路径可能需要调整。
