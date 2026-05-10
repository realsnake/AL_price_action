# Stock Trading System

自动化美股交易系统，支持实时 K 线图、可插拔策略框架、Paper Trading 模拟交易。

## 技术栈

- **后端**: Python 3.11+ / FastAPI / SQLite / Alpaca API
- **前端**: React + TypeScript / Vite / TailwindCSS / lightweight-charts
- **券商**: Alpaca (Paper Trading 模拟盘)

## 功能特性

- ✅ TradingView 风格 K 线图 (支持 1m/5m/15m/1h/1D 多时间周期)
- ✅ 可插拔策略框架 (内置 MA 交叉、RSI、MACD 策略)
- ✅ 买卖信号可视化标记
- ✅ 实时账户/持仓/盈亏展示
- ✅ Paper Trading 模拟交易
- ✅ 手动下单功能
- 🚧 WebSocket 实时行情推送 (Phase 4)

## 快速开始

### 1. 获取 Alpaca API Key

访问 [Alpaca](https://alpaca.markets/) 注册账号，获取 Paper Trading API Key。

### 2. 配置后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env 文件，填入你的 Alpaca API Key
```

`.env` 文件示例：
```
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
PAPER_TRADING=true
```

如需切到 IBKR 做小额真实交易实验，保持 Alpaca 行情配置不变，并额外显式开启交易券商与风控开关：

```bash
BROKER=ibkr
IBKR_HOST=127.0.0.1
IBKR_PORT=7496
IBKR_CLIENT_ID=17
IBKR_ACCOUNT=U1234567
IBKR_LIVE_TRADING_ENABLED=true
IBKR_ORDER_TRANSMIT=true
IBKR_ALLOWED_SYMBOLS=QQQ
IBKR_MAX_ORDER_USD=750
IBKR_DAILY_MAX_NOTIONAL_USD=1500
```

IBKR 路径只允许手动 `limit` 单，并要求前端勾选 live confirmation。Brooks 自动 runner 仍限制在 `BROKER=alpaca` 的纸盘路径。详细步骤见 `docs/ibkr-live-trading.md`。

### 3. 启动后端

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

后端运行在 http://localhost:8000

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 http://localhost:5173

## 项目结构

```
stock-trader/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型
│   ├── database.py          # 数据库
│   ├── routers/             # API 路由
│   │   ├── market.py        # 行情 API
│   │   ├── trading.py       # 交易 API
│   │   ├── strategy.py      # 策略 API
│   │   └── ws.py            # WebSocket
│   ├── services/
│   │   ├── alpaca_client.py # Alpaca 封装
│   │   └── strategy_engine.py # 策略引擎
│   └── strategies/          # 策略实现
│       ├── base.py          # 策略基类
│       ├── ma_crossover.py  # 均线交叉
│       ├── rsi_strategy.py  # RSI 策略
│       └── macd_strategy.py # MACD 策略
└── frontend/
    └── src/
        ├── components/      # React 组件
        │   ├── Chart.tsx    # K 线图
        │   ├── TradePanel.tsx
        │   └── StrategyPanel.tsx
        ├── services/api.ts  # API 调用
        └── types/index.ts   # TypeScript 类型
```

## API 文档

启动后端后访问 http://localhost:8000/docs 查看 Swagger API 文档。

### 主要端点

- `GET /api/market/bars/{symbol}` - 获取 K 线数据
- `GET /api/market/quote/{symbol}` - 获取实时报价
- `GET /api/trading/account` - 账户信息
- `GET /api/trading/positions` - 持仓列表
- `POST /api/trading/order` - 下单
- `GET /api/strategy/list` - 可用策略列表
- `POST /api/strategy/signals` - 运行策略获取信号

## 添加自定义策略

1. 在 `backend/strategies/` 创建新文件，例如 `my_strategy.py`
2. 继承 `BaseStrategy` 并实现 `generate_signals()` 方法
3. 使用 `@register_strategy` 装饰器注册

示例：

```python
from strategies.base import BaseStrategy, Signal, SignalType
from services.strategy_engine import register_strategy
from datetime import datetime

@register_strategy
class MyStrategy(BaseStrategy):
    name = "my_strategy"
    description = "My custom strategy"

    def default_params(self) -> dict:
        return {"threshold": 0.02, "quantity": 1}

    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        signals = []
        # 实现你的策略逻辑
        return signals
```

## 实现阶段

- ✅ **Phase 1**: 基础框架 + K 线图
- ✅ **Phase 2**: 策略引擎
- ✅ **Phase 3**: 交易执行
- 🚧 **Phase 4**: 实时推送 (WebSocket)

## 注意事项

- 默认使用 Alpaca Paper Trading (模拟盘)，不会真实交易
- 历史数据有限制，免费账户可能有 API 调用频率限制
- 策略仅供学习参考，实盘交易需谨慎

## License

MIT
