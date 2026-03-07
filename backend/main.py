from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import market, trading, strategy, ws, backtest
from services import market_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await market_data.start_stream()
    yield
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
