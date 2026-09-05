# AGENTS.md

## 1. 项目定位

本项目是一款**极简金融行情查看 App**，核心目标是让用户打开 App 后，可以第一时间看到：

1. 国际黄金行情
2. 上海黄金交易所国内黄金行情
3. 纳斯达克指数行情
4. 标普 500 指数行情
5. 各行情当前价格、涨跌额、涨跌幅
6. 根据需要提供极简的日内走势/历史走势查看

App 不以交易、下单、资讯、社区、复杂指标为目标，第一阶段只专注于**快速、清晰、低干扰地查看涨跌幅**。

---

## 2. 开发原则

### 2.1 核心原则

- 首页必须极简。
- 用户打开 App 后优先看到行情，不显示复杂启动页。
- 涨跌幅是最重要的信息，价格是第二重要信息。
- 正常情况下首页只需要展示核心行情卡片，不堆叠新闻、资讯、指标。
- 不实现交易功能。
- 不实现账户、资金、证券交易等功能。
- 不为了“功能丰富”增加无关页面。
- 所有网络请求必须有超时、重试、缓存和降级处理。
- 第三方行情数据异常时，App 不得崩溃。
- 必须明确区分“最新行情时间”和“App 当前时间”。
- 必须避免把历史缓存数据伪装成实时数据。

### 2.2 UI 原则

整体 UI 按用户提供的“图片四”参考设计执行：

- 极简
- 大留白
- 清晰层级
- 少量颜色
- 卡片/分组简洁
- 不使用复杂渐变
- 不使用大量阴影
- 不使用过度装饰
- 动画短、轻、克制
- 重点突出价格和涨跌幅
- 保持现代移动端金融行情 App 的视觉感

如果参考图片与本文件的文字要求发生冲突，优先遵循用户最新明确要求。

> 注意：当前开发文档不假定参考图中的具体色值、字体和间距；实际开发时应以项目中提供的“图片四”参考图为最终视觉基准。

---

# 3. 技术架构

推荐采用：

```text
Flutter App
    │
    │ HTTPS
    ▼
Python FastAPI 后端
    │
    ├── yfinance
    │
    ├── AKShare
    │
    ├── 内存缓存
    │
    └── 本地/磁盘缓存
```

App **不得直接访问 Yahoo Finance 或 AKShare 数据源**。

原因：

1. 防止第三方接口地址暴露在 APK 中。
2. 防止 API 请求数量随着 App 用户数量线性增加。
3. 可以统一处理 429。
4. 可以统一缓存行情。
5. 可以统一处理异常和数据源切换。
6. 后续更换数据源时无需修改 App。
7. 可以控制客户端刷新频率。

---

# 4. 数据源

## 4.1 国际黄金、纳斯达克、标普500：yfinance

使用开源项目：

```text
yfinance
```

GitHub：

```text
https://github.com/ranaroussi/yfinance
```

yfinance 通过 Yahoo Finance 数据服务获取市场数据。

第一阶段建议使用以下标的：

| App名称 | Yahoo Finance Symbol | 说明 |
|---|---|---|
| 国际黄金 | XAUUSD=X | 黄金/美元 |
| 纳斯达克100 | ^NDX | Nasdaq 100 |
| 纳斯达克综合 | ^IXIC | Nasdaq Composite |
| 标普500 | ^GSPC | S&P 500 |

最终首页默认使用：

```text
国际黄金
纳斯达克100
标普500
上海黄金 Au99.99
```

如果项目实际测试发现 XAUUSD=X 的实时/最新数据稳定性不足，可以将国际黄金数据源调整为黄金期货 GC=F，但必须在代码和 UI 中明确标注“黄金期货”，不能把期货价格伪装成现货黄金。

---

# 5. 上海黄金交易所数据：AKShare

使用：

```text
AKShare
```

官方文档：

```text
https://akshare.akfamily.xyz/data/spot/spot.html
```

上海黄金交易所相关接口包括：

```python
ak.spot_quotations_sge(symbol="Au99.99")
```

用于实时行情。

以及：

```python
ak.spot_hist_sge(symbol="Au99.99")
```

用于历史行情。

AKShare 官方文档当前明确列出：

