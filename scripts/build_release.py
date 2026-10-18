# -*- coding: utf-8 -*-
"""构建发布产物：走 OpenWrt 官方打包流程（OpenWrt SDK）。

本脚本只负责编排：
  1. 校验后端包、LuCI 包与 LuCI 视图三者的版本一致；
  2. 把 giwifi-auth/ 与 luci-app-giwifi/ 同步进 SDK 的 package/；
  3. 调用 SDK 编译（必要时先 defconfig）；
  4. 收集 SDK 产物到 dist/；
  5. 打包项目源码 zip。

LuCI 包使用官方的 luci.mk，因此 SDK 中必须先安装 LuCI feed：
  ./scripts/feeds update luci && ./scripts/feeds install -a -p luci

用法:
  python3 scripts/build_release.py --sdk /path/to/openwrt-sdk
  OPENWRT_SDK=/path/to/openwrt-sdk python3 scripts/build_release.py
  python3 scripts/build_release.py --sdk /path/to/sdk --dist dist --clean

产物:
  dist/giwifi-auth_<ver>-r<rel>_all.apk        （或 .ipk，取决于 SDK）
  dist/luci-app-giwifi_<ver>-r<rel>_all.apk    （或 .ipk）
  dist/luci-i18n-giwifi-zh-cn-*.apk          （或 .ipk）
  dist/openwrt-giwifi-<ver>.zip                （源码包）
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

PKG_NAMES = ("giwifi-auth", "luci-app-giwifi")
# LuCI translations are separate packages generated from po/ by luci.mk.
I18N_PKGS = ("luci-i18n-giwifi-zh-cn",)
UI_VIEW = os.path.join(ROOT, "luci-app-giwifi", "htdocs", "luci-static",
                       "resources", "view", "network", "giwifi.js")

# 排除项（打包源码 zip 时跳过）
SKIP_DIRS = {"dist", "__pycache__", ".git", ".pytest_cache",
             ".github", ".vscode", ".idea", ".work"}
SKIP_EXT = {".pyc", ".pyo"}


def _fail(msg):
    raise SystemExit("[ERROR] %s" % msg)


# ---------------------------------------------------------------------------
# 版本解析与一致性校验
# ---------------------------------------------------------------------------
def parse_pkg_version(makefile):
    """从 Makefile 解析 PKG_VERSION，返回纯版本号（不含 release）。"""
    with open(makefile, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*PKG_VERSION\s*:?=\s*(\S+)", line)
            if m:
                return m.group(1)
    raise SystemExit("无法解析版本号: %s" % makefile)


def js_version(path):
    """读取 LuCI 视图里的 VERSION 常量。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"(?:var|const|let)\s+VERSION\s*=\s*'([^']+)'", text)
    if not m:
        raise SystemExit("无法解析 LuCI 视图版本号: %s" % path)
    return m.group(1)


