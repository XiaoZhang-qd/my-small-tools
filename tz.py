from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import datetime
import os
import sys
import argparse
import secrets
import signal
import threading
import time
import platform

main_server = None
admin_server = None
main_sock = None
admin_sock = None
log_file_path = ""
dd_mode = False
stop_flag = threading.Event()

if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PHANDLER_ROUTINE = ctypes.CFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def _win_ctrl_handler(ctrl_type):
        if ctrl_type == 0:  # CTRL_C_EVENT
            clean_shutdown()
        return True

    win_ctrl_callback = PHANDLER_ROUTINE(_win_ctrl_handler)

def get_next_seq(log_file: str) -> int:
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return len(lines) + 1
    return 1

def is_ipv6(ip_addr: str) -> bool:
    return ":" in ip_addr

class MainProbeHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, log_file, redirect_url, **kwargs):
        self.log_file = log_file
        self.redirect_url = redirect_url
        super().__init__(*args, **kwargs)

    def do_GET(self):
        client_ip = self.client_address[0]
        headers = dict(self.headers)
        xff = headers.get("X-Forwarded-For", "")
        if xff:
            client_ip = xff.split(",")[0].strip()
        ua = headers.get("User-Agent", "")
        ip_type = "IPv6" if is_ipv6(client_ip) else "IPv4"
        now = str(datetime.datetime.now())
        seq = get_next_seq(self.log_file)

        record = {
            "seq": seq,
            "time": now,
            "client_ip": client_ip,
            "ip_type": ip_type,
            "user_agent": ua,
            "raw_headers": dict(headers)
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.send_response(302)
        self.send_header("Location", self.redirect_url)
        self.end_headers()

class AdminLogHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, log_file, secret_key, **kwargs):
        self.log_file = log_file
        self.secret_key = secret_key
        super().__init__(*args, **kwargs)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        input_key = qs.get("key", [""])[0]
        detail_seq = qs.get("detail", [""])[0]

        if input_key != self.secret_key:
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>403 Forbidden - Wrong Access Key</h1>")
            return

        if detail_seq:
            rows = []
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            rows.append(json.loads(line))
                        except:
                            continue
            target = None
            for r in rows:
                if str(r.get("seq")) == detail_seq:
                    target = r
                    break
            if target:
                html = f'''
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>pre{{white-space:pre-wrap;}}</style>
</head>
<body>
<h1>完整记录 #{detail_seq}</h1>
<pre>{json.dumps(target, ensure_ascii=False, indent=2)}</pre>
<br><a href="?key={input_key}">← 返回列表</a>
</body>
</html>'''
            else:
                html = f'<h1>记录不存在</h1><a href="?key={input_key}">← 返回</a>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        rows = []
        if os.path.exists(self.log_file):
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except:
                        continue
        rows = reversed(rows)
        html = '''
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
table{width:100%;border-collapse:collapse;font-size:12px;}
td,th{border:1px #ccc solid;padding:6px;}
th{background:#222;color:#fff;}
button{cursor:pointer}
</style>
</head>
<body>
<h1>IP探针日志面板</h1>
<table>
<tr>
<th>序号</th><th>时间</th><th>IP</th><th>类型</th><th>UA</th><th>操作</th>
</tr>'''
        for item in rows:
            seq = item["seq"]
            t = item["time"]
            ip = item["client_ip"]
            itype = item["ip_type"]
            ua = item["user_agent"][:80]
            html += f'''
<tr>
<td>{seq}</td><td>{t}</td><td>{ip}</td><td>{itype}</td><td>{ua}</td>
<td><button onclick="location.href='?key={input_key}&detail={seq}'">查看全部信息</button></td>
</tr>'''
        html += "</table></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

def create_main_server(bind, port, log, redirect):
    def handler(*args, **kw):
        return MainProbeHandler(*args, log_file=log, redirect_url=redirect, **kw)
    return HTTPServer((bind, port), handler)