- `spot_quotations_sge`：上海黄金交易所实时行情走势
- `spot_hist_sge`：上海黄金交易所历史行情走势
- `spot_golden_benchmark_sge`：上海金基准价

其中 `spot_quotations_sge` 返回：

```text
品种
时间
现价
更新时间
```

项目必须优先使用：

```text
Au99.99
```

作为国内黄金首页默认品种。

注意：

AKShare 是 Python 数据接口库，并不等于数据本身。后端必须对返回数据的时间、价格和异常情况进行校验。

---

# 6. yfinance 429 限速处理

这是本项目的重点。

不能采用：

```text
App打开
↓
每次直接请求 Yahoo
↓
每个行情单独请求
↓
用户不断刷新
```

这种架构极易触发 429。

必须采用：

```text
定时后台采集
        ↓
统一缓存
        ↓
App读取缓存
```

## 6.1 Session 复用

后端必须尽可能复用 HTTP Session，减少重复建立连接和 Cookie/Crumb 获取。

当前 yfinance 优先使用 `curl_cffi` HTTP 后端；不要人为禁用该机制。

建议依赖：

```text
yfinance
curl_cffi
```

如果当前 yfinance 版本已经自动管理 curl_cffi，则按照当前版本的官方方式使用，不重复实现 Cookie/Crumb。

---

## 6.2 请求合并

不要：

```text
请求 ^NDX
请求 ^GSPC
请求 XAUUSD=X
```

三个完全独立的高频请求。

应尽量批量获取：

```python
yf.download(
    ["XAUUSD=X", "^NDX", "^GSPC"],
    ...
)
```

具体调用方式以当前安装的 yfinance 版本 API 为准。

---

## 6.3 请求频率

不要让客户端决定 Yahoo 请求频率。

推荐：

```text
Yahoo/yfinance采集器：
正常运行：30~60 秒一次

上海黄金交易所：
正常运行：15~30 秒一次

App：
打开时先读取缓存
之后通过自己的后端进行刷新
```

实际频率必须根据数据源稳定性和网络环境调整。

不要为了追求“看起来实时”而每 1 秒请求一次 Yahoo。

---

# 7. 429 专用处理策略

参考用户指定文章：

```text
https://blog.csdn.net/gitblog_00291/article/details/151145655
```

文章重点包括：

- YFRateLimitError
- 429 检测
- 指数退避
- Session 复用
- Cookie 持久化
- 请求间隔控制
- 批量处理
- 缓存优先
- 请求监控

本项目必须将这些原则整合到后端。

---

## 7.1 指数退避

发生 429 时：

```text
第1次：等待 5 秒
第2次：等待 10 秒
第3次：等待 20 秒
第4次：等待 40 秒
```

具体最大等待时间必须设置上限。

建议：

```text
base_delay = 5
max_delay = 120
max_retries = 3~5
```

禁止无限重试。

---

## 7.2 随机抖动

多个后端任务同时失败时，不能全部在相同时间重新请求。

建议：

```text
delay = min(base * 2^retry, max_delay) + random_jitter
```

避免形成请求尖峰。

---

## 7.3 429 后暂停采集

如果某一数据源连续触发 429：

```text
进入冷却状态
↓
暂停主动请求
↓
继续向 App 返回最近一次有效缓存
↓
后台等待冷却时间
↓
再次尝试
```

不能继续高速重试。

---

# 8. 多级缓存

必须采用多级缓存：

```text
一级：内存缓存
二级：磁盘缓存
三级：App 本地最近数据
```

行情对象至少保存：

```json
{
  "symbol": "^GSPC",
  "price": 6487.32,
  "change": 12.34,
  "change_percent": 0.19,
  "timestamp": "2026-09-05T12:30:00+08:00",
  "source": "yfinance",
  "market_status": "open",
  "is_stale": false
}
```

---

# 9. 缓存策略

## 9.1 正常状态

如果数据源正常：

```text
更新缓存
↓
记录 timestamp
↓
App读取最新缓存
```

## 9.2 数据源暂时失败

如果请求失败：

```text
保留最后一次有效数据
```

但必须：

```text
is_stale = true
```

App 中可以显示：

```text
数据更新于 12:28
```

而不能继续显示成“实时”。

---

# 10. 后端 API

建议设计为：

```text
GET /api/market/overview
```

