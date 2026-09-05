# Market-Quotes 极简行情 App

打开即看、一眼知道涨跌的极简金融行情 App：

- 国际黄金（XAU/USD）
- 纳斯达克 100（^NDX）
- 标普 500（^GSPC）
- 上海黄金 Au99.99（元/克）

第一阶段只有行情展示：当前价格、涨跌额、涨跌幅、极简迷你走势图。无交易、无资讯、无账户。

## 架构

```text
Flutter App
    │  HTTPS（GET /api/market/overview）
    ▼
Python FastAPI 后端
    ├── yfinance（批量采集 XAUUSD=X / ^NDX / ^GSPC）
    ├── AKShare（上海黄金交易所 Au99.99）
    ├── 内存缓存 + 磁盘 JSON 快照
    └── 后台采集器（定时、限速退避、429 冷却）
```

App 不直接访问 Yahoo Finance / AKShare（AGENTS.md 第 3/26 节）。

## 目录

```text
app/       Flutter 客户端
server/    FastAPI 后端
tests/     后端单元测试（pytest）
ss.jpg     首页视觉参考图
```

## 启动后端

```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- 首页数据：`GET /api/market/overview`
- 详情走势：`GET /api/market/{id}/history?period=1d|1w|1m|6m|1y`（天/周/月/半年/年；SGE 当日走势为后端累积采样点）
- 健康检查/监控：`GET /health`（含 429 计数、缓存命中、最后成功时间）

环境变量见 `server/.env.example`（采集间隔、退避参数、缓存 TTL 等）。

## 运行 App

```bash
cd app
flutter pub get
flutter run
```

后端地址不写死在代码里：首次打开在「设置 → 后端地址」填入你的服务地址（如 `http://192.168.1.10:8000`），保存即生效。

## 部署

服务器部署（Docker Compose / systemd）、GitHub Actions 自动构建与 ghcr.io 镜像说明，见 [DEPLOY.md](DEPLOY.md)。

## 构建与测试

```bash
# 后端
python -m pytest tests -q

# Flutter
flutter analyze
flutter test
flutter build apk --debug
# 产物：app/build/app/outputs/flutter-apk/app-debug.apk
```

## 稳定性设计（对应 AGENTS.md 第 6/7/9/20 节）

- **缓存优先**：App 打开先读本地最近数据，后台请求后端更新；后端一级内存缓存 + 二级磁盘快照。
- **请求合并**：三个 yfinance 标的合并为一次 `yf.download` 批量请求。
- **低频采集**：yfinance 默认 45s 一次、SGE 默认 30s 一次（可配置），休市自动降频到 5 分钟。
- **429 处理**：指数退避（5s 起、上限 120s）+ 随机抖动；持续 429 进入冷却，暂停主动请求，期间继续返回缓存。
- **异常隔离**：单数据源失败只把对应行情标记 `is_stale`，另一数据源正常返回。
- **stale 标识**：失败时保留最后有效数据并明确标记，UI 显示"部分数据可能延迟 / 更新于 HH:mm"，不伪装实时。
- **开闭市**：按市场时区计算交易状态，UI 显示"交易中 / 已收盘"。
- **测试 429**：设置 `YF_FORCE_429=1` 启动后端即可模拟持续限速，验证退避/冷却/降级。

## 已知行为说明

- 若 Yahoo Finance 对服务器 IP 持续限速，国际黄金/指数卡片显示 `--`，上海黄金不受影响；恢复后自动重新采集。
- SGE 实时接口只提供现价，涨跌幅基于最近交易日收盘价计算；日内走势为后端累积的采样点。
- 美股/SGE 开闭市判断未含节假日（第一阶段简化）。