# ---------------------------------------------------------------------------
# 参数与 SDK 定位
# ---------------------------------------------------------------------------
def parse_args(argv):
    opts = {"sdk": os.environ.get("OPENWRT_SDK", ""),
            "dist": DIST, "clean": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--sdk" and i + 1 < len(argv):
            opts["sdk"] = argv[i + 1]
            i += 2
        elif a == "--dist" and i + 1 < len(argv):
            opts["dist"] = argv[i + 1]
            i += 2
        elif a == "--clean":
            opts["clean"] = True
            i += 1
        elif a in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        else:
            _fail("未知参数: %s" % a)
    return opts


def resolve_sdk(sdk):
    if not sdk:
        _fail("未指定 OpenWrt SDK：请用 --sdk <目录>，"
              "或设置环境变量 OPENWRT_SDK。")
    sdk = os.path.abspath(sdk)
    if not os.path.isdir(sdk):
        _fail("SDK 目录不存在: %s" % sdk)
    if not (os.path.isfile(os.path.join(sdk, "rules.mk"))
            or os.path.isdir(os.path.join(sdk, "include"))):
        _fail("%s 看起来不是 OpenWrt SDK（缺 rules.mk / include/）。" % sdk)
    return sdk


def check_luci_feed(sdk):
    """luci-app-giwifi/Makefile 需要 $(TOPDIR)/feeds/luci/luci.mk。"""
    luci_mk = os.path.join(sdk, "feeds", "luci", "luci.mk")
    if not os.path.isfile(luci_mk):
        _fail("SDK 缺少 LuCI feed（%s）。\n"
              "请先在 SDK 中执行：\n"
              "  ./scripts/feeds update luci\n"
              "  ./scripts/feeds install -a -p luci" % luci_mk)


def _normalize_permissions(root):
    """Normalize modes after copying from a Windows/9p workspace.

    The LuCI package uses cp -pR, so source modes end up in the package.
    Directories must be 0755, ordinary files 0644 and the two backend
    executables 0755.
    """
    for base, dirs, files in os.walk(root):
        os.chmod(base, 0o755)

        for d in dirs:
            os.chmod(os.path.join(base, d), 0o755)

        for f in files:
            path = os.path.join(base, f)
            executable = (f == "giwifi-auth" and
                          ("/usr/bin/" in path or "/etc/init.d/" in path))
            os.chmod(path, 0o755 if executable else 0o644)


def sync_package(sdk, name):
    """把仓库内的包目录复制进 SDK 的 package/（覆盖旧副本）。"""
    src = os.path.join(ROOT, name)
    dst = os.path.join(sdk, "package", name)
    if not os.path.isdir(src):
        _fail("包目录不存在: %s" % src)
    if os.path.islink(dst) or os.path.isfile(dst):
        os.remove(dst)
    elif os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    _normalize_permissions(dst)
    print("  -> 已同步包目录到 SDK: %s" % dst)


# ---------------------------------------------------------------------------
# SDK 编译与产物收集
# ---------------------------------------------------------------------------
def run_make(sdk, targets):
    cmd = ["make"] + targets
    print("  $ (cd %s && %s)" % (sdk, " ".join(cmd)))
    try:
        subprocess.run(cmd, cwd=sdk, check=True)
    except FileNotFoundError:
        _fail("未找到 make。请在 Linux/WSL 环境安装 OpenWrt SDK 后执行"
              "（Windows 原生环境无法运行 SDK 构建）。")
    except subprocess.CalledProcessError as e:
        _fail("SDK 编译失败（退出码 %d），请查看上方日志。" % e.returncode)


def clean_sdk_artifacts(sdk):
    """Remove previous artifacts of the same packages from the SDK.

    luci.mk derives the translation package version from the po timestamp,
    so a rebuild otherwise leaves multiple luci-i18n-*.apk files behind.
    """
    for name in PKG_NAMES + I18N_PKGS:
        for ext in ("apk", "ipk"):
            pattern = os.path.join(sdk, "bin", "packages", "**",
                                   "%s[-_]*.%s" % (name, ext))
            for path in glob.glob(pattern, recursive=True):
                os.remove(path)
                print("  -> 清理旧产物: %s" % path)


def collect_artifacts(sdk, dist):
    """从 SDK 的 bin/packages 收集两个包及中文翻译包的产物（apk 或 ipk）。"""
    found = []
    for name in PKG_NAMES + I18N_PKGS:
        for ext in ("apk", "ipk"):
            # apk 产物名 <name>-<ver>-r<rel>.apk（连字符）；
            # ipk 产物名 <name>_<ver>_<arch>.ipk（下划线）。
            pat = os.path.join(sdk, "bin", "packages", "**",
                               "%s[-_]*.%s" % (name, ext))
            found.extend(glob.glob(pat, recursive=True))
    found = sorted(set(found))
    if not found:
        _fail("SDK 未产出 %s 包，请检查编译日志。"
              % " / ".join(PKG_NAMES + I18N_PKGS))
    os.makedirs(dist, exist_ok=True)
    for name in PKG_NAMES + I18N_PKGS:
        for ext in ("apk", "ipk"):
            for old in glob.glob(os.path.join(dist, "%s[-_]*.%s" % (name, ext))):
                os.remove(old)
    out = []
    for f in found:
        target = os.path.join(dist, os.path.basename(f))
        shutil.copy2(f, target)
        print("  -> %s (%d bytes)" % (target, os.path.getsize(target)))
        out.append(target)
    return out


def build_zip(ver, dist):
    """把仓库源码打包成 zip（排除 dist/隐藏目录/缓存）。"""
    out = os.path.join(dist, "openwrt-giwifi-%s.zip" % ver)
    skip = set(SKIP_DIRS)
    # --dist 可能指到仓库内部（如 .build-test）：必须跳过输出目录，
    # 否则 zip 会边写边把自己读进去，永远到不了 EOF。
    try:
        rel = os.path.relpath(os.path.abspath(dist), ROOT)
        if rel != "." and not rel.startswith(".."):
            skip.add(rel.split(os.sep)[0])
    except ValueError:
        pass
    out_abs = os.path.abspath(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs
                       if d not in skip and not d.startswith(".")]
            for fn in files:
                if fn.startswith(".") or os.path.splitext(fn)[1] in SKIP_EXT:
                    continue
                full = os.path.join(root, fn)
                if os.path.abspath(full) == out_abs:
                    continue
                rel = os.path.relpath(full, ROOT)
                arc = os.path.join("openwrt-giwifi", rel).replace("\\", "/")
                zf.write(full, arc)
    print("  -> %s (%d bytes)" % (out, os.path.getsize(out)))
    return out


def main():
    global DIST
    opts = parse_args(sys.argv[1:])
    DIST = os.path.abspath(opts["dist"])
    os.makedirs(DIST, exist_ok=True)

    versions = {}

    for name in PKG_NAMES:
        makefile = os.path.join(ROOT, name, "Makefile")
        versions[name] = parse_pkg_version(makefile)

    ui_ver = js_version(UI_VIEW)

    if len(set(list(versions.values()) + [ui_ver])) != 1:
        _fail("版本不一致：%s，LuCI 视图 %s"
              % (", ".join("%s=%s" % item for item in versions.items()), ui_ver))

    ver = ui_ver

    sdk = resolve_sdk(opts["sdk"])
    check_luci_feed(sdk)
    print("== 使用 OpenWrt SDK 构建 %s ==" % ", ".join(PKG_NAMES))

    for name in PKG_NAMES:
        sync_package(sdk, name)

    # Always refresh the package metadata: the package directories were just
    # copied into the SDK, and their package/... targets do not exist until
    # the metadata has been regenerated.
    run_make(sdk, ["defconfig"])

    targets = []
    if opts["clean"]:
        for name in PKG_NAMES:
            run_make(sdk, ["-C", os.path.join(sdk, "package", name),
                           "TOPDIR=" + sdk, "clean", "V=s"])

    # Compile each package through its own Makefile. This avoids pulling the
    # whole runtime dependency graph into the SDK (the SDK intentionally only
    # ships the target toolchain); the resulting packages are still produced
    # by the official package.mk/luci.mk machinery.
    clean_sdk_artifacts(sdk)

    for name in PKG_NAMES:
        run_make(sdk, ["-C", os.path.join(sdk, "package", name),
                       "TOPDIR=" + sdk, "compile", "V=s"])

    collect_artifacts(sdk, DIST)

    print("== 构建源码 zip ==")
    build_zip(ver, DIST)
    print("完成。产物目录: %s" % DIST)


if __name__ == "__main__":
    main()