def create_admin_server(bind, port, log, key):
    def handler(*args, **kw):
        return AdminLogHandler(*args, log_file=log, secret_key=key, **kw)
    return HTTPServer((bind, port), handler)

def clean_shutdown():
    global main_server, admin_server, main_sock, admin_sock, log_file_path, dd_mode
    if stop_flag.is_set():
        return
    stop_flag.set()
    print("\n🛑 收到终止信号，正在关闭服务...")
    if main_sock:
        try:
            main_sock.close()
        except Exception: pass
    if admin_sock:
        try:
            admin_sock.close()
        except Exception: pass
    if main_server:
        try:
            main_server.shutdown()
        except Exception: pass
    if admin_server:
        try:
            admin_server.shutdown()
        except Exception: pass
    if dd_mode and os.path.exists(log_file_path):
        try:
            os.remove(log_file_path)
            print(f"🗑️ --dd模式：日志 {log_file_path} 已删除")
        except Exception as e:
            print(f"⚠️ 删除日志失败：{e}")
    else:
        print(f"✅ 日志正常保存：{log_file_path}")
    print("✅ 程序完全退出")
    sys.exit(0)

def sigint_handler(signum, frame):
    clean_shutdown()

def main():
    global main_server, admin_server, main_sock, admin_sock, log_file_path, dd_mode
    parser = argparse.ArgumentParser(description="IP探针工具", add_help=False)
    parser.add_argument("-h", "-H", "--help", action="help", help="查看帮助")
    parser.add_argument("-b", "-B", "--bind", default="0.0.0.0", help="监听IP 0.0.0.0/127.0.0.1")
    parser.add_argument("-p", "-P", "--port", type=int, default=8080, help="主探针端口")
    parser.add_argument("-ap", "-AP", "--admin-port", type=int, default=8081, help="日志面板端口")
    parser.add_argument("--log", default="probe_log.txt", help="日志文件名")
    parser.add_argument("--redirect", default="https://ifconfig.io", help="访问后跳转地址")
    parser.add_argument("-pw", "-PW", "--pw", help="自定义后台密钥")
    parser.add_argument("-rkl", "-RKL", "--rand-key-len", type=int, default=16, help="随机密钥长度")
    parser.add_argument("--dd", action="store_true", help="退出自动删除日志")
    args = parser.parse_args()

    log_file_path = args.log
    dd_mode = args.dd

    if args.pw:
        admin_key = args.pw
    else:
        admin_key = secrets.token_urlsafe(args.rand_key_len)
        print(f"⚠️ 自动生成后台密钥：{admin_key}")

    main_server = create_main_server(args.bind, args.port, args.log, args.redirect)
    admin_server = create_admin_server(args.bind, args.admin_port, args.log, admin_key)
    main_sock = main_server.socket
    admin_sock = admin_server.socket

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)
    if platform.system() == "Windows":
        kernel32.SetConsoleCtrlHandler(win_ctrl_callback, True)

    def run_main():
        try:
            main_server.serve_forever(poll_interval=0.05)
        except Exception: pass
    def run_admin():
        try:
            admin_server.serve_forever(poll_interval=0.05)
        except Exception: pass

    t1 = threading.Thread(target=run_main, daemon=True)
    t2 = threading.Thread(target=run_admin, daemon=True)
    t1.start()
    t2.start()

    print(f"✅ 主探针地址：http://{args.bind}:{args.port} → 跳转 {args.redirect}")
    print(f"✅ 日志面板地址：http://{args.bind}:{args.admin_port}/?key={admin_key}")
    print(f"📄 日志文件：{args.log}")
    if args.dd:
        print("🗑️ 开启--dd，退出会删除日志")
    print("🛑 按下一次 Ctrl+C 即可关闭程序\n")

    try:
        while not stop_flag.is_set():
            time.sleep(0.05)
    except KeyboardInterrupt:
        clean_shutdown()

if __name__ == "__main__":
    main()