一次返回首页全部行情。

例如：

```json
{
  "updated_at": "2026-09-05T12:30:00+08:00",
  "items": [
    {
      "id": "gold_global",
      "name": "国际黄金",
      "symbol": "XAUUSD=X",
      "price": 3521.80,
      "change": 18.60,
      "change_percent": 0.53,
      "currency": "USD",
      "unit": "oz",
      "source": "yfinance",
      "timestamp": "2026-09-05T12:29:50+08:00",
      "is_stale": false
    },
    {
      "id": "nasdaq100",
      "name": "纳斯达克100",
      "symbol": "^NDX",
      "price": 23456.78,
      "change": 125.30,
      "change_percent": 0.54,
      "currency": "USD",
      "source": "yfinance",
      "timestamp": "2026-09-05T12:29:50+08:00",
      "is_stale": false
    },
    {
      "id": "sp500",
      "name": "标普500",
      "symbol": "^GSPC",
      "price": 6487.32,
      "change": -12.45,
      "change_percent": -0.19,
      "currency": "USD",
      "source": "yfinance",
      "timestamp": "2026-09-05T12:29:50+08:00",
      "is_stale": false
    },
    {
      "id": "gold_cn",
      "name": "上海黄金 Au99.99",
      "symbol": "Au99.99",
      "price": 755.00,
      "change": null,
      "change_percent": null,
      "currency": "CNY",
      "unit": "g",
      "source": "AKShare/SGE",
      "timestamp": "2026-09-05T12:28:55+08:00",
      "is_stale": false
    }
  ]
}
```

实际字段根据最终数据源返回结果调整。

---

# 11. 涨跌幅计算

所有行情统一使用：

```text
change = current_price - previous_close

change_percent =
(current_price - previous_close)
/
previous_close
× 100
```

注意：

- 不要使用 App 本地时间自行推算涨跌幅。
- 优先使用数据源提供的 previous close。
- 如果数据源没有直接提供 change/change_percent，后端计算。
- 必须统一小数位。
- 黄金价格和指数价格的小数位可以不同。

---

# 12. 上海黄金涨跌幅计算

对于：

```text
Au99.99
```

如果实时接口只提供：

```text
现价
```

则需要使用最近有效交易日的收盘价作为 previous close。

推荐流程：

```text
实时 Au99.99
        ↓
读取最近交易日历史行情
        ↓
获取 previous close
        ↓
计算涨跌额
        ↓
计算涨跌幅
```

交易日切换时必须正确更新 previous close。

不能把上一条实时数据直接当作涨跌基准。

---

# 13. 市场开闭市处理

后端必须知道不同市场交易时间。

至少区分：

```text
美股市场
上海黄金交易所
```

市场关闭时：

- 不需要频繁请求。
- 首页显示最后有效价格。
- 显示“已收盘”或“休市”。
- 显示最后更新时间。
- 不应把旧价格显示成实时跳动数据。

---

# 14. App 首页

首页是整个 App 的核心。

推荐结构：

```text
顶部
日期 / 市场状态

↓

国际黄金

价格
涨跌额
涨跌幅

↓

纳斯达克100

价格
涨跌额
涨跌幅

↓

标普500

价格
涨跌额
涨跌幅

↓

上海黄金 Au99.99

价格
涨跌额
涨跌幅
```

默认不要添加：

- 新闻
- 新闻推荐
- 股票列表
- 复杂技术指标
- RSI
- MACD
- KDJ
- 交易入口
- 社区
- 广告区域
- 多余按钮

---

# 15. 行情卡片设计

每张行情卡片只突出：

```text
名称

当前价格

涨跌额
涨跌幅
```

例如：

```text
国际黄金

$3,521.80

+18.60   +0.53%
```

涨跌幅必须比涨跌额更醒目。

可以根据用户提供的参考图片使用极简卡片或无边框分组方式。

---

# 16. 涨跌颜色

必须考虑不同地区用户习惯。

默认采用：

```text
上涨：红色
下跌：绿色
持平：中性色
```

因为本 App 主要面向中文用户。

但所有颜色必须集中定义，不能在页面中散落硬编码。

---

# 17. 实时刷新动画

行情变化时不要刷新整个页面。

只更新：

```text
价格
涨跌额
涨跌幅
```

