from http.server import HTTPServer, BaseHTTPRequestHandler
import hashlib
import sqlite3
import urllib.parse
import time
import sys
import re
import random

DEFAULT_BIND_IP = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin123"
DEFAULT_DAILY_LIMIT = 20
DEFAULT_HASH_LEN = 8
DB_FILE = "url_system.db"
SESSION_EXPIRE = 86400
DEFAULT_ACCESS_LOG = True

def print_help():
    help_text = """
哈希URL混淆加密+短链接服务 帮助文档
功能：将原始URL生成MD5哈希混淆加密短链接，访问哈希地址302跳转原链接
支持多用户、管理员权限、每日生成次数限制、账号管理、后台自定义哈希字符长度

启动参数：
    -h / --help          打印本帮助信息并退出
    --bind-ip / -i IP         指定监听IP，默认 0.0.0.0（全部网卡）
    --port / -p 数字          指定服务端口，默认8080
    --admin-user / -au 账号    初始化管理员账号，默认admin
    --admin-pass / -ap 密码    初始化管理员账号，默认admin
    --default-limit / -dl 数字 新建用户默认每日生成短链上限，默认20
    --no-access-log / -nal      关闭访问日志输出，默认开启

示例：
    python3 urljm.py -h
    python3 urljm.py --bind-ip 192.168.1.100 --port 9000 --admin-user root --admin-pass 666666 --default-limit 50
    python3 urljm.py --no-access-log

访问地址说明：
    /login        用户登录页面
    /user_panel   普通用户面板（生成加密短链、查看自有链接）
    /admin        管理员后台（管理账号、调整用户限额、设置哈希加密字符长度）
    /logout       退出登录
    /xxxxxxxx     N位哈希加密短链，自动302重定向至原URL
"""
    print(help_text)
    sys.exit(0)

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def validate_username(username):
    if not username or len(username) < 3 or len(username) > 20:
        return False, "用户名长度需在3-20字符之间"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含字母、数字和下划线"
    return True, ""

def validate_password(password):
    if not password or len(password) < 6:
        return False, "密码长度至少6位"
    return True, ""

def validate_url(url):
    if not url:
        return False, "URL不能为空"
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "URL必须以http://或https://开头"
    if len(url) > 2048:
        return False, "URL长度不能超过2048字符"
    return True, ""

