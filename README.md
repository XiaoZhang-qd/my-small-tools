<!--# my-small-tool

A repository for my personal tools, scripts, and experiments.

-->
---

# My Small Tools

`My Small Tools` 是一个个人工具集合仓库，用于存放我制作的一些小型工具、脚本和实验性项目。

这些工具覆盖多个方向，包括网络工具、效率工具、自动化脚本以及各种用于学习和探索的小项目。

仓库中的每个工具都拥有独立的功能和用途：

- **[URLJM** —— 一个 URL 哈希混淆与短链接管理系统；
- **TZ** —— 一个用于检测 IP 和网络环境信息的工具；
- **Daili** —— 一个轻量级代理管理与本地代理转发工具。

这个仓库的目标不是打造大型软件，而是记录开发过程中的想法、实践和解决问题的方法。

---

# 🛡️ Daili

**Lightweight Proxy Manager & Local Forward Proxy**

Daili 是轻量级命令行代理管理工具。

 支持多源代理池加载、动态代理选择、终端环境变量注入，同时内置本地中转代理服务，统一应用出口。

> 适用场景：网络调试、自动化脚本、代理轮换、临时切换系统代理环境。

---

## 📋 目录

- [✨ 核心特性](#-%E6%A0%B8%E5%BF%83%E7%89%B9%E6%80%A7)
- [📥 代理来源](#-%E4%BB%A3%E7%90%86%E6%9D%A5%E6%BA%90)
- [🔀 代理选择策略](#-%E4%BB%A3%E7%90%86%E9%80%89%E6%8B%A9%E7%AD%96%E7%95%A5)
- [🌐 支持代理格式](#-%E6%94%AF%E6%8C%81%E4%BB%A3%E7%90%86%E6%A0%BC%E5%BC%8F)
- [🔍 协议过滤](#-%E5%8D%8F%E8%AE%AE%E8%BF%87%E6%BB%A4)
- [🔄 自动轮换刷新](#-%E8%87%AA%E5%8A%A8%E8%BD%AE%E6%8D%A2%E5%88%B7%E6%96%B0)
- [🌍 读取系统已有代理](#-%E8%AF%BB%E5%8F%96%E7%B3%BB%E7%BB%9F%E5%B7%B2%E6%9C%89%E4%BB%A3%E7%90%86)
- [🖥️ 本地中转代理服务](#%EF%B8%8F-%E6%9C%AC%E5%9C%B0%E4%B8%AD%E8%BD%AC%E4%BB%A3%E7%90%86%E6%9C%8D%E5%8A%A1)
- [🔐 本地代理鉴权](#-%E6%9C%AC%E5%9C%B0%E4%BB%A3%E7%90%86%E9%89%B4%E6%9D%83)
- [📤 导出终端环境变量](#-%E5%AF%BC%E5%87%BA%E7%BB%88%E7%AB%AF%E7%8E%AF%E5%A2%83%E5%8F%98%E9%87%8F)
- [📌 使用示例](#-%E4%BD%BF%E7%94%A8%E7%A4%BA%E4%BE%8B)
- [⚙️ 完整参数说明](#%EF%B8%8F-%E5%AE%8C%E6%95%B4%E5%8F%82%E6%95%B0%E8%AF%B4%E6%98%8E)
- [💡 项目定位](#-%E9%A1%B9%E7%9B%AE%E5%AE%9A%E4%BD%8D)

---

## ✨ 核心特性

- ✅ 三类代理源：本地文件 / 远程 HTTP 链接 / 标准输入管道
- ✅ 两种选取策略：随机选取 / 顺序选取
- ✅ 自动补全代理协议头，兼容 `ip:port` 最简格式
- ✅ 支持按 HTTP / SOCKS5 协议过滤代理池
- ✅ 定时自动重载代理池，动态切换上游代理
- ✅ 内置 HTTP 本地中转代理，支持 Basic Auth 认证
- ✅ `--export-env` 自动识别终端类型输出适配脚本
  - Windows CMD
    - Windows PowerShell
    - Linux / macOS Shell
- ✅ 可读取系统环境变量 `HTTP_PROXY/ALL_PROXY` 加入代理池

---

## 📥 代理来源

### 1. 本地文本文件

bash

```
python daili.py -f proxy.txt
```

示例

`proxy.txt`

plaintext

```
127.0.0.1:8080
http://127.0.0.1:8081
socks5://127.0.0.1:1080
user:pass@1.2.3.4:2080
```

### 2. 远程 HTTP / HTTPS 代理列表

bash

```
python daili.py -f https://example.com/proxy-list.txt
```

程序自动请求地址、按行解析载入代理池。

### 3. 标准输入（管道模式）

传递

`-`

 从 stdin 读取，方便串联其他工具

bash

```
cat proxy.txt | python daili.py -f -
```

---

## 🔀 代理选择策略

### 随机模式 `random`

bash

```
python daili.py -f proxy.txt -m random
```

从代理池随机挑选，适合长期轮换出口。

### 顺序模式 `seq`

bash

```
python daili.py -f proxy.txt -m seq
```

始终选用列表第一个有效代理，适合固定线路测试。

---

## 🌐 支持代理格式

工具自动标准化各类简写格式（通过

`--default-scheme`

 指定默认协议）

表格

| 输入格式 | 自动转换结果 |
| --- | --- |
| 127.0.0.1:8080 | http://127.0.0.1:8080 |
| user:pass@127.0.0.1:8080 | http://user:pass@127.0.0.1:8080 |
| http://x.x.x.x:port | 直接原样使用 |
| socks5://x.x.x.x:port | 直接原样使用 |

> 默认协议：
>
> `http`
>
> ，可通过
>
> `--default-scheme socks5`
>
>  修改。

---

## 🔍 协议过滤

参数：

`--filter`

- `all`：加载池内全部代理（默认）
- `http-only`：仅保留 `http://` 代理
- `socks-only`：仅保留 `socks5://` 代理

bash

```
# 只使用 socks5 代理
python daili.py -f proxy.txt -m random --filter socks-only
```

---

## 🔄 自动轮换刷新

参数：

`--loop`

 设置刷新秒数，定时重新加载代理池并切换代理

bash

```
python daili.py \
-f proxy.txt \
-m random \
--loop 60
```

运行流程：

1. 加载代理列表 → 选择代理
2. 休眠指定时长
3. 重新拉取代理池并更新当前代理

适合动态代理池、长时间持续运行任务。

---

## 🌍 读取系统已有代理

参数：

`--use-env-proxy`

 读取系统环境变量：

`ALL_PROXY > HTTP_PROXY > HTTPS_PROXY`

，并入代理池。

bash

```
python daili.py -f proxy.txt --use-env-proxy
```

---

## 🖥️ 本地中转代理服务

参数：

`--local-proxy`

 启动内置 HTTP 中转代理，统一入口转发至上游动态代理。

 默认地址：

`127.0.0.1:8899`

数据流：

plaintext

```
应用程序
    ↓
127.0.0.1:8899 (Daili本地代理)
    ↓
动态上游代理（自动轮换）
    ↓
目标站点
```

启动命令：

bash

```
python daili.py -f proxy.txt -m random --local-proxy
```

可自定义监听地址与端口：

bash

```
python daili.py -f proxy.txt --local-proxy --local-ip 0.0.0.0 --local-port 9999
```

---

## 🔐 本地代理鉴权

为本地中转代理增加账号密码保护

bash

```
python daili.py \
-f proxy.txt \
--local-proxy \
--local-user admin \
--local-pass 123456
```

访问地址：

plaintext

```
admin:123456@127.0.0.1:8899
```

---

## 📤 导出终端环境变量

参数：

`--export-env`

 输出环境变量脚本，注入当前终端会话代理配置

 输出变量：

`HTTP_PROXY`

 /

`HTTPS_PROXY`

 /

`ALL_PROXY`

 /

`PROXY_URL`

工具

**自动识别父终端类型**

，输出对应语法：

### Windows CMD

cmd

```
for /f "delims=" %%x in ('python daili.py -f proxy.txt -m random --export-env') do set "%%x"
```

### Windows PowerShell

powershell

```
python daili.py -f proxy.txt -m random --export-env | iex
```

### Linux / macOS Shell

bash

```
eval $(python3 daili.py -f proxy.txt -m random --export-env)
```

> ⚠️ 底层原理：子进程无法直接修改父终端环境，依靠打印脚本由父终端执行赋值。

---

## 📌 使用示例

### 1. 单次随机选取代理

bash

```
python daili.py -f proxy.txt -m random
```

### 2. 启动本地中转代理

bash

```
python daili.py -f proxy.txt -m random --local-proxy
```

### 3. 每 30 秒自动刷新代理

bash

```
python daili.py -f proxy.txt -m random --loop 30
```

### 4. 输出环境变量配置（PowerShell 示例）

powershell

```
python daili.py -f proxy.txt -m seq --export-env | iex
```

### 5. 全局上游代理账号（所有不带 auth 的代理统一账号密码）

bash

```
python daili.py -f proxy.txt --proxy-user user --proxy-pass password
```

---

## ⚙️ 完整参数说明

表格

| 参数 | 说明 |
| --- | --- |
| -f, --file | 代理来源：本地文件 /http 链接 / - (标准输入) |
| -m, --mode | 代理选取模式：random /seq |
| --filter | 协议过滤：all /http-only/socks-only |
| --default-scheme | 无协议前缀代理默认协议，http /socks5 |
| --loop | 自动刷新间隔 (秒)，0 = 仅执行一次 |
| --export-env | 输出适配当前终端的环境变量脚本 |
| --use-env-proxy | 将系统环境代理加入代理池 |
| --proxy-user | 上游代理全局默认账号 |
| --proxy-pass | 上游代理全局默认密码 |
| --local-proxy | 开启本地 HTTP 中转代理服务 |
| --local-ip | 本地代理监听 IP，默认 127.0.0.1 |
| --local-port | 本地代理监听端口，默认 8899 |
| --local-user | 本地代理 Basic Auth 用户名 |
| --local-pass | 本地代理 Basic Auth 密码 |

---

## 💡 项目定位

Daili 面向开发人员用于：

- 简易代理池轮换管理
- 网络抓包、接口测试
- 自动化脚本动态切换出口代理
- 快速临时切换终端系统代理环境

# 🔗 URLJM

## URL Hash Encryption & Short Link System

URLJM 是一个基于哈希算法的 URL 混淆加密短链接服务。

 它可以将较长的 URL 转换为短格式哈希链接，同时隐藏原始 URL 信息，实现链接缩短和匿名混淆。

 项目内置 Web 管理界面，支持用户登录、短链接生成、链接记录管理、管理员控制以及访问配置。

---

## ✨ 核心功能

### 🔐 URL 哈希混淆

URLJM 使用 MD5 哈希生成短链接标识。

 用户输入：

`https://example.com/very/long/path?id=123456`

 系统生成：

`http://your-domain/hashcode`

生成后的链接作用：

- 缩短 URL 长度
- 隐藏原始地址
- 避免直接暴露目标 URL
- 方便分享和管理

系统支持自定义哈希长度：

- 哈希长度可全局配置
- 取值范围：4～16 位

### 🔗 短链接生成

用户登录后，可通过 Web 页面生成新的短链接。

**生成流程**

plaintext

```
用户输入长 URL
 ↓
系统验证 URL
 ↓
生成 MD5 哈希并截取短码
 ↓
保存 URL 映射关系
 ↓
返回可用短链接
```

生成记录自动归属当前登录用户。

### 📋 链接记录管理

每个用户拥有独立的短链接记录列表。

 支持操作：

- 查看全部已生成链接历史
- 自主删除个人创建的链接
- 页面一键复制短链接

列表展示信息：原始 URL、短链接哈希编号、创建时间、操作按钮

### 👤 用户系统

URLJM 内置完整账号认证系统。

 用户通过

**用户名 + 密码**

完成登录，登录后创建会话。

 会话采用 Cookie 存储：

`sid`

，启用 HttpOnly 属性，提升会话安全。

### 👥 用户权限管理

系统划分两类角色：普通用户、管理员

**普通用户权限**

- 登录系统
- 创建短链接
- 查看自有链接记录
- 删除自己创建的链接

**管理员额外权限**

- 创建、删除用户账号
- 修改用户每日生成限额
- 修改全局系统配置
- 调整哈希短码长度
- 开启 / 关闭访客模式

### 📊 生成次数限制

支持为用户配置每日短链接生成上限。

 用户面板实时展示统计信息：

> 今日已生成 / 每日限制、剩余可生成次数、当前哈希长度

示例展示：

`5 / 20  剩余 15 次  哈希长度 8`

 管理员可单独调整每位用户每日生成额度。

### 🌐 访客模式

管理员可自主配置访客相关规则：

- 是否允许游客无需登录直接生成短链接
- 设置游客每日生成数量上限

适合搭建公共短链服务、临时分享场景。

### ⚙️ 管理后台

管理员后台提供三大模块：

**用户管理**

- 创建账号、重置密码
- 设置用户每日生成额度
- 删除用户

**系统配置**

- 调整哈希长度（范围 4～16）
- 开启 / 关闭访问跳转日志

**访客配置**

- 启用 / 禁用游客生成功能
- 设置游客每日限额

### 🖥️ Web 服务

URLJM 内置独立 HTTP Web 服务。

访问流程：

plaintext

```
浏览器
 ↓
URLJM 内置 Web 服务
 ↓
本地数据库
 ↓
URL 映射与跳转逻辑
```

内置页面：登录页、用户操作面板、管理员后台、短链接生成页面。

## 🚀 启动方式

基础启动命令

bash

```
python urljm.py
```

程序启动后控制台输出信息：

 哈希 URL 混淆加密 + 短链接服务 v2.0

 监听 IP

 监听端口

 管理员账号

 访问日志当前状态

## ⚙️ 命令行启动参数

- `--bind-ip` / `-i`：修改服务监听地址 示例：`python urljm.py --bind-ip 0.0.0.0`
- `--port` / `-p`：修改服务端口 示例：`python urljm.py --port 8080`
- `--admin-user` / `-au`：自定义初始管理员账号 示例：`python urljm.py --admin-user admin`
- `--admin-pass` / `-ap`：自定义初始管理员密码
- `--default-limit` / `-dl`：设置新用户默认每日生成额度
- `--no-access-log` / `-nal`：关闭访问跳转日志

## 🗂️ 数据持久化

程序自动本地持久化存储以下数据：

- 用户账号与密码信息
- 用户会话 Session
- 短链接与原始 URL 映射关系
- 用户短链接生成记录
- 全部系统运行配置

## 🛠️ 技术特点

- 单文件脚本运行，部署简单
- 内置原生 HTTP 服务，无需额外 Web 框架
- 完善多用户体系与权限隔离
- 个人短链接数据隔离
- 可视化 Web 管理员后台
- 全部配置支持动态修改

## 📌 使用场景

URLJM 适用于：

- 自建个人短链接服务
- 内网环境 URL 管理
- 隐藏原始长链接地址
- 临时分享链接场景
- URL 简易混淆处理
- 小型团队内部链接管理

## ⚠️ 注意事项

URLJM 使用 MD5 仅用于生成唯一短链接标识，实现链接缩短、地址隐藏、便捷分享。

**它不属于密码学加密方案。**

 MD5 短码无法提供高强度加密保护，请勿用于需要高保密级别的隐私链接场景。

# 🌐 TZ

## IP Probe & Access Tracking Tool

TZ 是一款轻量级 IP 探针工具，用于采集、记录访问者 IP、请求头、访问时间等网络信息。

 当访客访问探针地址时，TZ 自动留存访问日志，并将客户端 302 重定向至预设目标地址；内置受密钥保护的 Web 日志面板，可随时查看完整访问记录。

---

## ✨ 功能特点

### 🎯 IP 探针核心服务

启动 HTTP 探针接收访问请求。

 访问地址示例：

`http://your-server:8080`

收到请求后自动执行：

1. 获取访问客户端 IP
2. 自动识别 IPv4 / IPv6 类型
3. 提取 User-Agent
4. 完整保存全部 HTTP 请求头
5. 写入本地访问日志
6. 返回 302 跳转至目标网址

默认跳转地址：

`https://ifconfig.io`

### 📡 访问信息完整记录

单条访问日志数据结构示例

json

```
{
    "seq": 1,
    "time": "2026-01-01 12:00:00",
    "client_ip": "1.2.3.4",
    "ip_type": "IPv4",
    "user_agent": "Mozilla/5.0",
    "raw_headers": {}
}
```

记录字段说明：

- `seq`：自增序号，快速定位单条访问记录
- `time`：精确访问时间
- `client_ip`：客户端真实 IP，同时兼容 IPv4 / IPv6
- `ip_type`：IP 协议类型自动识别
- `user_agent`：客户端设备 / 程序标识（浏览器、curl、requests 等）
- `raw_headers`：完整原始 HTTP 请求头

### 🔄 真实 IP 获取策略

TZ 支持两种场景 IP 识别方案：

1. **直连环境**：直接读取客户端连接地址
2. **反向代理 / CDN 环境**：优先解析 `X-Forwarded-For`，取列表第一个公网 IP

适配 Nginx、各类网关、CDN 转发场景。

### 🔀 自动跳转机制

探针不会展示静态页面，收到访问后立即返回

**HTTP 302 重定向**

。

 支持自定义跳转目标：

bash

```
--redirect https://example.com
```

访问流程

plaintext

```
访问者 → HTTP请求 → TZ探针 → 记录全部访问信息 → 写入日志 → 302跳转 → 目标网站
```

### 📊 Web 日志管理面板

独立端口运行可视化日志页面

 默认地址：

`http://服务器IP:8081/?key=密钥`

面板功能：

- 展示全部访问日志列表
- 一键展开查看单条完整原始请求数据

### 🔐 面板访问安全控制

日志页面必须携带正确密钥参数，未授权访问直接返回

`403 Forbidden`

。

手动指定密钥启动示例：

bash

```
python tz.py --pw mypassword
```

访问地址示例：

plaintext

```
http://127.0.0.1:8081/?key=mypassword
```

### 🔑 随机密钥自动生成

不手动指定密钥时，程序自动生成随机密钥并在控制台输出。

 默认随机密钥长度：16 位，支持自定义长度。

bash

```
python tz.py --rand-key-len 32
```

### 🖥️ 跨平台信号优化

针对 Windows / Linux 系统优化进程退出逻辑：

- Windows：控制台事件捕获
- Linux：支持 `SIGINT` / `SIGTERM` 信号
- Socket 安全关闭、服务优雅停止、线程回收 实现**单次 Ctrl+C 即可正常退出程序**。

### 🗑️ 临时日志模式

参数

`--dd`

 开启临时模式：程序退出自动删除日志文件。

bash

```
python tz.py --dd
```

适用场景：一次性临时探针、短期测试，无需持久留存访问记录。

---

## ⚙️ 完整命令参数

表格

| 参数 | 说明 |
| --- | --- |
| -b / --bind | 服务监听地址 |
| -p / --port | 探针主服务端口 |
| -ap / --admin-port | 日志管理面板端口 |
| --log | 自定义日志文件名称 |
| --redirect | 探针访问后的 302 跳转地址 |
| -pw / --pw | 自定义日志面板访问密钥 |
| -rkl / --rand-key-len | 自动生成随机密钥长度 |
| --dd | 临时模式，程序退出自动删除日志 |

## 🚀 使用示例

### 基础启动（默认配置）

bash

```
python tz.py
```

- 探针地址：`http://0.0.0.0:8080`
- 日志面板：`http://0.0.0.0:8081/?key=随机密钥`

### 自定义探针与面板端口

bash

```
python tz.py \
-p 9000 \
-ap 9001
```

### 修改访问跳转目标

bash

```
python tz.py --redirect https://example.com
```

### 手动设置后台访问密码

bash

```
python tz.py --pw 123456
```

### 临时探针模式（退出自动清理日志）

bash

```
python tz.py --dd
```

## 📌 适用场景

- 线上 / 内网 IP 探测溯源
- 网络连通性测试
- 访问来源、客户端 UA 分析
- 代理、VPN 连通性测试
- CDN、反向代理真实 IP 验证
- HTTP 请求头采集分析
- 短期临时访问行为追踪

## 🛠️ 项目特点

- 单 Python 文件运行，部署简单
- 无额外第三方依赖
- 内置原生 HTTP Web 服务
- 同时支持 IPv4、IPv6 识别
- 完整采集全部 HTTP 请求头
- 可视化密钥保护日志面板
- Windows / Linux 全平台兼容
- 优化信号处理，一键优雅退出
- 支持临时日志自动清理模式

> ⚠️ 提示：本工具仅用于自身授权网络环境测试，请勿用于未经许可的访问追踪。