建议动画：

```text
150~300ms
```

可采用：

- 数字轻微淡入
- 数字轻微缩放
- 数字颜色短暂变化

不要：

- 整张卡片跳动
- 页面闪烁
- 长动画
- 大幅移动

---

# 18. App 启动流程

打开 App：

```text
启动
 ↓
读取本地最近缓存
 ↓
立即显示
 ↓
请求后端最新行情
 ↓
更新页面
 ↓
进入后台刷新状态
```

即使网络很慢，用户也应该能够先看到最近一次行情。

---

# 19. 网络异常

如果无法连接后端：

```text
显示最近缓存
```

同时显示：

```text
最后更新：12:28
```

不要弹出连续错误对话框。

网络恢复：

```text
自动刷新
```

---

# 20. 后端异常

任何第三方异常都必须被后端捕获。

包括：

```text
429
403
502
503
timeout
connection reset
DNS error
数据为空
字段缺失
数据格式变化
```

后端不能因为单个数据源失败导致整个 API 返回 500。

例如：

```text
yfinance失败
↓
国际黄金 / 纳指 / 标普500标记 stale
↓
AKShare仍正常
↓
上海黄金正常返回
```

反之亦然。

---

# 21. 日志和监控

后端必须记录：

```text
请求时间
数据源
symbol
HTTP状态
耗时
成功/失败
429次数
重试次数
缓存命中次数
最后成功时间
```

建议统计：

```text
total_requests
successful_requests
failed_requests
rate_limit_count
cache_hits
cache_misses
average_latency
```

生产环境不能打印敏感信息。

---

# 22. 数据质量检查

每次采集后必须检查：

```text
price != null
price > 0
timestamp != null
```

对于涨跌幅：

```text
isfinite(change_percent)
```

禁止 NaN、Infinity 等值直接进入 API。

---

# 23. yfinance 采集器设计

建议封装为：

```text
services/
  market/
    yfinance_service.py
    akshare_service.py
    cache_service.py
    rate_limiter.py
    market_service.py
```

禁止在 FastAPI 路由中直接写：

```python
yf.Ticker(...)
```

路由只负责：

```text
接收请求
↓
调用 MarketService
↓
返回缓存数据
```

---

# 24. AKShare 采集器设计

建议：

```python
def fetch_sge_gold():
    df = ak.spot_quotations_sge(symbol="Au99.99")
    ...
```

必须将 AKShare DataFrame 转换为内部统一模型。

不能让 Flutter 直接理解 AKShare 的中文字段名。

内部统一：

```text
symbol
price
change
change_percent
timestamp
source
is_stale
```

---

# 25. 统一数据模型

后端内部统一使用：

```text
MarketQuote
```

至少包括：

```text
id
name
symbol
price
change
change_percent
currency
unit
source
timestamp
market_status
is_stale
```

这样以后更换数据源不会影响 Flutter。

---

# 26. 不允许的实现方式

禁止：

```text
Flutter → Yahoo Finance
```

禁止：

```text
Flutter → AKShare
```

禁止：

```text
App每1秒请求后端
```

禁止：

```text
后端每个用户请求都重新访问Yahoo
```

禁止：

```text
429后立即无限循环重试
```

禁止：

```text
使用旧缓存但标记为实时
```

禁止：

```text
将黄金期货价格直接命名为黄金现货
```

禁止：

```text
没有时间戳的数据直接显示为实时行情
```

---

# 27. 后端刷新建议

推荐后台任务：

```text
YFinance Collector
    ↓
每30~60秒
    ↓
更新缓存

AKShare SGE Collector
    ↓
每15~30秒
    ↓
更新缓存
```

实际间隔应根据：

- 市场开闭市
- 数据源响应
- 429 状态
- 网络状况

动态调整。

休市期间自动降低请求频率。

---

# 28. App 刷新建议

App 不直接控制第三方请求。

推荐：

```text
App打开
↓
GET /api/market/overview
↓
显示
↓
每30~60秒请求自己的后端
```

如果后端未来增加 WebSocket/SSE，可以改为：

```text
App
 ↓
WebSocket/SSE
 ↓
自己的后端
```

但第一版不需要为了“实时”强行增加 WebSocket。

---

# 29. 历史走势图

第二阶段再增加。