def init_db(init_admin_user, init_admin_pass, init_default_limit):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            pass_hash TEXT NOT NULL,
            daily_max INTEGER NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS links (
            hash_code TEXT PRIMARY KEY,
            original_url TEXT NOT NULL,
            create_user TEXT NOT NULL,
            create_date TEXT NOT NULL,
            FOREIGN KEY(create_user) REFERENCES users(username)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            expire_ts INTEGER NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS sys_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        cur.execute("SELECT value FROM sys_config WHERE key='hash_len'")
        if not cur.fetchone():
            cur.execute("INSERT INTO sys_config (key, value) VALUES ('hash_len', ?)", (str(DEFAULT_HASH_LEN),))
        cur.execute("SELECT value FROM sys_config WHERE key='return_limit_on_delete'")
        if not cur.fetchone():
            cur.execute("INSERT INTO sys_config (key, value) VALUES ('return_limit_on_delete', '1')")
        cur.execute("SELECT value FROM sys_config WHERE key='visitor_mode_enabled'")
        if not cur.fetchone():
            cur.execute("INSERT INTO sys_config (key, value) VALUES ('visitor_mode_enabled', '0')")
        cur.execute("SELECT value FROM sys_config WHERE key='visitor_daily_limit'")
        if not cur.fetchone():
            cur.execute("INSERT INTO sys_config (key, value) VALUES ('visitor_daily_limit', '10')")
        cur.execute("SELECT username FROM users WHERE username=?", (init_admin_user,))
        if not cur.fetchone():
            admin_pass_hash = get_str_hash(init_admin_pass)
            cur.execute(
                "INSERT INTO users (username, pass_hash, daily_max, is_admin) VALUES (?,?,?,1)",
                (init_admin_user, admin_pass_hash, init_default_limit)
            )
        conn.commit()
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        sys.exit(1)
    finally:
        conn.close()

def get_sys_hash_len() -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM sys_config WHERE key='hash_len'")
        res = cur.fetchone()
        if res and res[0].isdigit():
            return int(res[0])
    except Exception as e:
        print(f"获取哈希长度失败: {e}")
    finally:
        conn.close()
    return DEFAULT_HASH_LEN

def set_sys_hash_len(new_len: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE sys_config SET value=? WHERE key='hash_len'", (str(new_len),))
        conn.commit()
    except Exception as e:
        print(f"设置哈希长度失败: {e}")
    finally:
        conn.close()

def get_return_limit_on_delete() -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM sys_config WHERE key='return_limit_on_delete'")
        res = cur.fetchone()
        if res:
            return res[0] == '1'
    except Exception as e:
        print(f"获取删除返还配置失败: {e}")
    finally:
        conn.close()
    return True

def set_return_limit_on_delete(value: bool):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE sys_config SET value=? WHERE key='return_limit_on_delete'", ('1' if value else '0',))
        conn.commit()
    except Exception as e:
        print(f"设置删除返还配置失败: {e}")
    finally:
        conn.close()

def get_visitor_mode_enabled() -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM sys_config WHERE key='visitor_mode_enabled'")
        res = cur.fetchone()
        if res:
            return res[0] == '1'
    except Exception as e:
        print(f"获取游客模式配置失败: {e}")
    finally:
        conn.close()
    return False

def set_visitor_mode_enabled(value: bool):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE sys_config SET value=? WHERE key='visitor_mode_enabled'", ('1' if value else '0',))
        conn.commit()
    except Exception as e:
        print(f"设置游客模式配置失败: {e}")
    finally:
        conn.close()

def get_visitor_daily_limit() -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM sys_config WHERE key='visitor_daily_limit'")
        res = cur.fetchone()
        if res and res[0].isdigit():
            return int(res[0])
    except Exception as e:
        print(f"获取游客每日限额失败: {e}")
    finally:
        conn.close()
    return 10

def set_visitor_daily_limit(value: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE sys_config SET value=? WHERE key='visitor_daily_limit'", (str(value),))
        conn.commit()
    except Exception as e:
        print(f"设置游客每日限额失败: {e}")
    finally:
        conn.close()

def get_visitor_link_count(ip: str) -> int:
    today = time.strftime("%Y-%m-%d")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM links WHERE create_user=? AND create_date=?", ('__visitor__', today))
        cnt = cur.fetchone()[0]
        return cnt
    except Exception as e:
        print(f"获取游客链接数失败: {e}")
        return 0
    finally:
        conn.close()

def get_str_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf8")).hexdigest()

def url_short_hash(url: str) -> str:
    md5 = hashlib.md5(url.encode("utf8")).hexdigest()
    cut_len = get_sys_hash_len()
    return md5[:cut_len]

def user_login_check(username: str, password: str) -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT pass_hash FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        return row and row[0] == get_str_hash(password)
    except Exception as e:
        print(f"登录验证失败: {e}")
        return False
    finally:
        conn.close()

def is_user_admin(username: str) -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        return row and row[0] == 1
    except Exception as e:
        print(f"权限检查失败: {e}")
        return False
    finally:
        conn.close()

def get_today_link_count(username: str) -> int:
    today = time.strftime("%Y-%m-%d")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM links WHERE create_user=? AND create_date=?", (username, today))
        return cur.fetchone()[0]
    except Exception as e:
        print(f"获取今日链接数失败: {e}")
        return 0
    finally:
        conn.close()

def get_user_daily_limit(username: str) -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT daily_max FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        return row[0] if row else 0
    except Exception as e:
        print(f"获取用户限额失败: {e}")
        return 0
    finally:
        conn.close()

def create_new_user(username: str, password: str, daily_max: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        p_hash = get_str_hash(password)
        cur.execute(
            "INSERT OR IGNORE INTO users (username, pass_hash, daily_max, is_admin) VALUES (?,?,?,0)",
            (username, p_hash, daily_max)
        )
        conn.commit()
    except Exception as e:
        print(f"创建用户失败: {e}")
    finally:
        conn.close()

def set_user_limit(username: str, new_limit: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET daily_max=? WHERE username=?", (new_limit, username))
        conn.commit()
    except Exception as e:
        print(f"设置用户限额失败: {e}")
    finally:
        conn.close()

def delete_user(username: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM links WHERE create_user=?", (username,))
        cur.execute("DELETE FROM sessions WHERE username=?", (username,))
        cur.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
    except Exception as e:
        print(f"删除用户失败: {e}")
    finally:
        conn.close()

def save_link(hash_code: str, raw_url: str, username: str):
    today = time.strftime("%Y-%m-%d")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO links (hash_code, original_url, create_user, create_date) VALUES (?,?,?,?)",
            (hash_code, raw_url, username, today)
        )
        conn.commit()
    except Exception as e:
        print(f"保存链接失败: {e}")
    finally:
        conn.close()

def delete_link(hash_code: str, username: str) -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT create_date FROM links WHERE hash_code=? AND create_user=?", (hash_code, username))
        row = cur.fetchone()
        if not row:
            return False
        create_date = row[0]
        today = time.strftime("%Y-%m-%d")
        cur.execute("DELETE FROM links WHERE hash_code=? AND create_user=?", (hash_code, username))
        conn.commit()
        if create_date == today and get_return_limit_on_delete():
            print(f"返还次数给用户: {username}")
        return True
    except Exception as e:
        print(f"删除链接失败: {e}")
        return False
    finally:
        conn.close()

def get_origin_url(hash_code: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT original_url FROM links WHERE hash_code=?", (hash_code,))
        res = cur.fetchone()
        return res[0] if res else None
    except Exception as e:
        print(f"查询链接失败: {e}")
        return None
    finally:
        conn.close()

def get_user_all_links(username: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT hash_code, original_url, create_date FROM links WHERE create_user=? ORDER BY create_date DESC", (username,))
        return cur.fetchall()
    except Exception as e:
        print(f"获取用户链接失败: {e}")
        return []
    finally:
        conn.close()

def get_all_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, daily_max, is_admin FROM users ORDER BY username")
        return cur.fetchall()
    except Exception as e:
        print(f"获取用户列表失败: {e}")
        return []
    finally:
        conn.close()

def create_session(username: str) -> str:
    session_id = get_str_hash(f"{username}{time.time()}{random.getrandbits(64)}")
    expire = int(time.time()) + SESSION_EXPIRE
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE username=?", (username,))
        cur.execute("INSERT INTO sessions (session_id, username, expire_ts) VALUES (?,?,?)", (session_id, username, expire))
        conn.commit()
        return session_id
    except Exception as e:
        print(f"创建会话失败: {e}")
        return ""
    finally:
        conn.close()

def get_session_user(session_id: str):
    now = int(time.time())
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username FROM sessions WHERE session_id=? AND expire_ts > ?", (session_id, now))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"获取会话失败: {e}")
        return None
    finally:
        conn.close()

def clear_session(session_id: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.commit()
    except Exception as e:
        print(f"清除会话失败: {e}")
    finally:
        conn.close()

CSS_STYLE = """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    color: #333;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

.card {
    background: white;
    border-radius: 16px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
    padding: 30px;
    margin-bottom: 25px;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.card:hover {
    transform: translateY(-2px);
    box-shadow: 0 15px 45px rgba(0,0,0,0.15);
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 25px;
    padding-bottom: 15px;
    border-bottom: 2px solid #f0f0f0;
}

.card-title {
    font-size: 24px;
    font-weight: 700;
    color: #2d3748;
    display: flex;
    align-items: center;
    gap: 10px;
}

.card-title::before {
    content: '';
    width: 4px;
    height: 24px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 2px;
}

.btn {
    padding: 10px 24px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.btn-primary {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

.btn-secondary {
    background: #f7fafc;
    color: #4a5568;
    border: 1px solid #e2e8f0;
}

.btn-secondary:hover {
    background: #edf2f7;
}

.btn-danger {
    background: #fc8181;
    color: white;
}

.btn-danger:hover {
    background: #f56565;
    box-shadow: 0 4px 15px rgba(245, 101, 101, 0.3);
}

.btn-sm {
    padding: 6px 14px;
    font-size: 12px;
}

.form-group {
    margin-bottom: 20px;
}

.form-label {
    display: block;
    font-size: 14px;
    font-weight: 600;
    color: #4a5568;
    margin-bottom: 8px;
}

.form-input {
    width: 100%;
    padding: 12px 16px;
    border: 2px solid #e2e8f0;
    border-radius: 10px;
    font-size: 14px;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
    outline: none;
}

.form-input:focus {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-input::placeholder {
    color: #a0aec0;
}

.form-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
}

.stat-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}

.stat-value {
    font-size: 32px;
    font-weight: 700;
    color: #667eea;
    margin-bottom: 5px;
}

.stat-label {
    font-size: 13px;
    color: #718096;
}

.link-list {
    max-height: 400px;
    overflow-y: auto;
}

.link-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 15px;
    background: #f7fafc;
    border-radius: 10px;
    margin-bottom: 10px;
    transition: background 0.3s ease;
}

.link-item:hover {
    background: #edf2f7;
}

.link-info {
    flex: 1;
    margin-right: 20px;
}

.link-hash {
    font-family: 'Monaco', 'Consolas', monospace;
    font-size: 14px;
    color: #667eea;
    font-weight: 600;
    margin-bottom: 5px;
}

.link-url {
    font-size: 13px;
    color: #718096;
    word-break: break-all;
    max-width: 500px;
}

.link-date {
    font-size: 12px;
    color: #a0aec0;
}

.alert {
    padding: 15px 20px;
    border-radius: 8px;
    margin-bottom: 20px;
    font-size: 14px;
}

.alert-success {
    background: #c6f6d5;
    color: #22543d;
    border-left: 4px solid #48bb78;
}

.alert-error {
    background: #fed7d7;
    color: #742a2a;
    border-left: 4px solid #fc8181;
}

.alert-info {
    background: #ebf8ff;
    color: #1a365d;
    border-left: 4px solid #63b3ed;
}

.user-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 15px;
    background: #f7fafc;
    border-radius: 10px;
    margin-bottom: 10px;
}

.user-info {
    display: flex;
    align-items: center;
    gap: 15px;
}

.user-name {
    font-weight: 600;
    color: #2d3748;
}

.user-badge {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
}

.user-badge.admin {
    background: #fbd38d;
    color: #c25205;
}

.user-badge.normal {
    background: #c6f6d5;
    color: #22543d;
}

.nav-bar {
    background: white;
    padding: 15px 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    margin-bottom: 30px;
}

.nav-content {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.nav-brand {
    font-size: 20px;
    font-weight: 700;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.nav-links {
    display: flex;
    gap: 15px;
}

.login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
}

.login-card {
    background: white;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.15);
    padding: 45px;
    width: 100%;
    max-width: 450px;
    animation: fadeInUp 0.5s ease;
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.login-header {
    text-align: center;
    margin-bottom: 35px;
}

.login-title {
    font-size: 28px;
    font-weight: 800;
    color: #2d3748;
    margin-bottom: 10px;
}

.login-subtitle {
    font-size: 14px;
    color: #718096;
}

.login-form {
    margin-bottom: 25px;
}

.login-footer {
    text-align: center;
    font-size: 13px;
    color: #a0aec0;
}

.generate-result {
    background: linear-gradient(135deg, #ebf8ff 0%, #e6fffa 100%);
    border: 2px dashed #63b3ed;
    border-radius: 12px;
    padding: 25px;
    margin-top: 20px;
}

.result-url {
    font-family: 'Monaco', 'Consolas', monospace;
    font-size: 16px;
    color: #667eea;
    word-break: break-all;
    margin: 10px 0;
}

.copy-btn {
    margin-top: 15px;
}

@media (max-width: 768px) {
    .container {
        padding: 10px;
    }
    .card {
        padding: 20px;
    }
    .login-card {
        padding: 30px 20px;
    }
    .link-item {
        flex-direction: column;
        align-items: flex-start;
    }
    .link-info {
        margin-right: 0;
        margin-bottom: 10px;
    }
    .nav-links {
        flex-direction: column;
        gap: 10px;
    }
}
"""

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if not hasattr(self.server, 'access_log_enabled') or self.server.access_log_enabled:
            BaseHTTPRequestHandler.log_message(self, format, *args)

    def get_cookie(self, key: str):
        if "Cookie" not in self.headers:
            return None
        cookies = {}
        for pair in self.headers["Cookie"].split(";"):
            try:
                k, v = pair.strip().split("=", 1)
                cookies[k] = v
            except:
                continue
        return cookies.get(key)

    def get_login_user(self):
        sid = self.get_cookie("sid")
        if not sid:
            return None
        return get_session_user(sid)

    def redirect_login(self):
        self.send_response(302)
        self.send_header("Location", "/login")
        self.end_headers()

    def render_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf8"))

    def build_nav(self, user):
        is_admin = is_user_admin(user) if user else False
        nav = f"""
        <div class="nav-bar">
            <div class="nav-content">
                <div class="nav-brand">🔗 URL哈希加密系统</div>
                <div class="nav-links">
                    <a href="/user_panel" class="btn btn-secondary">用户面板</a>
                    {f'<a href="/admin" class="btn btn-primary">管理后台</a>' if is_admin else ''}
                    <a href="/logout" class="btn btn-secondary">退出登录</a>
                </div>
            </div>
        </div>
        """
        return nav

    def do_GET(self):
        path = self.path.split("?")[0].strip("/")
        user = self.get_login_user()
        current_hash_len = get_sys_hash_len()

        if path not in ["login", "admin", "user_panel", "create_user", "user_list", "set_hash_len", ""]:
            target = get_origin_url(path)
            if target:
                self.send_response(302)
                self.send_header("Location", target)
                self.end_headers()
                return

        visitor_enabled = get_visitor_mode_enabled()
        
        if path == "login":
            visitor_section = f'''
            <div style="margin-top:20px; padding-top:20px; border-top:1px solid #e2e8f0;">
                <p style="text-align:center; color:#718096; margin-bottom:15px;">或使用游客模式</p>
                <a href="/visitor_panel" class="btn btn-secondary" style="width:100%;">游客模式（免登录）</a>
            </div>
            ''' if visitor_enabled else ''
            
            html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>哈希加密短链系统 - 登录</title>
                <style>{CSS_STYLE}</style>
            </head>
            <body>
                <div class="login-container">
                    <div class="login-card">
                        <div class="login-header">
                            <div class="login-title">🔗 URL哈希加密系统</div>
                            <div class="login-subtitle">当前加密字符长度：{current_hash_len}位</div>
                        </div>
                        <form method="POST" class="login-form">
                            <div class="form-group">
                                <label class="form-label">账号</label>
                                <input type="text" name="user" class="form-input" placeholder="请输入用户名" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">密码</label>
                                <input type="password" name="pass" class="form-input" placeholder="请输入密码" required>
                            </div>
                            <button type="submit" class="btn btn-primary" style="width:100%;">登 录</button>
                        </form>
                        {visitor_section}
                        <div class="login-footer">
                            生成MD5哈希混淆加密、缩短后的URL，访问哈希地址自动跳转原链接
                        </div>
                    </div>
                </div>
            </body>
            </html>
            '''
            self.render_html(html)
            return

        if not user:
            if visitor_enabled and path == "visitor_panel":
                pass
            else:
                self.redirect_login()
                return

        if path == "user_panel":
            limit = get_user_daily_limit(user)
            used = get_today_link_count(user)
            links = get_user_all_links(user)
            remaining = limit - used
            progress = (used / limit) * 100 if limit > 0 else 0
            host = self.headers.get("Host", "localhost:8080")
            base_url = f"http://{host}"

            link_html = """<div class="alert alert-info">暂无生成的短链接</div>""" if not links else ""
            if links:
                link_html = '<div class="link-list">'
                for h, u, d in links:
                    full_link = f"{base_url}/{h}"
                    link_html += f'''
                    <div class="link-item">
                        <div class="link-info">
                            <div class="link-hash">
                                <span style="font-family: 'Monaco', 'Consolas', monospace; font-size:14px; color:#667eea; font-weight:600;">{full_link}</span>
                            </div>
                            <div class="link-url">{u}</div>
                            <div class="link-date">创建于 {d}</div>
                        </div>
                        <div style="display:flex; gap:8px;">
                            <button onclick="copyLink('{full_link}', this)" class="btn btn-secondary btn-sm">复制</button>
                            <a href="/{h}" target="_blank" class="btn btn-primary btn-sm">访问</a>
                            <form method="POST" action="/del_link" style="display:inline;" onsubmit="return confirm('确定删除这条短链吗？')">
                                <input type="hidden" name="hash_code" value="{h}">
                                <button type="submit" class="btn btn-danger btn-sm">删除</button>
                            </form>
                        </div>
                    </div>
                    '''
                link_html += '</div>'

            page = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>用户面板 - URL哈希加密系统</title>
                <style>{CSS_STYLE}</style>
            </head>
            <body>
                {self.build_nav(user)}
                <div class="container">
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">欢迎回来，{user}</div>
                        </div>
                        <div class="stat-cards">
                            <div class="stat-card">
                                <div class="stat-value">{used}/{limit}</div>
                                <div class="stat-label">今日已生成/限额</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">{remaining}</div>
                                <div class="stat-label">今日剩余次数</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">{current_hash_len}</div>
                                <div class="stat-label">哈希加密位数</div>
                            </div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">生成哈希加密短链接</div>
                        </div>
                        <form method="POST" action="/gen_link">
                            <div class="form-group">
                                <label class="form-label">原始长URL</label>
                                <input type="url" name="url" class="form-input" size="60" placeholder="https://xxx.com/long/url" required>
                            </div>
                            <button type="submit" class="btn btn-primary">生成混淆加密短链</button>
                        </form>
                        <div style="margin-top:15px; padding:15px; background:#f7fafc; border-radius:8px; font-size:13px; color:#718096;">
                            说明：{current_hash_len}位MD5哈希既缩短地址长度，又隐藏原始URL实现匿名混淆
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">我的加密短链记录</div>
                        </div>
                        {link_html}
                    </div>
                </div>
                <script>
                    function copyLink(text, btn) {{
                        var originalText = btn.innerHTML;
                        
                        if (navigator.clipboard && window.isSecureContext) {{
                            navigator.clipboard.writeText(text).then(function() {{
                                showCopied(btn, originalText);
                            }}).catch(function() {{
                                fallbackCopy(text, btn, originalText);
                            }});
                        }} else {{
                            fallbackCopy(text, btn, originalText);
                        }}
                    }}
                    
                    function fallbackCopy(text, btn, originalText) {{
                        var textarea = document.createElement('textarea');
                        textarea.value = text;
                        textarea.style.position = 'fixed';
                        textarea.style.left = '-9999px';
                        textarea.style.top = '0';
                        textarea.setAttribute('readonly', '');
                        document.body.appendChild(textarea);
                        
                        var selected = document.getSelection().rangeCount > 0 ? document.getSelection().getRangeAt(0) : false;
                        
                        textarea.focus();
                        textarea.select();
                        
                        try {{
                            var successful = document.execCommand('copy');
                            if (successful) {{
                                showCopied(btn, originalText);
                            }} else {{
                                alertCopy(text);
                            }}
                        }} catch (err) {{
                            alertCopy(text);
                        }}
                        
                        document.body.removeChild(textarea);
                        
                        if (selected) {{
                            document.getSelection().removeAllRanges();
                            document.getSelection().addRange(selected);
                        }}
                    }}
                    
                    function alertCopy(text) {{
                        var temp = document.createElement('div');
                        temp.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#333;color:white;padding:20px;border-radius:10px;font-size:16px;z-index:9999;text-align:center;max-width:80%;';
                        temp.innerHTML = '<div style="font-size:24px;margin-bottom:10px;">📋</div><div>请手动复制：</div><div style="margin-top:10px;font-family:monospace;word-break:break-all;">' + text + '</div><div style="margin-top:15px;font-size:12px;color:#aaa;">点击关闭</div>';
                        temp.onclick = function() {{ document.body.removeChild(temp); }};
                        document.body.appendChild(temp);
                    }}
                    
                    function showCopied(btn, originalText) {{
                        btn.innerHTML = '✓ 已复制';
                        btn.style.background = '#48bb78';
                        btn.style.color = 'white';
                        setTimeout(function() {{
                            btn.innerHTML = originalText;
                            btn.style.background = '#f7fafc';
                            btn.style.color = '#4a5568';
                        }}, 2000);
                    }}
                </script>
            </body>
            </html>
            '''
            self.render_html(page)
            return

        if path == "visitor_panel":
            if not visitor_enabled:
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    <div class="login-container">
                        <div class="login-card">
                            <div class="alert alert-error">游客模式未启用</div>
                            <a href="/login" class="btn btn-secondary">返回登录</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return
            
            limit = get_visitor_daily_limit()
            used = get_visitor_link_count(self.client_address[0])
            remaining = limit - used
            host = self.headers.get("Host", "localhost:8080")
            base_url = f"http://{host}"
            
            page = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>游客模式 - URL哈希加密系统</title>
                <style>{CSS_STYLE}</style>
            </head>
            <body>
                <div class="nav-bar">
                    <div class="nav-content">
                        <div class="nav-brand">🔗 URL哈希加密系统</div>
                        <div class="nav-links">
                            <a href="/login" class="btn btn-secondary">登录账号</a>
                        </div>
                    </div>
                </div>
                <div class="container">
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">👤 游客模式</div>
                        </div>
                        <div class="stat-cards">
                            <div class="stat-card">
                                <div class="stat-value">{used}/{limit}</div>
                                <div class="stat-label">今日已生成/限额</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">{remaining}</div>
                                <div class="stat-label">今日剩余次数</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">{current_hash_len}</div>
                                <div class="stat-label">哈希加密位数</div>
                            </div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">生成哈希加密短链接</div>
                        </div>
                        <form method="POST" action="/gen_link">
                            <div class="form-group">
                                <label class="form-label">原始长URL</label>
                                <input type="url" name="url" class="form-input" size="60" placeholder="https://xxx.com/long/url" required>
                            </div>
                            <button type="submit" class="btn btn-primary">生成混淆加密短链</button>
                        </form>
                        <div style="margin-top:15px; padding:15px; background:#f7fafc; border-radius:8px; font-size:13px; color:#718096;">
                            说明：游客模式生成的短链无法查看历史记录和删除，如需管理功能请登录账号
                        </div>
                    </div>
                </div>
            </body>
            </html>
            '''
            self.render_html(page)
            return

        if path == "admin":
            if not is_user_admin(user):
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {self.build_nav(user)}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">无管理员权限</div>
                            <a href="/user_panel" class="btn btn-secondary">返回个人面板</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return

            users = get_all_users()
            user_list_html = """<div class="alert alert-info">暂无用户</div>""" if not users else ""
            if users:
                user_list_html = ''
                for uname, lim, adm in users:
                    is_admin_mark = adm == 1
                    user_list_html += f'''
                    <div class="user-item">
                        <div class="user-info">
                            <span class="user-name">{uname}</span>
                            <span class="user-badge {'admin' if is_admin_mark else 'normal'}">{'管理员' if is_admin_mark else '普通用户'}</span>
                            <span style="color:#718096">每日限额: {lim}</span>
                        </div>
                        <div style="display:flex; gap:10px;">
                            <form method="POST" action="/set_limit" style="display:inline;">
                                <input hidden name="target_user" value="{uname}">
                                <input type="number" name="new_limit" value="{lim}" size="3" min="1" max="999" class="form-input" style="width:80px;">
                                <button type="submit" class="btn btn-primary btn-sm">修改</button>
                            </form>
                            {f'<form method="POST" action="/del_user" style="display:inline;"><input hidden name="del_user" value="{uname}"><button type="submit" class="btn btn-danger btn-sm">删除</button></form>' if uname != DEFAULT_ADMIN_USER else '<span style="color:#a0aec0; font-size:12px;">主管理员不可删除</span>'}
                        </div>
                    </div>
                    '''

            page = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>管理员后台 - URL哈希加密系统</title>
                <style>{CSS_STYLE}</style>
            </head>
            <body>
                {self.build_nav(user)}
                <div class="container">
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">全局设置 - 加密哈希字符长度</div>
                        </div>
                        <div style="margin-bottom:20px; padding:15px; background:#ebf8ff; border-radius:8px;">
                            当前哈希长度：<strong style="color:#667eea; font-size:24px;">{current_hash_len}</strong> 位
                        </div>
                        <form method="POST" action="/set_hash_len">
                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">新哈希位数</label>
                                    <input type="number" name="hash_len" value="{current_hash_len}" size="2" min="4" max="16" class="form-input" required>
                                </div>
                            </div>
                            <button type="submit" class="btn btn-primary">保存全局配置</button>
                            <p style="color:#718096; margin-top:10px; font-size:13px;">建议范围4~16位，位数越多重复概率越低</p>
                        </form>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">删除短链配置</div>
                        </div>
                        <div style="margin-bottom:20px; padding:15px; background:#ebf8ff; border-radius:8px;">
                            删除后返还次数：<strong style="color:#667eea; font-size:24px;">{'开启' if get_return_limit_on_delete() else '关闭'}</strong>
                        </div>
                        <form method="POST" action="/set_return_limit">
                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">删除后是否返还今日剩余次数</label>
                                    <select name="value" class="form-input">
                                        <option value="1" {'selected' if get_return_limit_on_delete() else ''}>是，返还次数</option>
                                        <option value="0" {'selected' if not get_return_limit_on_delete() else ''}>否，不返还次数</option>
                                    </select>
                                </div>
                            </div>
                            <button type="submit" class="btn btn-primary">保存配置</button>
                            <p style="color:#718096; margin-top:10px; font-size:13px;">开启后，用户删除今日生成的短链将返还一次生成次数</p>
                        </form>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">游客模式配置</div>
                        </div>
                        <div style="margin-bottom:20px; padding:15px; background:#ebf8ff; border-radius:8px;">
                            游客模式状态：<strong style="color:#667eea; font-size:24px;">{'开启' if get_visitor_mode_enabled() else '关闭'}</strong>
                            <br><br>
                            游客每日限额：<strong style="color:#667eea; font-size:24px;">{get_visitor_daily_limit()}</strong> 次
                        </div>
                        <form method="POST" action="/set_visitor_config">
                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">是否启用游客模式（免登录使用）</label>
                                    <select name="visitor_enabled" class="form-input">
                                        <option value="1" {'selected' if get_visitor_mode_enabled() else ''}>是，启用游客模式</option>
                                        <option value="0" {'selected' if not get_visitor_mode_enabled() else ''}>否，关闭游客模式</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">游客每日生成限额</label>
                                    <input type="number" name="visitor_limit" value="{get_visitor_daily_limit()}" class="form-input" min="1" max="999">
                                </div>
                            </div>
                            <button type="submit" class="btn btn-primary">保存游客配置</button>
                            <p style="color:#718096; margin-top:10px; font-size:13px;">游客模式允许未登录用户生成短链，但无法查看历史记录和删除。每日限额按IP地址统计。</p>
                        </form>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">新建普通用户</div>
                        </div>
                        <form method="POST" action="/create_user">
                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">用户名</label>
                                    <input type="text" name="new_user" class="form-input" placeholder="用户名" required>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">登录密码</label>
                                    <input type="password" name="new_pass" class="form-input" placeholder="密码" required>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">每日生成限额</label>
                                    <input type="number" name="new_limit" value="20" class="form-input" min="1" max="999">
                                </div>
                            </div>
                            <button type="submit" class="btn btn-primary">创建账号</button>
                        </form>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">系统用户列表</div>
                        </div>
                        {user_list_html}
                    </div>
                </div>
            </body>
            </html>
            '''
            self.render_html(page)
            return

        if path == "logout":
            sid = self.get_cookie("sid")
            if sid:
                clear_session(sid)
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "sid=; Max-Age=0; Path=/")
            self.end_headers()
            return

        self.send_response(302)
        self.send_header("Location", "/user_panel")
        self.end_headers()

    def do_POST(self):
        path = self.path.strip("/")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf8") if length > 0 else ""
        params = urllib.parse.parse_qs(body)
        user = self.get_login_user()
        current_hash_len = get_sys_hash_len()

        if path == "login":
            un = params.get("user", [""])[0].strip()
            pw = params.get("pass", [""])[0].strip()

            valid, msg = validate_username(un)
            if not valid:
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    <div class="login-container">
                        <div class="login-card">
                            <div class="login-header">
                                <div class="login-title">🔗 URL哈希加密系统</div>
                            </div>
                            <div class="alert alert-error">{msg}</div>
                            <a href="/login" class="btn btn-secondary">返回登录</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return

            if user_login_check(un, pw):
                sid = create_session(un)
                self.send_response(302)
                self.send_header("Location", "/user_panel")
                self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly")
                self.end_headers()
            else:
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    <div class="login-container">
                        <div class="login-card">
                            <div class="login-header">
                                <div class="login-title">🔗 URL哈希加密系统</div>
                            </div>
                            <div class="alert alert-error">账号或密码错误</div>
                            <a href="/login" class="btn btn-secondary">重新登录</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
            return

        if not user:
            if path == "gen_link" and get_visitor_mode_enabled():
                pass
            else:
                self.redirect_login()
                return

        if path == "set_hash_len":
            if not is_user_admin(user):
                self.render_html(f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {self.build_nav(user)}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">无管理员操作权限</div>
                        </div>
                    </div>
                </body>
                </html>
                ''')
                return
            try:
                new_len = int(params.get("hash_len", ["8"])[0])
                if 4 <= new_len <= 16:
                    set_sys_hash_len(new_len)
            except ValueError:
                pass
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return

        if path == "gen_link":
            raw_url = params.get("url", [""])[0].strip()
            valid, msg = validate_url(raw_url)
            if not valid:
                if user:
                    nav = self.build_nav(user)
                    back_url = "/user_panel"
                else:
                    nav = '''<div class="nav-bar"><div class="nav-content"><div class="nav-brand">🔗 URL哈希加密系统</div><div class="nav-links"><a href="/login" class="btn btn-secondary">登录账号</a></div></div></div>'''
                    back_url = "/visitor_panel"
                
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {nav}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">{msg}</div>
                            <a href="{back_url}" class="btn btn-secondary">返回</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return

            if user:
                limit = get_user_daily_limit(user)
                used = get_today_link_count(user)
                create_user = user
                back_url = "/user_panel"
                nav = self.build_nav(user)
            else:
                limit = get_visitor_daily_limit()
                used = get_visitor_link_count(self.client_address[0])
                create_user = "__visitor__"
                back_url = "/visitor_panel"
                nav = '''<div class="nav-bar"><div class="nav-content"><div class="nav-brand">🔗 URL哈希加密系统</div><div class="nav-links"><a href="/login" class="btn btn-secondary">登录账号</a></div></div></div>'''
            
            if used >= limit:
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {nav}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">今日加密短链生成次数已达上限 {limit}</div>
                            <a href="{back_url}" class="btn btn-secondary">返回面板</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return

            hash_code = url_short_hash(raw_url)
            save_link(hash_code, raw_url, create_user)
            full_url = f"http://{self.headers.get('Host', '')}/{hash_code}"

            html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>{CSS_STYLE}</style>
            </head>
            <body>
                {nav}
                <div class="container">
                    <div class="card">
                        <div class="card-header">
                            <div class="card-title">✅ 加密短链生成成功</div>
                        </div>
                        <div class="generate-result">
                            <p style="font-size:14px; color:#718096;">{current_hash_len}位MD5混淆加密短链接：</p>
                            <div class="result-url">{full_url}</div>
                            <p style="font-size:13px; color:#a0aec0; margin-top:10px;">
                                说明：{current_hash_len}位MD5哈希既缩短地址长度，又隐藏原始URL实现匿名混淆
                            </p>
                            <button onclick="copyLink('{full_url}', this)" class="btn btn-secondary copy-btn">复制链接</button>
                        </div>
                        <div style="margin-top:20px;">
                            <a href="{back_url}" class="btn btn-primary">返回面板</a>
                            <a href="{full_url}" target="_blank" class="btn btn-secondary">访问短链接</a>
                        </div>
                    </div>
                </div>
                <script>
                    function copyLink(text, btn) {{
                        var originalText = btn.innerHTML;
                        
                        if (navigator.clipboard && window.isSecureContext) {{
                            navigator.clipboard.writeText(text).then(function() {{
                                showCopied(btn, originalText);
                            }}).catch(function() {{
                                fallbackCopy(text, btn, originalText);
                            }});
                        }} else {{
                            fallbackCopy(text, btn, originalText);
                        }}
                    }}
                    
                    function fallbackCopy(text, btn, originalText) {{
                        var textarea = document.createElement('textarea');
                        textarea.value = text;
                        textarea.style.position = 'fixed';
                        textarea.style.left = '-9999px';
                        textarea.style.top = '0';
                        textarea.setAttribute('readonly', '');
                        document.body.appendChild(textarea);
                        
                        var selected = document.getSelection().rangeCount > 0 ? document.getSelection().getRangeAt(0) : false;
                        
                        textarea.focus();
                        textarea.select();
                        
                        try {{
                            var successful = document.execCommand('copy');
                            if (successful) {{
                                showCopied(btn, originalText);
                            }} else {{
                                alertCopy(text);
                            }}
                        }} catch (err) {{
                            alertCopy(text);
                        }}
                        
                        document.body.removeChild(textarea);
                        
                        if (selected) {{
                            document.getSelection().removeAllRanges();
                            document.getSelection().addRange(selected);
                        }}
                    }}
                    
                    function alertCopy(text) {{
                        var temp = document.createElement('div');
                        temp.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#333;color:white;padding:20px;border-radius:10px;font-size:16px;z-index:9999;text-align:center;max-width:80%;';
                        temp.innerHTML = '<div style="font-size:24px;margin-bottom:10px;">📋</div><div>请手动复制：</div><div style="margin-top:10px;font-family:monospace;word-break:break-all;">' + text + '</div><div style="margin-top:15px;font-size:12px;color:#aaa;">点击关闭</div>';
                        temp.onclick = function() {{ document.body.removeChild(temp); }};
                        document.body.appendChild(temp);
                    }}
                    
                    function showCopied(btn, originalText) {{
                        btn.innerHTML = '✓ 已复制';
                        btn.style.background = '#48bb78';
                        btn.style.color = 'white';
                        setTimeout(function() {{
                            btn.innerHTML = originalText;
                            btn.style.background = '#f7fafc';
                            btn.style.color = '#4a5568';
                        }}, 2000);
                    }}
                </script>
            </body>
            </html>
            '''
            self.render_html(html)
            return

        if path == "create_user":
            if not is_user_admin(user):
                self.render_html(f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {self.build_nav(user)}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">无管理员操作权限</div>
                        </div>
                    </div>
                </body>
                </html>
                ''')
                return
            nu = params.get("new_user", [""])[0].strip()
            np = params.get("new_pass", [""])[0].strip()
            nl = int(params.get("new_limit", ["20"])[0])

            valid, msg = validate_username(nu)
            if not valid:
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {self.build_nav(user)}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">{msg}</div>
                            <a href="/admin" class="btn btn-secondary">返回管理后台</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return

            valid, msg = validate_password(np)
            if not valid:
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>{CSS_STYLE}</style>
                </head>
                <body>
                    {self.build_nav(user)}
                    <div class="container">
                        <div class="card">
                            <div class="alert alert-error">{msg}</div>
                            <a href="/admin" class="btn btn-secondary">返回管理后台</a>
                        </div>
                    </div>
                </body>
                </html>
                '''
                self.render_html(html)
                return

            create_new_user(nu, np, nl)
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return

        if path == "set_limit":
            if not is_user_admin(user):
                return
            tu = params.get("target_user", [""])[0].strip()
            try:
                nl = int(params.get("new_limit", ["20"])[0])
                if nl > 0:
                    set_user_limit(tu, nl)
            except ValueError:
                pass
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return

        if path == "del_user":
            if not is_user_admin(user):
                return
            du = params.get("del_user", [""])[0].strip()
            if du != DEFAULT_ADMIN_USER:
                delete_user(du)
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return

        if path == "del_link":
            hash_code = params.get("hash_code", [""])[0].strip()
            if hash_code:
                delete_link(hash_code, user)
            self.send_response(302)
            self.send_header("Location", "/user_panel")
            self.end_headers()
            return

        if path == "set_return_limit":
            if not is_user_admin(user):
                return
            value = params.get("value", ["1"])[0].strip()
            set_return_limit_on_delete(value == "1")
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return

        if path == "set_visitor_config":
            if not is_user_admin(user):
                return
            visitor_enabled = params.get("visitor_enabled", ["0"])[0].strip()
            try:
                visitor_limit = int(params.get("visitor_limit", ["10"])[0])
                if visitor_limit < 1:
                    visitor_limit = 1
                if visitor_limit > 999:
                    visitor_limit = 999
            except ValueError:
                visitor_limit = 10
            set_visitor_mode_enabled(visitor_enabled == "1")
            set_visitor_daily_limit(visitor_limit)
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return

def parse_args():
    bind_ip = DEFAULT_BIND_IP
    port = DEFAULT_PORT
    admin_user = DEFAULT_ADMIN_USER
    admin_pass = DEFAULT_ADMIN_PASS
    daily_limit = DEFAULT_DAILY_LIMIT
    access_log = DEFAULT_ACCESS_LOG

    idx = 1
    while idx < len(sys.argv):
        arg = sys.argv[idx]
        if arg in ("-h", "--help"):
            print_help()
        elif arg in ("--bind-ip", "-i"):
            bind_ip = sys.argv[idx+1]
            idx +=2
        elif arg in ("--port", "-p"):
            port = int(sys.argv[idx+1])
            idx +=2
        elif arg in ("--admin-user", "-au"):
            admin_user = sys.argv[idx+1]
            idx +=2
        elif arg in ("--admin-pass", "-ap"):
            admin_pass = sys.argv[idx+1]
            idx +=2
        elif arg in ("--default-limit", "-dl"):
            daily_limit = int(sys.argv[idx+1])
            idx +=2
        elif arg in ("--no-access-log", "-nal"):
            access_log = False
            idx +=1
        else:
            idx +=1
    return bind_ip, port, admin_user, admin_pass, daily_limit, access_log

import socketserver

class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    bind_ip, port, run_admin_user, run_admin_pass, run_default_limit, run_access_log = parse_args()
    init_db(run_admin_user, run_admin_pass, run_default_limit)
    print("======================================")
    print("    哈希URL混淆加密+短链接服务 v2.0    ")
    print(f"监听IP：{bind_ip}  端口：{port}")
    print(f"管理员账号：{run_admin_user}")
    print(f"初始密码：{run_admin_pass}")
    print(f"访问日志：{'开启' if run_access_log else '关闭'}")
    print("启动帮助命令：python3 urljm.py -h")
    print("======================================")
    print("按 Ctrl+C 停止服务")
    try:
        server = ThreadedHTTPServer((bind_ip, port), RequestHandler)
        server.access_log_enabled = run_access_log
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
        server.shutdown()
        server.server_close()
        print("服务已正常关闭")