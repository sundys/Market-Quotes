# Market-Quotes 极简行情 App

打开即看、一眼知道涨跌的极简金融行情 App：

- 国际黄金（XAU/USD）
- 纳斯达克 100（^NDX）
- 标普 500（^GSPC）
- 上海黄金 Au99.99（元/克）

第一阶段只有行情展示：当前价格、涨跌额、涨跌幅、极简迷你走势图。无交易、无资讯、无账户。

## 架构

```text
akshare 生态（全部国内数据源，无 Yahoo）
    ├── 东方财富：美股三大指数实时与 K 线（自带 UA/Referer）
    ├── 新浪外盘：COMEX 黄金期货实时与日线
    ├── 上海黄金交易所：Au99.99 实时与历史
    ├── 内存缓存 + 磁盘 JSON 快照
    └── 后台采集器（定时、限速退避、冷却、三源互相隔离）
```

> 已彻底移除 Yahoo Finance 数据源（其 429 限流长期不稳定）。

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
- **低频采集**：指数 45s、黄金 30s 一次（可配置），休市自动降频到 5 分钟。
- **三源隔离**：东财（指数）/ 新浪外盘（期金）/ SGE 各自独立的健康状态、退避冷却与请求锁；任一源失败只标记对应行情 stale。
- **429/限流处理**：指数退避（5s 起、上限 120s）+ 随机抖动；持续失败进入冷却，暂停主动请求，期间继续返回缓存。
- **stale 标识**：失败时保留最后有效数据并明确标记，UI 显示"部分数据可能延迟 / 更新于 HH:mm"，不伪装实时。
- **开闭市**：按市场时区计算交易状态，UI 显示"交易中 / 已收盘"。
- **测试降级**：设置 `YF_FORCE_429=1` 启动后端即可模拟全部外部源失败，验证退避/冷却/降级。

## 已知行为说明

- 所有行情数据来自国内源（东财/新浪/上金所），无 Yahoo 依赖；若东财接口异常，指数卡片显示 `--`，黄金数据不受影响，恢复后自动重新采集。
- 国际黄金为 COMEX 黄金期货（接近全天交易），UI 已明确标注"期货"；与伦敦现货存在正常价差。
- SGE 实时接口只提供现价，涨跌幅基于最近交易日收盘价计算；日内走势为后端累积的采样点（后端重启后重新累积）。
- 美股/SGE 开闭市判断未含节假日（第一阶段简化）。