首页只显示涨跌幅。

点击行情卡片进入详情页：

```text
国际黄金
```

支持：

```text
1D
5D
1M
3M
1Y
```

第一阶段可以暂不实现 K 线。

如果实现走势图：

- 后端提供统一历史数据接口。
- Flutter 使用统一模型。
- 不允许 App 直接请求 Yahoo/SGE。
- 图表保持极简。
- 不添加大量指标。

---

# 30. 测试要求

## 30.1 数据源测试

必须测试：

```text
yfinance正常
yfinance超时
yfinance 429
yfinance返回空数据
Yahoo暂时不可用
AKShare正常
AKShare超时
AKShare返回空DataFrame
上海黄金休市
美股休市
```

## 30.2 App 测试

必须测试：

```text
首次安装
首次启动无缓存
有缓存但网络失败
网络恢复
快速打开/关闭
切换后台
重新进入前台
连续刷新
弱网
服务器异常
行情数据 stale
```

---

# 31. 429 测试

开发阶段必须能够模拟：

```text
429
```

验证：

```text
不会死循环
不会频繁请求
会指数退避
会进入冷却
缓存仍然可用
App仍能正常显示
恢复后可以重新采集
```

---

# 32. 安全要求

不要在 Flutter APK 中保存：

```text
Yahoo内部Cookie
Crumb
服务器管理密钥
数据库密码
第三方服务敏感凭据
```

所有服务端凭据只存在服务器环境变量。

---

# 33. 环境变量

建议：

```text
APP_ENV=production

CACHE_TTL=60

YF_MIN_INTERVAL=30
YF_MAX_RETRIES=3
YF_BACKOFF_BASE=5
YF_BACKOFF_MAX=120

SGE_REFRESH_INTERVAL=30

API_TIMEOUT=15
```

具体参数根据测试结果调整。

---

# 34. 项目目录建议

```text
project/
│
├── app/
│   ├── lib/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   ├── pages/
│   │   ├── widgets/
│   │   └── theme/
│   │
│   └── pubspec.yaml
│
├── server/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   │   └── market/
│   │   ├── models/
│   │   ├── cache/
│   │   ├── workers/
│   │   └── main.py
│   │
│   ├── requirements.txt
│   └── .env.example
│
├── tests/
│
├── README.md
└── AGENTS.md
```

实际项目已有目录结构时，不要为了符合此示例而大规模重构；优先保持现有架构。

---

# 35. 开发顺序

必须按照以下顺序开发：

### 第一步

检查项目当前结构。

确认：

```text
Flutter版本
Dart版本
Android配置
现有页面
现有网络层
现有依赖
```

不要未经分析直接重写项目。

### 第二步

建立后端：

```text
FastAPI
yfinance
AKShare
缓存
限速
错误处理
```

### 第三步

先实现：

```text
/api/market/overview
```

确认返回数据正确。

### 第四步

实现 Flutter 首页。

### 第五步

接入真实数据。

### 第六步

处理：

```text
429
timeout
缓存
stale
休市
```

### 第七步

优化 UI。

### 第八步

生成 Android Debug APK。

### 第九步

人工安装验证。

### 第十步

修复问题后再提交 Git。

---

# 36. Git 工作要求

每次开发完成后：

```text
git status
git diff
```

确认没有：

```text
.env
密钥
Cookie
缓存文件
日志
临时文件
构建产物
```

被错误提交。

提交信息使用清晰的英文或中文描述。

例如：

```text
feat: add market overview
fix: handle yfinance 429 rate limit
fix: add SGE gold quote cache
ui: simplify market cards
```

---

# 37. APK 验证要求

开发完成后必须执行：

```text
flutter analyze
flutter test
flutter build apk --debug
```

如果项目有 Android 原生代码，还必须执行对应 Gradle 构建验证。

生成：

```text
build/app/outputs/flutter-apk/app-debug.apk
```

然后等待人工安装验证。

没有人工确认之前，不要认为 UI 已经验收。

---

# 38. UI 验收标准

首页必须满足：

- 打开速度快
- 第一屏直接看到行情
- 不需要点击才能看到涨跌幅
- 数字层级明显
- 涨跌方向一眼可识别
- 不出现信息拥挤
- 不出现不必要的按钮
- 不出现大面积装饰
- 不出现频繁闪烁
- 行情更新不会导致整个页面跳动
- 网络失败时仍可查看最近数据
- stale 数据有明确提示

