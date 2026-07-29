#!/usr/bin/env python3
import argparse
import random
import sys
import time
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import threading
import requests
import base64
import subprocess

# 永久兼容本地文件 / python3 - / python3 -c 三种运行模式
try:
    SCRIPT_NAME = os.path.basename(__file__)
except NameError:
    SCRIPT_NAME = "daili.py"

# 全局存储当前选中的代理
current_proxy = {"type": None, "url": None}
# 全局本地代理鉴权
local_auth = {"user": None, "pass": None}

# 简易本地代理转发处理器（增加Basic Auth校验）
class ProxyHandler(BaseHTTPRequestHandler):
    def check_auth(self):
        # 未配置本地账号密码，直接放行
        if not local_auth["user"] or not local_auth["pass"]:
            return True
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return False
        # 解析base64账号密码
        auth_data = base64.b64decode(auth_header.replace("Basic ", "").strip()).decode("utf-8")
        req_user, req_pass = auth_data.split(":", 1)
        return req_user == local_auth["user"] and req_pass == local_auth["pass"]

    def do_all(self):
        # 鉴权校验失败
        if not self.check_auth():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Local Proxy Auth"')
            self.end_headers()
            self.wfile.write(b"Proxy auth required, format: user:pass@127.0.0.1:8899")
            return
        if not current_proxy["url"]:
            self.send_error(503, "No upstream proxy selected")
            return
        proxy_url = current_proxy["url"]
        try:
            headers = dict(self.headers)
            body = None
            if self.command == "POST":
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len)
            resp = requests.request(
                self.command,
                self.path,
                proxies={
                    "http": proxy_url,
                    "https": proxy_url
                },
                headers=headers,
                data=body,
                timeout=10
            )
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_error(502, f"Proxy forward failed: {str(e)}")
    do_GET = do_all
    do_POST = do_all

def start_local_proxy(listen_ip, listen_port):
    """启动本地中转代理服务"""
    server = HTTPServer((listen_ip, listen_port), ProxyHandler)
    # 打印带鉴权的本地代理地址
    if local_auth["user"] and local_auth["pass"]:
        addr_str = f"{local_auth['user']}:{local_auth['pass']}@{listen_ip}:{listen_port}"
    else:
        addr_str = f"{listen_ip}:{listen_port}"
    print(f"[{SCRIPT_NAME}] [LOCAL PROXY] Listening on {addr_str}, upstream proxy auto refresh")
    try:
        server.serve_forever()
    except Exception:
        server.shutdown()

def load_proxy_source(source: str) -> list:
    """
    统一加载代理池，支持三种输入：
    1. "-" 从标准输入读取
    2. http/https URL 网络远程代理文本
    3. 本地文件路径
    """
    raw_lines = []
    if source == "-":
        raw_data = sys.stdin.read()
        raw_lines = raw_data.splitlines()
    elif source.startswith("http://") or source.startswith("https://"):
        try:
            resp = requests.get(source, timeout=8)
            resp.raise_for_status()
            raw_lines = resp.text.splitlines()
        except Exception as e:
            print(f"[{SCRIPT_NAME}] ERROR: Fetch proxy url failed: {e}", file=sys.stderr)
            return []
    else:
        try:
            with open(source, "r", encoding="utf-8") as f:
                raw_lines = [line.rstrip("\n") for line in f]
        except Exception as e:
            print(f"[{SCRIPT_NAME}] WARNING: read file failed: {e}", file=sys.stderr)
            return []
    raw = [ln for ln in raw_lines if ln.strip() != ""]
    processed = []
    for line in raw:
        processed.append(line.strip())
    return processed

def parse_proxy_line(line: str, scheme: str, global_user: str = None, global_pass: str = None) -> str:
    """
    解析单行上游代理，支持格式：
    1. ip:port
    2. user:pass@ip:port
    3. http://xxx / socks5://xxx 完整链接
    """
    if "://" in line:
        return line
    if "@" in line:
        auth_part, addr_part = line.split("@", 1)
        return f"{scheme}://{auth_part}@{addr_part}"
    if global_user and global_pass:
        return f"{scheme}://{global_user}:{global_pass}@{line}"
    else:
        return f"{scheme}://{line}"

