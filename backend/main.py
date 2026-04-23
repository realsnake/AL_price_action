from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import market, trading, strategy, ws, backtest, paper_strategy
from services.alpaca_client import alpaca_client
from services import market_data, trade_updates


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await market_data.start_stream()
    await trade_updates.start_trade_updates_stream()
    yield
    await trade_updates.stop_trade_updates_stream()
    await market_data.stop_stream()


app = FastAPI(title="Stock Trader", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(trading.router)
app.include_router(strategy.router)
app.include_router(ws.router)
app.include_router(backtest.router)
app.include_router(paper_strategy.router)


@app.get("/api/health")
def health():
    alpaca_configured = alpaca_client.is_configured()
    return {
        "status": "ok" if alpaca_configured else "degraded",
        "alpaca_configured": alpaca_configured,
        "live_stream_enabled": market_data.is_live_stream_enabled(),
    }