---

# 39. 数据准确性原则

本项目属于金融行情展示工具。

因此：

> “实时”必须有数据时间依据。

必须显示：

```text
数据源
更新时间
市场状态
```

如果数据源本身存在延迟，不得在 UI 中声称“毫秒级实时”。

App 文案建议：

```text
最新行情
```

而不是未经数据源授权和验证的：

```text
100%实时
零延迟
```

---

# 40. 数据源说明

设置页可以增加非常简洁的：

```text
数据来源

国际黄金 / 纳斯达克100 / 标普500
Yahoo Finance / yfinance

上海黄金
上海黄金交易所 / AKShare
```

必须避免让用户误解为本 App 是证券交易平台。

---

# 41. 后续扩展

第一阶段只实现：

```text
国际黄金
上海黄金 Au99.99
纳斯达克100
标普500
```

后续可增加：

```text
纳斯达克综合
道琼斯
白银
原油
美元指数
人民币汇率
```

但增加任何品种之前必须确认：

1. 数据源稳定性。
2. 数据源授权。
3. 更新频率。
4. API 限制。
5. 是否适合 App 对外展示。

---

# 42. 最终目标

最终 App 应该做到：

```text
打开 App
   ↓
立即看到最近缓存
   ↓
后台获取最新行情
   ↓
自动更新
   ↓
只突出涨跌幅
   ↓
极简视觉
   ↓
数据源异常不崩溃
   ↓
429不会导致服务雪崩
```

核心体验：

> **打开即看，一眼知道涨跌。**

---

# 43. 开发者特别注意

不要把“实时行情”理解成“App疯狂请求接口”。

正确架构是：

```text
数据源
  ↓
低频、受控采集
  ↓
缓存
  ↓
统一后端 API
  ↓
App
```

而不是：

```text
每个用户
  ↓
不停请求
  ↓
Yahoo / 上海黄金交易所
```

本项目的稳定性核心不是增加请求次数，而是：

```text
缓存优先
+
请求合并
+
请求间隔控制
+
指数退避
+
429冷却
+
数据源异常隔离
+
stale数据明确标识
```

---

# 44. 参考资料

yfinance：

```text
https://github.com/ranaroussi/yfinance
```

yfinance 429/限速处理参考文章：

```text
https://blog.csdn.net/gitblog_00291/article/details/151145655
```

AKShare 上海黄金交易所：

```text
https://akshare.akfamily.xyz/data/spot/spot.html
```

AKShare 官方 GitHub：

```text
https://github.com/akfamily/akshare
```

开发过程中应优先以第三方项目当前官方文档和当前安装版本实际 API 为准，不应机械复制旧文章中的代码。

---

# 45. “图片四”首页视觉规范

用户已提供参考图 `ss.jpg`，该图片作为本项目首页 UI 的主要视觉参考。

参考图的核心风格不是传统证券软件，而是：

> **现代、轻量、极简、卡片化、留白充足的移动金融 App。**

开发时应重点参考图片中的**整体布局、卡片比例、圆角、留白、信息层级和导航方式**，而不是机械复制其中的股票、公司和按钮内容。

## 45.1 整体视觉

参考图具有以下特征：

- 页面背景为非常浅的冷灰/暖灰白色。
- 内容区域以白色卡片为主。
- 卡片使用较大的圆角。
- 主要操作使用明亮蓝色。
- 上涨使用绿色。
- 下跌使用红色/粉红色。
- 深色行情卡片用于突出重要市场指标。
- 阴影非常轻，不使用厚重投影。
- 页面整体具有明显留白。
- 字体采用现代无衬线字体。
- 标题字重较高。
- 辅助信息使用较浅灰色。
- 数字使用较大的字号。
- 涨跌幅信息需要明显突出。

整体视觉应保持：

```text
浅色背景
   ↓
白色/深色圆角卡片
   ↓
大字号价格
   ↓
醒目涨跌幅
   ↓
少量蓝色强调
```

---

# 46. 本项目首页布局

本项目不复制参考图中的 Portfolio、Most Actives、Stocks Idea 等股票投资功能。

