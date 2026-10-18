# -*- coding: utf-8 -*-
"""giwifi-auth 的单元 / 端到端测试（本地 mock Portal）。

既可直接运行（python test/test_openwrt_auth.py），也可被 pytest 收集。
所有子进程输出按 UTF-8 解码，避免 Windows 默认 GBK 导致测试崩溃。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.dont_write_bytecode = True

KEY = b"1234567887654321"
IV = "2b1df7114d9ea781"
RAW_SIGN = ("WKGHRyOs4ZDeDKFxNTZMBVDq5PBScgUYQmG0AQFcPBzN%2FILxKvukDnWOOQcoYFzFninNdme8f9X0bJemG3%2F5%2Fw%3D%3D")

# ---- 独立 AES-128-CBC 解密（校验脚本加密结果）----
SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]
INV = [0] * 256
for _i in range(256):
    INV[SBOX[_i]] = _i
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xt(a):
    a &= 0xff
    return ((a << 1) ^ (0x1b if a & 0x80 else 0)) & 0xff


def _gm(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = _xt(a)
        b >>= 1
    return r & 0xff


def _exp(key):
    w = [list(key[4 * i:4 * i + 4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    rk = []
    for i in range(44):
        rk.extend(w[i])
    return rk


def _dec(state, rk):
    st = [state[j] ^ rk[160 + j] for j in range(16)]
    for rnd in range(9, -1, -1):
        st = [st[0], st[13], st[10], st[7], st[4], st[1], st[14], st[11],
              st[8], st[5], st[2], st[15], st[12], st[9], st[6], st[3]]
        st = [INV[b] for b in st]
        st = [st[j] ^ rk[16 * rnd + j] for j in range(16)]
        if rnd > 0:
            out = [0] * 16
            for c in range(4):
                col = st[4 * c:4 * c + 4]
                out[4 * c + 0] = _gm(0x0e, col[0]) ^ _gm(0x0b, col[1]) ^ _gm(0x0d, col[2]) ^ _gm(0x09, col[3])
                out[4 * c + 1] = _gm(0x09, col[0]) ^ _gm(0x0e, col[1]) ^ _gm(0x0b, col[2]) ^ _gm(0x0d, col[3])
                out[4 * c + 2] = _gm(0x0d, col[0]) ^ _gm(0x09, col[1]) ^ _gm(0x0e, col[2]) ^ _gm(0x0b, col[3])
                out[4 * c + 3] = _gm(0x0b, col[0]) ^ _gm(0x0d, col[1]) ^ _gm(0x09, col[2]) ^ _gm(0x0e, col[3])
            st = out
    return st


def cbc_dec(ct, key, iv):
    rk = _exp(key)
    prev = list(iv)
    out = []
    for i in range(0, len(ct), 16):
        blk = list(ct[i:i + 16])
        d = _dec(blk, rk)
        out.extend(d[j] ^ prev[j] for j in range(16))
        prev = blk
    return bytes(out)


SCRIPT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "giwifi-auth", "files", "usr", "bin", "giwifi-auth"))

FIELDS = (
    '<form id="frmLogin" role="form">'
    '<input type="hidden" name="nasName" value="LITBAS1"/>'
    '<input type="hidden" name="nasIp" value=""/>'
    '<input type="hidden" name="userIp" value="10.50.240.101"/>'
    '<input type="hidden" name="userMac" value=""/>'
    '<input type="hidden" name="ssid" value=""/>'
    '<input type="hidden" name="apMac" value=""/>'
    '<input type="hidden" name="pid" value="23"/>'
    '<input type="hidden" name="vlan" value=""/>'
    '<input type="hidden" name="sign" value="' + RAW_SIGN + '"/>'
    '<input type="hidden" name="iv" id="iv" value="' + IV + '"/>'
    '<input type="hidden" name="redirectUrl" id="redirectUrl" value="http://1.2.3.4"/>'
    '<input type="hidden" name="portalTemplateId" value="23"/>'
    '<input type="hidden" name="account_type" value="">'
    '<input name="name" type="text" value=""/>'
    '<input name="password" type="password" value=""/>'
    '<input id="remember" name="remember" type="checkbox" value="0">'
    '</form>'
    '<script>function login(){var msg=cryptoEncode($("#frmLogin").serialize());'
    '$.ajax({url:"/gportal/web/authLogin?round="+Math.round(Math.random()*1000),data:msg,type:"post"});}</script>'
)


class Portal(BaseHTTPRequestHandler):
    """单文件 mock Portal：登录页 + authLogin / queryAuthState / authLogout / reBindMac。"""
    online = True
    mode = "ok"          # ok / rebind / no_rebind
    auth_count = 0
    rebind_count = 0
    captured = {}

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.captured["get_ua"] = self.headers.get("User-Agent", "")
        self._send(200, "text/html; charset=utf-8", FIELDS.encode(),
                   extra={"Set-Cookie": "PHPSESSID=owrt12345; path=/"})

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(ln).decode("utf-8")
        self.captured["post_ua"] = self.headers.get("User-Agent", "")
        qs = urllib.parse.parse_qs(raw)
        if self.path.startswith("/gportal/web/authLogin"):
            Portal.auth_count += 1
            self.captured["login_body"] = raw
            data = base64.b64decode(qs.get("data", [""])[0])
            pt = cbc_dec(data, KEY, qs.get("iv", [""])[0].encode())
            self.captured["plaintext"] = pt.rstrip(b"\x00").decode("utf-8")
            if Portal.mode == "rebind" and Portal.auth_count == 1:
                resp = {"data": {"resultCode": 2, "reasoncode": 43,
                                 "bindmac": "aa:bb:cc:dd:ee:ff"},
                        "info": "该账号已绑定过其他同类型设备，是否重新绑定至当前设备？",
                        "status": 0}
            elif Portal.mode == "no_rebind":
                resp = {"data": {"resultCode": 2, "reasoncode": 41},
                        "info": "需要先绑定手机号", "status": 0}
            else:
                resp = {"status": 1, "info": "登录成功"}
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(resp, ensure_ascii=False).encode())
        elif self.path.startswith("/gportal/web/queryAuthState"):
            self.captured["qas_body"] = raw
            if Portal.online:
                resp = {"data": {"resultCode": 0,
                                 "data": {"authState": 2, "onlineTime": 1234}},
                        "info": "", "status": 1}
            else:
                resp = {"data": {"resultCode": 0},
                        "info": "", "status": 0}
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(resp).encode())
        elif self.path.startswith("/gportal/web/authLogout"):
            self._send(200, "application/json; charset=utf-8",
                       json.dumps({"status": 1, "info": "已下线"},
                                  ensure_ascii=False).encode())
        elif self.path.startswith("/gportal/web/reBindMac"):
            Portal.rebind_count += 1
            self._send(200, "application/json; charset=utf-8",
                       json.dumps({"data": 1, "info": "已绑定成功,请重新点击认证",
                                   "status": 1}, ensure_ascii=False).encode())
        else:
            self._send(200, "application/json; charset=utf-8",
                       json.dumps({"status": 0, "info": "not found"}).encode())


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), Portal)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _write_uci(path, accounts, main_opts=None):
    """生成临时 UCI 配置文件（多账号结构）。"""
    def q(v):
        return str(v).replace("'", "'\\''")

    lines = ["config giwifi 'main'"]
    main_opts = main_opts or {}
    lines.append("\toption enabled '1'")
    lines.append("\toption base_url '%s'" % q(main_opts.get("base_url", "")))
    lines.append("\toption interval '%s'" % main_opts.get("interval", "10"))
    lines.append("\toption iface_restart_enabled '0'")
    lines.append("\toption iface_restart_time '04:00'")
    lines.append("\toption iface_restart_cron '0 4 * * *'")
    lines.append("")
    for i, acc in enumerate(accounts):
        name = acc.get("name")
        if name:
            lines.append("config account '%s'" % q(name))
        else:
            # 与 libuci 落盘一致：匿名段不写段名
            lines.append("config account")
        lines.append("\toption enabled '1'")
        lines.append("\toption interface '%s'" % q(acc.get("interface", "lo")))
        lines.append("\toption username '%s'" % q(acc.get("username", "")))
        lines.append("\toption password '%s'" % q(acc.get("password", "")))
        lines.append("\toption device_type '%s'" % acc.get("device_type", "windows"))
        lines.append("\toption device_ua '%s'" % q(acc.get("device_ua", "")))
        lines.append("\toption auto_rebind '%s'" % acc.get("auto_rebind", "0"))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _run(args, uci_path, log_path, timeout=90):
    env = dict(os.environ,
               GIWIFI_UCI_PATH=uci_path,
               GIWIFI_LOG_PATH=log_path,
               PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, SCRIPT] + args, env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def _load_module():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("giwifi_auth_mod", SCRIPT)
    spec = importlib.util.spec_from_loader("giwifi_auth_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# pytest / 手工运行共用测试
# ---------------------------------------------------------------------------
def test_uci_parse():
    """UCI 引号/转义、匿名段（config account 无段名）解析。"""
    mod = _load_module()
    cases = {
        "config test 't'\noption username 'abc'":
            {"t": {"username": "abc"}},
        "config test 't'\noption password 'a'\\''b'":
            {"t": {"password": "a'b"}},
        'config test \'t\'\noption p2 "x\\"y"':
            {"t": {"p2": 'x"y'}},
        "config test 't'\noption p3 plain":
            {"t": {"p3": "plain"}},
        "config test 't'\noption empty ''":
            {"t": {"empty": ""}},
        "config account\noption username 'u1'":
            {"@account[0]": {"username": "u1"}},
        "config account\noption username 'u1'\nconfig account\noption username 'u2'":
            {"@account[0]": {"username": "u1"},
             "@account[1]": {"username": "u2"}},
    }
    for text, expect in cases.items():
        fd, path = tempfile.mkstemp(suffix=".uci")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            got = mod._load_uci_config(path)
            got = {k: {o: v for o, v in sec.items() if o != ".type"}
                   for k, sec in got.items()}
            assert got == expect, "%r -> %r != %r" % (text, got, expect)
        finally:
            os.unlink(path)


def test_account_targeting():
    """按段名 / 用户名 / 绑定接口解析账号（前端对匿名段传接口）。"""
    mod = _load_module()
    a = mod.Account("s1", "eth0", "u1", "p1")
    b = mod.Account("s2", "eth1", "u2", "p2")
    accounts = [a, b]
    assert mod._accounts_matching(accounts, "eth0") == [a]
    assert mod._accounts_matching(accounts, "u2") == [b]
    assert mod._accounts_matching(accounts, "s1") == [a]
    assert mod._resolve_accounts(accounts, "eth1") == [b]
    assert mod._resolve_accounts(accounts, "nope") == []


def test_iface_ipv4():
    """_iface_ipv4：空串/不存在接口返回空串且不抛异常（跨平台安全）。"""
    mod = _load_module()
    assert mod._iface_ipv4("") == ""
    assert mod._iface_ipv4("giwifi-no-such-iface") == ""


def test_iface_ready():
    """_iface_ready：未绑定接口视为就绪；不存在接口返回不可用+原因。"""
    mod = _load_module()
    assert mod._iface_ready("") == (True, "")
    ready, why = mod._iface_ready("giwifi-no-such-iface")
    assert ready is False and why


def test_login_flow():
    """authLogin：明文表单编码、sign 双编码、UA。"""
    srv = _serve()
    Portal.online = False
    Portal.mode = "ok"
    Portal.auth_count = 0
    Portal.captured = {}
    fd, uci_path = tempfile.mkstemp(suffix=".uci")
    os.close(fd)
    log_path = uci_path + ".log"
    try:
        _write_uci(uci_path, [
            {"name": "t1", "username": "13800001111",
             "password": "P@ss 12#9", "device_type": "windows"},
        ], {"base_url": "http://127.0.0.1:%d" % srv.server_port,
            "interval": "10"})
        r = _run(["login"], uci_path, log_path)
        assert r.returncode == 0, r.stdout + r.stderr
        pt = Portal.captured.get("plaintext", "")
        assert "name=13800001111" in pt
        assert "password=P%40ss%2012%239" in pt
        assert "%252F" in pt
        assert "iv=2b1df7114d9ea781" in pt
        assert "userIp=10.50.240.101" in pt
        assert "Windows NT" in Portal.captured.get("get_ua", "")
        assert "Windows NT" in Portal.captured.get("post_ua", "")
    finally:
        srv.shutdown()
        srv.server_close()
        for p in (uci_path, log_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def test_check_online():
    srv = _serve()
    Portal.online = True
    fd, uci_path = tempfile.mkstemp(suffix=".uci")
    os.close(fd)
    log_path = uci_path + ".log"
    try:
        _write_uci(uci_path, [
            {"username": "13800001111", "password": "x", "interface": "lo"},
        ], {"base_url": "http://127.0.0.1:%d" % srv.server_port})
        r = _run(["check"], uci_path, log_path, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "在线" in r.stdout
        assert Portal.captured.get("qas_body", "").startswith("userIp=")
    finally:
        srv.shutdown()
        srv.server_close()
        for p in (uci_path, log_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def test_device_type_ua():
    srv = _serve()
    Portal.online = False
    fd, uci_path = tempfile.mkstemp(suffix=".uci")
    os.close(fd)
    log_path = uci_path + ".log"
    try:
        for dt, needle in (("windows", "Windows NT"),
                           ("android", "Android"),
                           ("iphone", "iPhone")):
            Portal.captured = {}
            _write_uci(uci_path, [
                {"username": "13800001111", "password": "x",
                 "device_type": dt},
            ], {"base_url": "http://127.0.0.1:%d" % srv.server_port})
            r = _run(["login"], uci_path, log_path, timeout=60)
            assert r.returncode == 0, r.stdout + r.stderr
            assert needle in Portal.captured.get("post_ua", ""), dt
    finally:
        srv.shutdown()
        srv.server_close()
        for p in (uci_path, log_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def test_rebind_flow():
    """reasoncode：43=设备换绑应触发 reBindMac；41=绑定手机号不得误触发。"""
    srv = _serve()
    Portal.online = False
    fd, uci_path = tempfile.mkstemp(suffix=".uci")
    os.close(fd)
    log_path = uci_path + ".log"
    try:
        _write_uci(uci_path, [
            {"username": "13800001111", "password": "P@ss 12#9",
             "device_type": "windows", "auto_rebind": "1"},
        ], {"base_url": "http://127.0.0.1:%d" % srv.server_port})
        # A: reasoncode=43 -> 自动换绑并重新认证成功
        Portal.mode, Portal.auth_count, Portal.rebind_count = "rebind", 0, 0
        r = _run(["login"], uci_path, log_path, timeout=90)
        assert r.returncode == 0, r.stdout + r.stderr
        assert Portal.rebind_count == 1
        assert Portal.auth_count == 2
        assert "已换绑" in r.stdout
        # B: reasoncode=41（绑定手机号）-> 不得触发 reBindMac
        Portal.mode, Portal.auth_count, Portal.rebind_count = "no_rebind", 0, 0
        r = _run(["login"], uci_path, log_path, timeout=60)
        assert r.returncode == 1, r.stdout + r.stderr
        assert Portal.rebind_count == 0
        assert "reasoncode=41" in r.stdout
        assert "绑定手机号" in r.stdout
    finally:
        srv.shutdown()
        srv.server_close()
        for p in (uci_path, log_path):
            try:
                os.unlink(p)
            except OSError:
                pass


TEST_FUNCS = [
    ("uci-parse", test_uci_parse),
    ("account-targeting", test_account_targeting),
    ("iface-ipv4", test_iface_ipv4),
    ("iface-ready", test_iface_ready),
    ("login-flow", test_login_flow),
    ("check-online", test_check_online),
    ("device-type-ua", test_device_type_ua),
    ("rebind-flow", test_rebind_flow),
]


def main():
    """直接运行：逐项执行并汇总（pytest 下不会调用）。"""
    failed = 0
    for name, fn in TEST_FUNCS:
        try:
            fn()
            print("  PASS %s" % name)
        except Exception as e:  # noqa: BLE001 - 手工运行时汇总所有失败
            failed += 1
            print("  FAIL %s: %s" % (name, e))
    print("\nRESULT:", "ALL_PASS" if failed == 0 else "HAS_FAILURE")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
