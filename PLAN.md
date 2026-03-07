# 美股自动交易系统 - 实现方案

## 技术选型

- **后端**: Python 3.11+ / FastAPI / SQLite / alpaca-py
- **前端**: React + TypeScript / lightweight-charts (TradingView 开源图表库) / TailwindCSS
- **通信**: REST API + WebSocket (实时行情推送)
- **券商**: Alpaca (支持 Paper Trading 模拟盘)

## 项目结构

```
stock-trader/
├── backend/
│   ├── main.py                  # FastAPI 入口, 路由注册
│   ├── config.py                # 配置管理 (Alpaca keys, DB path)
│   ├── models.py                # SQLite 数据模型 (SQLAlchemy)
│   ├── database.py              # 数据库连接与初始化
│   ├── routers/
│   │   ├── market.py            # 行情 API (K线, 报价)
│   │   ├── trading.py           # 交易 API (下单, 撤单, 持仓)
│   │   ├── strategy.py          # 策略管理 API
│   │   └── ws.py                # WebSocket 端点 (实时行情推送)
│   ├── services/
│   │   ├── alpaca_client.py     # Alpaca API 封装
│   │   ├── market_data.py       # 行情数据服务
│   │   ├── trade_executor.py    # 交易执行器
│   │   └── strategy_engine.py   # 策略引擎 (加载/运行策略)
│   ├── strategies/
│   │   ├── base.py              # 策略抽象基类
│   │   ├── ma_crossover.py      # 均线交叉策略
│   │   ├── rsi_strategy.py      # RSI 策略
│   │   └── macd_strategy.py     # MACD 策略
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── Chart.tsx         # K线图 (lightweight-charts)
│   │   │   ├── TradePanel.tsx    # 交易面板 (下单/持仓)
│   │   │   ├── StrategyPanel.tsx # 策略选择与配置
│   │   │   ├── PositionTable.tsx # 持仓列表
│   │   │   └── SignalMarker.tsx  # 买卖信号标记
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts   # WebSocket 连接管理
│   │   │   └── useMarketData.ts  # 行情数据 hook
│   │   ├── services/
│   │   │   └── api.ts            # REST API 调用封装
│   │   └── types/
│   │       └── index.ts          # TypeScript 类型定义
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
└── README.md
```

## 核心设计

### 1. 策略接口 (Strategy Base Class)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class Signal:
    symbol: str
    signal_type: SignalType
    price: float
    quantity: int
    reason: str
    timestamp: datetime

class BaseStrategy(ABC):
    name: str = "base"
    description: str = ""

    def __init__(self, params: dict):
        self.params = params

    @abstractmethod
    def generate_signals(self, symbol: str, bars: list[dict]) -> list[Signal]:
        """输入 K 线数据, 输出交易信号"""
        pass

    @abstractmethod
    def default_params(self) -> dict:
        """返回策略默认参数"""
        pass
```

### 2. 数据模型 (SQLite)

```sql
-- 交易记录
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,          -- buy/sell
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    strategy TEXT,
    signal_reason TEXT,
    status TEXT DEFAULT 'pending',
    alpaca_order_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 策略配置
CREATE TABLE strategy_configs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    params TEXT NOT NULL,        -- JSON
    is_active BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- K线缓存
CREATE TABLE bars_cache (
    symbol TEXT,
    timeframe TEXT,
    timestamp TIMESTAMP,
    open REAL, high REAL, low REAL, close REAL,
    volume INTEGER,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
```

### 3. API 端点

```
REST API:
GET    /api/market/bars/{symbol}        # 获取 K 线数据 (?timeframe=1D&limit=200)
GET    /api/market/quote/{symbol}       # 获取实时报价
GET    /api/trading/positions           # 获取持仓
GET    /api/trading/orders              # 获取订单列表
POST   /api/trading/order               # 手动下单
DELETE /api/trading/order/{id}          # 撤单
GET    /api/trading/account             # 账户信息 (余额/盈亏)
GET    /api/strategy/list               # 可用策略列表
POST   /api/strategy/activate           # 激活策略 (symbol + strategy + params)
POST   /api/strategy/deactivate         # 停用策略
GET    /api/strategy/signals/{symbol}   # 获取策略信号历史

WebSocket:
WS     /ws/market/{symbol}              # 实时行情推送 (K线更新 + 报价)
WS     /ws/trades                       # 交易信号 & 订单状态推送
```

### 4. 数据流

```
Alpaca WebSocket ──→ Backend Market Service ──→ Strategy Engine
                                                    │
                                              generate_signals()
                                                    │
                                              Trade Executor ──→ Alpaca Order API
                                                    │
                                              WebSocket Push ──→ Frontend
                                                    │
                                    ┌───────────────┼───────────────┐
                                    │               │               │
                              Chart Update    Signal Marker    Position Update
```

### 5. 前端图表方案

使用 TradingView 的 `lightweight-charts` 库:
- 主图: K 线 + MA/EMA 叠加
- 副图: 成交量 / MACD / RSI (可切换)
- 买卖信号: 用 markers API 在 K 线上标记箭头
- 时间周期: 1m / 5m / 15m / 1h / 1D 切换
- 实时更新: WebSocket 推送最新 bar, 增量更新图表

### 6. 依赖

**Backend (requirements.txt):**
- fastapi / uvicorn
- alpaca-py (Alpaca 官方 SDK)
- sqlalchemy / aiosqlite
- pandas / numpy (指标计算)
- ta (技术分析指标库)
- websockets

**Frontend (package.json):**
- react / react-dom
- lightweight-charts (TradingView 图表)
- tailwindcss
- axios

## 实现阶段

### Phase 1: 基础框架 + K 线图
- 搭建 FastAPI 项目骨架
- 接入 Alpaca 行情 API, 获取历史 K 线
- 搭建 React 项目, 集成 lightweight-charts
- 实现基础 K 线图展示 + 时间周期切换

### Phase 2: 策略引擎
- 实现策略基类和策略引擎
- 实现 3 个内置策略 (MA交叉 / RSI / MACD)
- 策略管理 API + 前端策略配置面板
- 买卖信号在图表上标记

### Phase 3: 交易执行
- 接入 Alpaca 交易 API (Paper Trading)
- 实现交易执行器
- 持仓/订单管理
- 账户盈亏展示

### Phase 4: 实时推送
- Alpaca WebSocket 实时行情接入
- 后端 → 前端 WebSocket 推送
- 图表实时更新
- 交易信号实时通知