只保留参考图的**视觉语言**，将内容替换成黄金和指数行情。

建议首页：

```text
┌─────────────────────────────┐
│  9:41                 ⋯     │
│                             │
│  Market                     │
│  全球主要行情                │
│                             │
│  ┌───────────────────────┐  │
│  │  国际黄金              │  │
│  │                       │  │
│  │  $3,521.80            │  │
│  │                       │  │
│  │  +18.60    +0.53%     │  │
│  │                       │  │
│  │       ╭──╮            │  │
│  │   ╭───╯  ╰──╮         │  │
│  └───────────────────────┘  │
│                             │
│  主要指数                    │
│                             │
│  ┌──────────┐ ┌──────────┐ │
│  │ NASDAQ   │ │ S&P 500  │ │
│  │ 23,456.78│ │ 6,487.32 │ │
│  │ +0.54%   │ │ -0.19%   │ │
│  └──────────┘ └──────────┘ │
│                             │
│  中国黄金                    │
│                             │
│  ┌───────────────────────┐  │
│  │ 上海黄金 Au99.99       │  │
│  │                       │  │
│  │ ¥755.00 / 克           │  │
│  │ +2.30     +0.31%      │  │
│  └───────────────────────┘  │
│                             │
│  更新时间 12:30             │
└─────────────────────────────┘
```

具体布局可以根据屏幕尺寸自适应。

---

# 47. 首页信息层级

首页必须遵循：

### 第一层：当前价格

字号最大。

例如：

```text
$3,521.80
```

### 第二层：涨跌幅

涨跌幅必须比普通辅助信息更醒目：

```text
+0.53%
```

### 第三层：涨跌额

```text
+18.60
```

### 第四层：更新时间

```text
12:30:25
```

### 第五层：数据源/市场状态

仅在需要时显示。

---

# 48. 黄金主卡片

参考图中的深色行情卡片可用于本项目的核心黄金卡片。

建议：

```text
┌─────────────────────────┐
│ 国际黄金                 │
│ XAU/USD                 │
│                         │
│ $3,521.80               │
│                         │
│ +18.60   +0.53%         │
│                         │
│       ╭──╮              │
│   ╭───╯  ╰────╮         │
│ ╭─╯           ╰─        │
└─────────────────────────┘
```

核心卡片可以采用深色背景，以对应参考图中的 Dow Jones / S&P / NASD 深色卡片风格。

但不要使用过于鲜艳的渐变。

---

# 49. 指数卡片

纳斯达克100和标普500使用并排的小卡片。

推荐：

```text
┌────────────────┐ ┌────────────────┐
│ NASDAQ 100     │ │ S&P 500        │
│                │ │                │
│ 23,456.78      │ │ 6,487.32       │
│                │ │                │
│ +0.54%         │ │ -0.19%         │
│   ╱╲__╱╲       │ │ ╲__╱╲__        │
└────────────────┘ └────────────────┘
```

屏幕较小时自动改为上下排列。

禁止为了强行并排导致价格被压缩。

---

# 50. 国内黄金卡片

上海黄金交易所行情使用独立卡片：

```text
上海黄金
Au99.99

¥755.00 / 克

+2.30   +0.31%
```

必须明确：

```text
人民币
元/克
```

避免用户误解为美元/盎司。

---

# 51. 颜色规范

颜色集中定义在 Theme 中。

建议使用接近参考图的颜色体系：

```text
Primary Blue
用于：
- 当前选中状态
- 强调按钮
- 重要交互

Positive
用于上涨

Negative
用于下跌

Background
极浅灰白

Surface
白色

Text Primary
深蓝灰/近黑

Text Secondary
中灰

Divider
极浅灰
```

不要在页面代码中直接散落：

```text
Colors.blue
Colors.red
Colors.green
```

必须通过主题或语义颜色：

```text
AppColors.primary
AppColors.positive
AppColors.negative
AppColors.surface
AppColors.textPrimary
AppColors.textSecondary
```

---

# 52. 圆角规范

参考图的卡片圆角明显。

建议：

```text
大卡片：20~24dp
小卡片：16~20dp
按钮：12~16dp
标签：10~12dp
```

具体数值以实际 UI 验证结果调整。

不要同时出现大量不同圆角规格。