def main():
    parser = argparse.ArgumentParser(
        description="daili.py - pick proxy from file/url/stdin + local forward server",
        prog="daili.py"
    )
    parser.add_argument(
        "-f", "--file",
        help="proxy source: local file path / http(s) url / '-' read from stdin"
    )
    parser.add_argument("-m", "--mode", choices=["random", "seq"], help="pick mode: random / seq")
    parser.add_argument("--filter", choices=["all", "http-only", "socks-only"], help="filter type")
    parser.add_argument("--default-scheme", choices=["http", "socks5"], default="http", help="scheme for lines without ://, default=http")
    parser.add_argument("--loop", type=int, default=0, help="loop refresh interval(second), 0 = once")
    parser.add_argument("--export-env", action="store_true", help="output shell env format for eval")
    parser.add_argument("--use-env-proxy", action="store_true", help="read system HTTP_PROXY/ALL_PROXY into proxy pool")
    # 上游代理全局账号密码
    parser.add_argument("--proxy-user", type=str, help="global upstream proxy auth username")
    parser.add_argument("--proxy-pass", type=str, help="global upstream proxy auth password")
    # 本地中转代理配置
    parser.add_argument("--local-proxy", action="store_true", help="start local global proxy server")
    parser.add_argument("--local-ip", default="127.0.0.1", help="local proxy listen ip, default 127.0.0.1")
    parser.add_argument("--local-port", type=int, default=8899, help="local proxy listen port, default 8899")
    # 新增：本地代理鉴权账号密码
    parser.add_argument("--local-user", type=str, help="local proxy auth username")
    parser.add_argument("--local-pass", type=str, help="local proxy auth password")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    args = parser.parse_args()

    # 全局保存本地代理鉴权信息
    local_auth["user"] = args.local_user
    local_auth["pass"] = args.local_pass

    def pick_one():
        proxy_pool = []
        if args.file:
            raw_proxy_lines = load_proxy_source(args.file)
            processed = []
            for line in raw_proxy_lines:
                full_url = parse_proxy_line(
                    line,
                    args.default_scheme,
                    args.proxy_user,
                    args.proxy_pass
                )
                processed.append(full_url)
            proxy_pool.extend(processed)
        if args.use_env_proxy:
            env_proxy = os.getenv("ALL_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            if env_proxy:
                full_url = parse_proxy_line(
                    env_proxy,
                    args.default_scheme,
                    args.proxy_user,
                    args.proxy_pass
                )
                proxy_pool.append(full_url)
        filtered = []
        for item in proxy_pool:
            if args.filter == "all":
                filtered.append(item)
            elif args.filter == "http-only":
                if item.startswith("http://"):
                    filtered.append(item)
            elif args.filter == "socks-only":
                if item.startswith("socks5://"):
                    filtered.append(item)
        if len(filtered) == 0:
            print(f"[{SCRIPT_NAME}] ERROR: no proxy match filter (source empty or filtered out)", file=sys.stderr)
            return None, None
        if args.mode == "random":
            picked = random.choice(filtered)
        else:
            picked = filtered[0]
        if picked.startswith("http://"):
            ptype = "http"
        elif picked.startswith("socks5://"):
            ptype = "socks5"
        else:
            ptype = "unknown"
        return ptype, picked

    # ===================== 放在main内部，args正常访问 =====================
    def print_result(ptype, url):
        current_proxy["type"] = ptype
        current_proxy["url"] = url
        if args.export_env:
            shell = "unix"
            if sys.platform == "win32":
                shell = "win_unknown"
                ppid = os.getppid()
                try:
                    res = subprocess.check_output(
                        ["wmic", "process", f"where ProcessId={ppid}", "get", "ExecutablePath", "/value"],
                        text=True, encoding="gbk", errors="ignore"
                    )
                    exe_name = None
                    for line in res.splitlines():
                        line = line.strip()
                        if line.startswith("ExecutablePath="):
                            path = line.split("=", 1)[1]
                            exe_name = path.split("\\")[-1].lower() if path else None
                            break
                    if exe_name == "cmd.exe":
                        shell = "cmd"
                    elif exe_name in ("powershell.exe", "pwsh.exe"):
                        shell = "powershell"
                except Exception:
                    pass

            if shell == "cmd":
                print(f'HTTP_PROXY={url}')
                print(f'HTTPS_PROXY={url}')
                print(f'ALL_PROXY={url}')
                print(f'PROXY_URL={url}')
            elif shell == "powershell":
                print(f'$env:HTTP_PROXY="{url}"')
                print(f'$env:HTTPS_PROXY="{url}"')
                print(f'$env:ALL_PROXY="{url}"')
                print(f'$env:PROXY_URL="{url}"')
            else:
                print(f'HTTP_PROXY="{url}"')
                print(f'HTTPS_PROXY="{url}"')
                print(f'ALL_PROXY="{url}"')
                print(f'PROXY_URL="{url}"')
        else:
            print(f"TYPE={ptype}")
            print(f"PROXY_URL={url}")

    # 启动本地代理线程
    local_proxy_thread = None
    if args.local_proxy:
        local_proxy_thread = threading.Thread(
            target=start_local_proxy,
            args=(args.local_ip, args.local_port),
            daemon=True
        )
        local_proxy_thread.start()
        print(f"[{SCRIPT_NAME}] [INFO] Local proxy service started")

    # 主循环
    try:
        while True:
            ptype, url = pick_one()
            if ptype and url:
                print_result(ptype, url)
            if args.loop <= 0:
                break
            time.sleep(args.loop)
    except KeyboardInterrupt:
        print(f"\n[{SCRIPT_NAME}] [EXIT] User stop program, exit normally")
        sys.exit(0)

if __name__ == "__main__":
    main()