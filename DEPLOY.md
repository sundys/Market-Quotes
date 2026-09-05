# 后端部署指南

后端是一个普通的 Python 长驻进程（FastAPI + yfinance + AKShare + 缓存），推荐用 Docker 部署在任意一台常驻机器上：国内/海外轻量 VPS、家里 NAS、公司内网服务器均可。

> 上一轮已论证：Cloudflare Workers/Pages 无法运行本后端（curl_cffi 原生依赖 + AKShare 无 JS 等价物 + 无常驻进程模型）。本文描述的是可行的部署方式。

---

## 方式一：Docker Compose（推荐）

### 1. 准备机器

任意装了 Docker 26+ 与 Docker Compose v2 的 Linux 机器：

```bash
curl -fsSL https://get.docker.com | sh
```

### 2. 选址建议（重要）

部署前先在候选机器上实测 Yahoo 连通性——Yahoo 对不同 IP 段的限速差异很大：

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1d&interval=1d"
```

- 返回 `200` 或偶发 `429`：可用（偶发 429 后端会自动退避重试）
- 持续 `429`：换机房再测
- AKShare（上海黄金）走国内源，任何机房都可达

### 3. 启动

```bash
git clone https://github.com/sundys/Market-Quotes.git
cd Market-Quotes

# 准备环境变量（按需修改采集间隔等参数）
cp server/.env.example .env

docker compose up -d
```

镜像来源二选一：
- **CI 镜像**（默认）：`docker compose up -d` 会直接拉取 GitHub Actions 推送的 `ghcr.io/sundys/market-quotes-backend:latest`
- **本地构建**：`docker compose up -d --build`（改了 server/ 代码后用这个）

### 4. 验证

```bash
# 健康检查：看数据源状态、429 计数、缓存命中、最后成功时间
curl http://127.0.0.1:8000/health | python3 -m json.tool

# 首页行情
curl http://127.0.0.1:8000/api/market/overview
```

首次启动后 yfinance/SGE 采集器需要几秒到几十秒填入第一批数据。

### 5. 更新

```bash
git pull
docker compose pull          # 用 CI 镜像
docker compose up -d
```

### 6. 日志与数据

```bash
docker compose logs -f backend     # 采集日志（含 429/退避/成功）
docker compose restart backend     # 重启
```

磁盘缓存快照存在 named volume `market_cache`（容器内 `/data`），容器重建后自动恢复最近一次有效行情，不会把旧数据伪装成实时（恢复的数据会按采集时间正常展示，但缓存快照恢复的行情在数据源恢复前会保持上次状态）。

---

## 方式二：systemd 裸机部署（不用 Docker）

```bash
cd Market-Quotes/server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`/etc/systemd/system/market-quotes.service`：

```ini
[Unit]
Description=Market Quotes Backend
After=network-online.target

[Service]
WorkingDirectory=/opt/Market-Quotes/server
ExecStart=/opt/Market-Quotes/server/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=APP_ENV=production
Environment=DATA_DIR=/opt/Market-Quotes/server/cache

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now market-quotes
```

---

## 防火墙

只放行需要的端口，后端没有任何鉴权，不要暴露到公网任意访问范围之外的场景外：

```bash
# UFW 示例：只允许 App 用户网段访问（按需收紧）
sudo ufw allow 8000/tcp
```

当前 `/api/*` 是公开只读接口（只读缓存，无敏感信息），后续如需限制可在前面加 Nginx/Caddy 做来源白名单或 Basic Auth。

---

## App 侧配置

后端地址不写死在代码里：安装 App 后在「设置 → 后端地址」中填入你的服务器地址（如 `http://<服务器IP>:8000`），保存后立即生效并持久化在设备本地。

> release 包已在 AndroidManifest 中声明 `INTERNET` 权限并开启 `usesCleartextTraffic`，允许 `http://` 明文访问；改用 HTTPS 更安全，只需在设置里填 `https://` 地址。

### 正式签名（可选）

- 本地：参照 `app/android/key.properties.example` 生成 `app/android/key.properties` 并把 keystore 放到 `app/android/` 下（已 gitignore），之后 `flutter build apk --release` 即为正式签名；未配置时自动回退 debug 签名
- CI：在 GitHub 仓库 Settings → Secrets and variables → Actions 配置 4 个 Secrets：`KEYSTORE_BASE64`（keystore 文件 base64，`base64 -w0 upload-keystore.jks` 生成）、`KEYSTORE_PASSWORD`、`KEY_ALIAS`、`KEY_PASSWORD`，配置后 `build-android.yml` 会自动额外产出 `market-quotes-release-apk` artifact

---

## GitHub Actions 自动化

| 工作流 | 触发 | 产物 |
|---|---|---|
| `build-android.yml` | push 到 main（app/** 变更）或手动 | 正式版 APK 按 ABI 拆分：**armv7**（`armeabi-v7a`）与 **arm64**（`arm64-v8a`）两个独立 artifact |
| `docker.yml` | push 到 main（server/** 变更）、打 `v*` tag 或手动 | 多架构镜像（amd64 + arm64）推送到 `ghcr.io/sundys/market-quotes-backend` |

镜像 tag 规则：
- `latest`：main 分支最新构建
- `v1.2.3`：对应 git tag
- `sha-xxxxxxx`：具体提交，便于回滚

首次推送后镜像默认是 private，如需匿名拉取，在 GitHub 仓库 → Packages → 该镜像 → Package settings 中改为 public。

---

## 监控与运维要点

- **`GET /health`** 是唯一的健康出口：`yfinance.rate_limit_count`（429 次数）、`in_cooldown`（是否冷却中）、`cache.*_last_success`（最后成功时间）。接 Uptime Robot / 告警脚本轮询即可
- **数据 stale 判断**：`/api/market/overview` 中每个 item 的 `is_stale` 与 `timestamp`，App 已做展示，无需额外处理
- **重启策略**：容器 `restart: unless-stopped`；进程崩溃 systemd `Restart=always`。重启不丢缓存（磁盘快照）
- **不要调小采集间隔**：Yahoo 429 的解法是"更低频 + 批量 + 缓存"，不是加机器加请求