---

# 53. 间距规范

采用 8dp 基础间距体系：

```text
8
16
24
32
```

主要页面：

```text
左右边距：16~20dp

模块之间：20~28dp

标题与内容：8~12dp

卡片内部：16~20dp
```

不要让页面内容贴近屏幕边缘。

---

# 54. 字体规范

建议使用系统无衬线字体。

信息层级：

```text
页面标题：22~26sp / Bold

行情名称：16~18sp / SemiBold

当前价格：28~36sp / Bold

涨跌幅：15~18sp / SemiBold

涨跌额：13~15sp

辅助信息：11~13sp

更新时间：10~12sp
```

价格数字必须保持清晰，避免使用过度装饰字体。

---

# 55. 图表规范

参考图中的行情卡片包含非常简洁的迷你走势图。

本项目可采用：

```text
Sparkline
```

而不是完整 K 线。

首页只显示趋势，不显示：

- 坐标轴
- MACD
- RSI
- KDJ
- 成交量
- 大量刻度
- 网格

例如：

```text
      ╭──╮
  ╭───╯  ╰──╮
╭─╯          ╰─
```

图表只用于帮助用户快速判断趋势。

---

# 56. 行情数字动画

参考图整体是静态、轻量的，因此实时行情更新动画必须非常克制。

推荐：

```text
价格变化：
150~250ms

涨跌幅变化：
150~250ms
```

可以使用：

```text
AnimatedSwitcher
TweenAnimationBuilder
数字轻微淡入
```

禁止：

```text
整张卡片移动
页面重新布局
长时间闪烁
大幅缩放
```

---

# 57. 首页导航

参考图底部有：

```text
Home
Market
Portfolio
Notification
More
```

但本项目功能非常简单，不需要照搬五项导航。

推荐第一阶段：

```text
首页
```

或者：

```text
行情
设置
```

如果以后增加历史行情：

```text
行情
自选
设置
```

但没有实际功能的导航项目禁止为了“看起来像完整 App”而添加。

---

# 58. 首页顶部

参考图顶部采用：

```text
头像/图标
日期
时间
搜索
菜单
```

本项目建议简化为：

```text
行情

当前日期
市场状态
设置按钮
```

不需要：

- 用户头像
- 登录
- 搜索股票
- 买入按钮
- 卖出按钮

因为本项目不是交易 App。

---

# 59. 极简原则

任何准备添加到首页的 UI 元素，都必须先回答：

> 这个元素是否能帮助用户更快判断黄金、纳斯达克100、标普500和国内黄金的涨跌？

如果不能：

```text
不放首页。
```

---

# 60. 图片四与项目内容的对应关系

参考图片中的：

```text
Dow Jones
S&P
NASDAQ
```

替换为：

```text
国际黄金
NASDAQ 100
S&P 500
```

参考图片中的：

```text
Most Actives
```

替换为：

```text
主要行情
```

参考图片中的：

```text
Stocks Idea
```

不需要保留。

参考图片中的：

```text
Portfolio
```

不需要保留。

参考图片中的：

```text
BUY
```

不需要保留。

参考图片中的：

```text
News
Health
Technical
```

第一阶段不需要保留。

---

# 61. 首页最终视觉目标

最终视觉应该接近：

```text
              Market

        今日全球主要行情

      ┌──────────────────┐
      │  国际黄金         │
      │                  │
      │  $3,521.80       │
      │                  │
      │  +18.60  +0.53%  │
      │      ╭──╮        │
      │   ╭──╯  ╰──      │
      └──────────────────┘

      ┌────────┐ ┌────────┐
      │NASDAQ  │ │S&P 500 │
      │        │ │        │
      │23,456  │ │6,487   │
      │+0.54%  │ │-0.19%  │
      └────────┘ └────────┘

      ┌──────────────────┐
      │ 上海黄金 Au99.99  │
      │                  │
      │ ¥755.00 / 克     │
      │ +0.31%           │
      └──────────────────┘

            更新于 12:30
```

视觉关键词：

```text
Minimal
Clean
Soft
Modern
Financial
Rounded
Spacious
Fast
```

最终效果必须让用户：

> **打开 App → 不需要思考 → 3 秒内知道今天黄金和主要指数是涨还是跌。**

