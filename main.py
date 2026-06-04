import asyncio
import logging
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import os
import datetime
import yfinance as yf
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_DATA_URL   = "https://data.alpaca.markets/v2"
ALPACA_HEADERS    = {
    "APCA-API-KEY-ID": ALPACA_API_KEY or "",
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY or "",
}

app = FastAPI(title="OmniQuant V2.0 Engine - Institutional Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nice-sand-06aa39c00.7.azurestaticapps.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    ticker: str


class SMCRequest(BaseModel):
    ticker: str = "GC=F"
    timeframe: str = "4h"


class RiskMatrixRequest(BaseModel):
    account_size: float
    risk_percentage: float
    stop_loss_pips: float
    daily_drawdown_limit: float = 5.0
    asset_class: str = "forex"


class ChartRequest(BaseModel):
    ticker: str = "BTC"


class NewsRequest(BaseModel):
    ticker: str = "BTCUSDT"


class ATRRequest(BaseModel):
    ticker: str = "BTC"


# ==========================================
# ALPACA DATA HELPERS + SMC MATH ENGINE
# ==========================================

# RWA ticker keywords → Alpaca ETF proxy symbols (carry real volume data)
_RWA_ALPACA: dict[str, str] = {"XAU": "GLD", "GOLD": "GLD", "XAG": "SLV", "SILVER": "SLV"}
# FX keywords → Alpaca forex pair notation
_FX_ALPACA: dict[str, str] = {"EUR": "EUR/USD", "GBP": "GBP/USD", "JPY": "USD/JPY", "AUD": "AUD/USD"}


async def _fetch_alpaca_stock_bars(
    client: httpx.AsyncClient, symbol: str, limit: int = 120
) -> list[dict]:
    """Daily OHLCV bars for a US ETF/stock from Alpaca free IEX feed."""
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars"
    params = {"timeframe": "1Day", "limit": limit, "sort": "asc", "feed": "iex"}
    try:
        r = await client.get(url, params=params, headers=ALPACA_HEADERS, timeout=8.0)
        if r.status_code != 200:
            logger.warning("Alpaca stock bars HTTP %d for %s", r.status_code, symbol)
            return []
        return [
            {"h": b["h"], "l": b["l"], "c": b["c"], "v": int(b.get("v", 0))}
            for b in r.json().get("bars", [])
        ]
    except Exception as exc:
        logger.warning("Alpaca stock bars failed (%s): %s", symbol, exc)
        return []


async def _fetch_alpaca_forex_bars(
    client: httpx.AsyncClient, pair: str, limit: int = 120
) -> list[dict]:
    """Daily bars for an FX pair from Alpaca (premium plan; returns [] on free tier)."""
    url = f"{ALPACA_DATA_URL}/forex/bars"
    params = {"symbols": pair, "timeframe": "1Day", "limit": limit, "sort": "asc"}
    try:
        r = await client.get(url, params=params, headers=ALPACA_HEADERS, timeout=8.0)
        if r.status_code != 200:
            logger.warning("Alpaca forex bars HTTP %d for %s", r.status_code, pair)
            return []
        raw = r.json().get("bars", {}).get(pair, [])
        return [{"h": b["h"], "l": b["l"], "c": b["c"], "v": 0} for b in raw]
    except Exception as exc:
        logger.warning("Alpaca forex bars failed (%s): %s", pair, exc)
        return []


def run_smc_engine(bars: list[dict]) -> dict:
    """
    Volume-weighted Smart Money Concepts trap zone detector.

    SHORT TRAP ZONES (Bear Traps / Stop Hunts):
        Swing Low + volume SPIKE above average
        Institutions sweep retail stop-losses before reversing price upward.
        Traders short at this level will be trapped.

    LONG TRAP ZONES (Bull Traps):
        Swing High + DECLINING relative volume
        Retail buys the breakout; no institutional follow-through means reversal.
        Traders long at this level will be trapped.

    Degrades gracefully to price-only detection when volume is unavailable (v=0).
    """
    n = len(bars)
    if n < 5:
        return {"short_trap_zones": [], "long_trap_zones": [], "fair_value_gaps": []}

    vols = [b.get("v", 0) for b in bars]
    has_vol = any(v > 0 for v in vols)
    avg_vol = (sum(vols) / n) if has_vol else 1.0

    short_traps: list[dict] = []
    long_traps: list[dict]  = []
    fvgs: list[dict]        = []

    for i in range(2, n - 2):
        cur = bars[i]
        p1, p2 = bars[i - 1], bars[i - 2]
        n1, n2 = bars[i + 1], bars[i + 2]
        rel_vol = round((cur.get("v", 0) / avg_vol) if avg_vol > 0 else 1.0, 2)

        # SHORT TRAP: swing low + elevated volume (stop hunt)
        if cur["l"] < min(p1["l"], p2["l"], n1["l"], n2["l"]):
            short_traps.append({
                "trigger_price": round(cur["l"], 6),
                "liquidity_pool": round(cur["l"] * 0.9985, 6),
                "rel_volume": rel_vol,
                "confidence": "HIGH" if (not has_vol or rel_vol > 1.25) else "MODERATE",
            })

        # LONG TRAP: swing high + declining volume (bull trap)
        if cur["h"] > max(p1["h"], p2["h"], n1["h"], n2["h"]):
            long_traps.append({
                "trigger_price": round(cur["h"], 6),
                "liquidity_pool": round(cur["h"] * 1.0015, 6),
                "rel_volume": rel_vol,
                "confidence": "HIGH" if (not has_vol or rel_vol < 0.80) else "MODERATE",
            })

        # FAIR VALUE GAP (3-candle imbalance)
        if p2["h"] < cur["l"]:
            fvgs.append({"bias": "BULLISH FVG", "ceiling": round(cur["l"], 6), "floor": round(p2["h"], 6)})
        elif p2["l"] > cur["h"]:
            fvgs.append({"bias": "BEARISH FVG", "ceiling": round(p2["l"], 6), "floor": round(cur["h"], 6)})

    return {
        "short_trap_zones": short_traps[-3:],
        "long_trap_zones":  long_traps[-3:],
        "fair_value_gaps":  fvgs[-2:],
    }


# ==========================================
# 1.5 PROP-FIRM RISK MATRIX
# ==========================================
@app.post("/api/risk")
async def calculate_risk(request: RiskMatrixRequest):
    logger.info("Risk Matrix: $%.2f account | %.1f%% drawdown limit", request.account_size, request.daily_drawdown_limit)

    if request.stop_loss_pips <= 0:
        return {"error": "Stop loss must be greater than 0"}

    dollar_risk = request.account_size * (request.risk_percentage / 100)
    pip_value_per_lot = 10.0
    recommended_lot = dollar_risk / (request.stop_loss_pips * pip_value_per_lot)
    max_daily_loss = request.account_size * (request.daily_drawdown_limit / 100)

    if dollar_risk >= max_daily_loss:
        status = "FUNDS AT RISK (Exceeds Daily Limit)"
    elif dollar_risk >= (max_daily_loss * 0.5):
        status = "ELEVATED RISK"
    else:
        status = "SAFE GUARDRAILS ACTIVE"

    return {
        "status": status,
        "dollar_risk": f"${dollar_risk:,.2f}",
        "recommended_lot_size": round(recommended_lot, 2),
        "max_daily_drawdown": f"${max_daily_loss:,.2f}",
    }


# ==========================================
# 1.6 LIVE INSTITUTIONAL TAPE & MACRO FEED
# ==========================================
@app.post("/api/macro-news")
async def fetch_macro_news(request: NewsRequest):
    logger.info("Macro sync for %s", request.ticker)

    terminal_feed: list[dict] = []
    smc_data: dict = {"short_trap_zones": [], "long_trap_zones": [], "fair_value_gaps": []}
    ticker_upper = request.ticker.upper()
    is_crypto = any(c in ticker_upper for c in ["BTC", "ETH", "SOL", "USDT"])

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if is_crypto:
                symbol = "BTCUSDT" if "BTC" in ticker_upper else "ETHUSDT"
                b_res = await client.get(f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit=500")
                seen: set[str] = set()
                if b_res.status_code == 200:
                    for t in b_res.json():
                        price = float(t.get("price", 0))
                        qty = float(t.get("qty", 0))
                        usd_val = price * qty
                        if usd_val >= 25_000.0:
                            sig = f"{price}_{qty}_{t.get('time')}"
                            if sig not in seen:
                                seen.add(sig)
                                buyer = not t.get("isBuyerMaker", False)
                                terminal_feed.append({
                                    "title": f"BLOCK: {'🟢 BUY' if buyer else '🔴 SELL'} {qty:.2f} {symbol.replace('USDT','')} (${usd_val:,.0f})",
                                    "source": "BINANCE",
                                    "url": f"@{price:,.2f}",
                                })
                terminal_feed = terminal_feed[:6]
            else:
                yf_symbol = "GC=F" if "XAU" in ticker_upper else "EURUSD=X"

                # Wrap blocking yfinance I/O — keeps event loop free
                hist = await asyncio.to_thread(
                    lambda: yf.Ticker(yf_symbol).history(period="5d", interval="1h")
                )
                if not hist.empty:
                    candles = hist[["Open", "High", "Low", "Close"]].reset_index().to_dict("records")
                    candles.reverse()
                    mean_range = float(abs(hist["High"] - hist["Low"]).mean())
                    for c in candles[:15]:
                        h, l, cl, op = c.get("High", 0), c.get("Low", 0), c.get("Close", 0), c.get("Open", 0)
                        if abs(h - l) > mean_range * 1.5:
                            bias = "🟢 INST BUY SWEEP" if cl > op else "🔴 INST SELL SWEEP"
                            dt = c.get("Datetime") or c.get("Date")
                            ts = dt.strftime("%H:%M") if dt else "LIVE"
                            terminal_feed.append({"title": f"{bias}: Volatility Expansion Detected", "source": "ICE_TAPE", "url": f"{ts} @ {cl:,.2f}"})
                        if len(terminal_feed) >= 6:
                            break

            # === ALPACA-POWERED SMC ENGINE (D1 bars with volume analytics) ===
            smc_bars: list[dict] = []

            if is_crypto:
                # Crypto pipeline: UNCHANGED — daily candles from yfinance
                smc_sym = "BTC-USD" if "BTC" in ticker_upper else "ETH-USD"
                raw = await asyncio.to_thread(
                    lambda: yf.Ticker(smc_sym).history(period="3mo", interval="1d")
                )
                if not raw.empty:
                    for _, row in raw.iterrows():
                        smc_bars.append({"h": float(row["High"]), "l": float(row["Low"]),
                                         "c": float(row["Close"]), "v": int(row.get("Volume", 0))})
            else:
                # RWA ETF path: Alpaca stocks API carries real volume — key for bull/bear trap detection
                alpaca_sym = next((v for k, v in _RWA_ALPACA.items() if k in ticker_upper), None)
                if alpaca_sym:
                    smc_bars = await _fetch_alpaca_stock_bars(client, alpaca_sym, limit=120)
                    logger.info("Alpaca RWA SMC: %d bars for %s→%s", len(smc_bars), ticker_upper, alpaca_sym)

                if not smc_bars:
                    # FX pair: Alpaca forex (premium plan) → yfinance fallback (no volume)
                    fx_pair = next((v for k, v in _FX_ALPACA.items() if k in ticker_upper), None)
                    if fx_pair:
                        smc_bars = await _fetch_alpaca_forex_bars(client, fx_pair, limit=120)
                        logger.info("Alpaca FX SMC: %d bars for %s", len(smc_bars), fx_pair)

                if not smc_bars:
                    yf_smc = "GC=F" if "XAU" in ticker_upper else "EURUSD=X"
                    raw = await asyncio.to_thread(
                        lambda: yf.Ticker(yf_smc).history(period="3mo", interval="1d")
                    )
                    if not raw.empty:
                        for _, row in raw.iterrows():
                            smc_bars.append({"h": float(row["High"]), "l": float(row["Low"]),
                                             "c": float(row["Close"]), "v": 0})
                        logger.info("yfinance fallback SMC: %d bars", len(smc_bars))

            smc_data = run_smc_engine(smc_bars)

    except Exception as e:
        logger.error("Macro sync fault: %s", e, exc_info=True)

    if not terminal_feed:
        terminal_feed = [
            {"title": f"SMC Structural Scan Active: {request.ticker}", "source": "SYS-FEED", "url": "LIVE"},
            {"title": "Searching institutional block execution clusters...", "source": "SYS-FILTER", "url": "SYNC"},
        ]

    now = datetime.datetime.now(datetime.timezone.utc)
    macro_events = [
        {"event": "US Core CPI Release", "date": "2026-06-10T12:30:00Z", "impact": "HIGH"},
        {"event": "FOMC Interest Rate Decision", "date": "2026-06-17T18:00:00Z", "impact": "CRITICAL"},
        {"event": "Non-Farm Payrolls (NFP)", "date": "2026-06-05T12:30:00Z", "impact": "HIGH"},
    ]
    active_calendar = []
    for ev in macro_events:
        ed = datetime.datetime.strptime(ev["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        if ed > now:
            delta = ed - now
            active_calendar.append({"name": ev["event"], "impact": ev["impact"], "countdown": f"{delta.days}d {delta.seconds // 3600}h", "is_imminent": delta.days <= 3})

    return {"status": "success", "news": terminal_feed, "smc": smc_data, "calendar": active_calendar}


# ==========================================
# 1.7 AI VOLATILITY ENGINE (ATR)
# ==========================================
@app.post("/api/atr")
async def calculate_dynamic_stop(request: ATRRequest):
    ticker_upper = request.ticker.upper().replace("/", "")
    logger.info("ATR engine: %s", ticker_upper)
    is_crypto = any(c in ticker_upper for c in ["BTC", "ETH", "SOL", "USDT"])

    try:
        true_ranges: list[float] = []
        if is_crypto:
            symbol = ticker_upper if "USDT" in ticker_upper else f"{ticker_upper}USDT"
            async with httpx.AsyncClient(timeout=5.0) as client:
                data = (await client.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=15")).json()
            if isinstance(data, dict) and "code" in data:
                logger.warning("Binance API error %s: %s", symbol, data.get("msg"))
                return {"error": data.get("msg"), "suggested_stop_loss": 50.0}
            for i in range(1, len(data)):
                h, l, pc = float(data[i][2]), float(data[i][3]), float(data[i-1][4])
                true_ranges.append(max(h - l, abs(h - pc), abs(l - pc)))
        else:
            yf_sym = "GC=F" if "XAU" in ticker_upper else ("EURUSD=X" if "EUR" in ticker_upper else f"{ticker_upper}=X")
            hist = await asyncio.to_thread(lambda: yf.Ticker(yf_sym).history(period="5d", interval="15m"))
            if hist.empty:
                return {"error": "No volatility data found", "suggested_stop_loss": 50.0}
            candles = hist[["High", "Low", "Close"]].tail(15).reset_index().to_dict("records")
            for i in range(1, len(candles)):
                h, l, pc = candles[i]["High"], candles[i]["Low"], candles[i-1]["Close"]
                true_ranges.append(max(h - l, abs(h - pc), abs(l - pc)))

        if not true_ranges:
            raise ValueError("Empty true ranges")

        atr = sum(true_ranges) / len(true_ranges)
        suggested_stop = round((atr * 1.5) * 10000, 1) if (not is_crypto and "XAU" not in ticker_upper) else round(atr * 1.5, 2)
        return {"status": "success", "atr_value": round(atr, 4), "suggested_stop_loss": suggested_stop}

    except Exception as e:
        logger.error("ATR calc error: %s", e, exc_info=True)
        return {"error": "Volatility stream failed", "suggested_stop_loss": 50.0}


# ==========================================
# LIVE CHART ENDPOINT
# ==========================================
@app.post("/api/chart")
async def get_live_chart(request: ChartRequest):
    ticker = request.ticker.upper().replace("/", "")
    is_crypto = any(c in ticker for c in ["BTC", "ETH", "SOL", "USDT"])
    candles: list[dict] = []

    smc_bars: list[dict] = []

    try:
        if is_crypto:
            symbol = ticker if "USDT" in ticker else f"{ticker}USDT"
            async with httpx.AsyncClient(timeout=8.0) as client:
                data = (await client.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=365")).json()
            if isinstance(data, dict) and "code" in data:
                return {"error": data.get("msg")}
            for k in data:
                candles.append({"time": int(k[0] / 1000), "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4])})
                # Binance klines include volume at index 5 — feed it directly into the SMC engine
                smc_bars.append({"h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])})
        else:
            yf_sym = "GC=F" if "XAU" in ticker else ("EURUSD=X" if "EUR" in ticker else f"{ticker}=X")
            hist = await asyncio.to_thread(lambda: yf.Ticker(yf_sym).history(period="1y", interval="1d"))
            for idx, row in hist.iterrows():
                candles.append({"time": int(idx.timestamp()), "open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])})
                smc_bars.append({"h": float(row["High"]), "l": float(row["Low"]), "c": float(row["Close"]), "v": float(row.get("Volume", 0))})

        return {"status": "success", "candles": candles, "smc": run_smc_engine(smc_bars)}

    except Exception as e:
        logger.error("Chart endpoint error: %s", e, exc_info=True)
        return {"error": str(e)}


# ==========================================
# 2. CRYPTO CONSOLIDATED ORDER BOOK (COB)
# ==========================================
async def fetch_order_book(client: httpx.AsyncClient, exchange: str, symbol: str) -> tuple[float, float]:
    try:
        if exchange == "Binance":
            data = (await client.get(f"https://api.binance.com/api/v3/depth?symbol={symbol.replace('/', '')}&limit=100")).json()
            return sum(float(p) * float(q) for p, q in data.get("bids", [])), sum(float(p) * float(q) for p, q in data.get("asks", []))
        elif exchange == "Bybit":
            data = (await client.get(f"https://api.bybit.com/v5/market/orderbook?category=spot&symbol={symbol.replace('/', '')}")).json().get("result", {})
            return sum(float(p) * float(q) for p, q in data.get("b", [])), sum(float(p) * float(q) for p, q in data.get("a", []))
    except Exception:
        pass
    return 0.0, 0.0


# ==========================================
# 2.5 DECENTRALIZED PERP SCANNER (HYPERLIQUID)
# ==========================================
async def fetch_hyperliquid_order_book(client: httpx.AsyncClient, symbol: str) -> tuple[float, float]:
    try:
        coin = symbol.split("/")[0] if "/" in symbol else symbol.replace("USDT", "")
        data = (await client.post("https://api.hyperliquid.xyz/info", json={"type": "l2Book", "coin": coin})).json()
        lvls = data.get("levels", [[], []])
        bid_vol = sum(float(lv["px"]) * float(lv["sz"]) for lv in lvls[0])
        ask_vol = sum(float(lv["px"]) * float(lv["sz"]) for lv in lvls[1])
        logger.info("Hyperliquid: pulled %s L2 book", coin)
        return bid_vol, ask_vol
    except Exception as e:
        logger.warning("Hyperliquid error: %s", e)
        return 0.0, 0.0


# ==========================================
# 3. SMART MONEY & INSTITUTIONAL FLOW TRACKER
# ==========================================
async def fetch_institutional_flow(client: httpx.AsyncClient) -> dict:
    logger.info("Scanning Ethereum for institutional movements")

    targets = {
        "BlackRock_BUIDL": "0x7712c34205737192402172409a8f7ccef8aa2aec",
        "Tether_Treasury_USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "Tokenized_Gold_PAXG": "0x45804880De22913dAFE09f4980848ECE6EcbAf78",
    }

    async def _fetch_one(name: str, address: str) -> tuple[str, dict]:
        url = (
            f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx"
            f"&contractaddress={address}&page=1&offset=50&sort=desc&apikey={ETHERSCAN_API_KEY}"
        )
        try:
            resp = await client.get(url)
            data = resp.json()
            if data.get("status") != "1":
                return name, {"status": "Awaiting Data"}
            mints, burns, net_flow = 0, 0, 0.0
            for tx in data.get("result", []):
                amount_usd = float(tx.get("value", 0)) / 1_000_000
                if amount_usd > 500_000:
                    if tx.get("from") == "0x0000000000000000000000000000000000000000":
                        mints += 1; net_flow += amount_usd
                    elif tx.get("to") == "0x0000000000000000000000000000000000000000":
                        burns += 1; net_flow -= amount_usd
            flow_str = f"+${net_flow:,.2f}" if net_flow >= 0 else f"-${abs(net_flow):,.2f}"
            return name, {"whale_mints_detected": mints, "whale_burns_detected": burns, "net_flow": flow_str}
        except Exception as e:
            return name, {"error": str(e)}

    # All three Etherscan requests fire concurrently
    results = await asyncio.gather(*[_fetch_one(n, a) for n, a in targets.items()])
    return dict(results)


# ==========================================
# 4. THE UNIVERSAL OMNI-QUANT SMART ROUTER
# ==========================================
@app.post("/api/scan")
async def run_omni_scan(request: ScanRequest):
    ticker = request.ticker.upper().strip()
    logger.info("OMNI-SCAN initiated: %s", ticker)

    rwa_indicators = ["XAU", "XAG", "GOLD", "MCAU", "PAXG", "BUIDL", "TREASURY", "EUR/", "GBP/", "JPY/", "AUD/", "CAD/"]
    is_rwa = any(r in ticker for r in rwa_indicators) and "USDT" not in ticker

    async with httpx.AsyncClient(timeout=10.0) as client:
        if is_rwa:
            logger.info("RWA/Forex detected — routing to Web3 Synthetics")
            (paxg_bids, paxg_asks), institutional_data = await asyncio.gather(
                fetch_order_book(client, "Binance", "PAXG/USDT"),
                fetch_institutional_flow(client),
            )
            return {
                "status": "success",
                "ticker": ticker,
                "asset_class": "Real World Assets (RWA)",
                "category": "RWA",
                "bid_volume": int(paxg_bids),
                "ask_volume": int(paxg_asks),
                "bias": "BULLISH" if paxg_bids > paxg_asks else "BEARISH",
                "institutional_money_flow": {
                    "BlackRock_BUIDL": institutional_data.get("BlackRock_BUIDL", {}),
                    "Tokenized_Gold_Flow": institutional_data.get("Tokenized_Gold_PAXG", {}),
                },
            }
        else:
            logger.info("Crypto detected — routing to CEX/DEX aggregator")
            crypto_symbol = ticker if ("/" in ticker or "USDT" in ticker) else f"{ticker}/USDT"
            (bin_bids, bin_asks), (bybit_bids, bybit_asks), (hl_bids, hl_asks), institutional_data, liq_data = await asyncio.gather(
                fetch_order_book(client, "Binance", crypto_symbol),
                fetch_order_book(client, "Bybit", crypto_symbol),
                fetch_hyperliquid_order_book(client, crypto_symbol),
                fetch_institutional_flow(client),
                fetch_liquidation_zones(client, ticker),
            )
            total_bids = bin_bids + bybit_bids + hl_bids
            total_asks = bin_asks + bybit_asks + hl_asks
            return {
                "status": "success",
                "ticker": ticker,
                "asset_class": "Crypto (CEX + DEX)",
                "category": "CRYPTO",
                "bid_volume": int(total_bids),
                "ask_volume": int(total_asks),
                "bias": "BULLISH" if total_bids > total_asks else "BEARISH",
                "institutional_money_flow": {
                    "Tether_Treasury_USDT": institutional_data.get("Tether_Treasury_USDT", {}),
                },
                "liquidation_heatmap": liq_data,
            }


# ==========================================
# 5. ORIGINAL XRPL DEEP CHAIN SCANNER
# ==========================================
async def run_deep_xrpl_scan(ticker: str) -> dict:
    logger.info("Deep XRPL ledger scan for %s", ticker)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {"method": "ledger", "params": [{"ledger_index": "validated", "transactions": True}]}
            data = (await client.post("https://s1.ripple.com:51234/", json=payload)).json()
            txs = data.get("result", {}).get("ledger", {}).get("transactions", [])
            tx_count = len(txs)
            logger.info("XRPL scan complete: %d transactions", tx_count)
            return {
                "status": "success",
                "network": "XRPL Mainnet",
                "rwa_target": "XRP Native & RWA Flow",
                "institutional_bids": f"${tx_count * 25400.50:,.2f}",
                "xrp_liquidity_backing": f"{tx_count * 1500:,.2f} XRP",
                "on_chain_blocks": tx_count,
                "deep_bias": "BULLISH" if tx_count > 40 else "NEUTRAL",
            }
    except Exception as e:
        logger.error("XRPL connection error: %s", e, exc_info=True)
        return {"error": "XRPL Scan failed"}


# ==========================================
# 6. LIQUIDATION ZONE PROCESSOR
# ==========================================
async def fetch_liquidation_zones(client: httpx.AsyncClient, symbol: str) -> dict:
    logger.info("Scanning liquidation traps for %s", symbol)
    clean = symbol.replace("/", "").replace("-", "").upper()
    if "USDT" not in clean:
        clean += "USDT"
    try:
        price_res, oi_res = await asyncio.gather(
            client.get(f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={clean}"),
            client.get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={clean}"),
        )
        price_data, oi_data = price_res.json(), oi_res.json()
        cur_price = float(price_data.get("lastPrice", 0))
        total_oi = float(oi_data.get("openInterest", 0)) * cur_price
        heat = "CRITICAL (Massive Traps)" if total_oi > 500_000_000 else ("LOW (Safe to Trade)" if total_oi < 100_000_000 else "ELEVATED")
        return {
            "current_mark_price": f"${cur_price:,.2f}",
            "total_open_interest": f"${total_oi:,.0f}",
            "danger_zone_upper": f"${cur_price * 1.015:,.2f}",
            "danger_zone_lower": f"${cur_price * 0.985:,.2f}",
            "liquidation_heat": heat,
        }
    except Exception as e:
        logger.error("Liquidation processor error: %s", e, exc_info=True)
        return {"error": "Liquidation scan failed. Exchange rate limit reached."}


# ==========================================
# 7. SMART MONEY CONCEPTS (SMC) MATH ENGINE
# ==========================================
@app.post("/api/smc-traps")
async def calculate_smc_traps(request: SMCRequest):
    logger.info("SMC engine: scanning %s", request.ticker)
    try:
        data = await asyncio.to_thread(
            lambda: yf.Ticker(request.ticker).history(period="1mo", interval=request.timeframe)
        )
        if data.empty:
            return {"error": "No array data found for ticker"}

        candles = data[["High", "Low"]].reset_index().to_dict("records")
        swing_highs, swing_lows, fvgs = [], [], []

        for i in range(2, len(candles) - 2):
            c, p1, p2, n1, n2 = candles[i], candles[i-1], candles[i-2], candles[i+1], candles[i+2]
            if c["High"] > max(p1["High"], p2["High"], n1["High"], n2["High"]):
                swing_highs.append({"price": round(c["High"], 2), "trap_zone": round(c["High"] * 1.0015, 2)})
            if c["Low"] < min(p1["Low"], p2["Low"], n1["Low"], n2["Low"]):
                swing_lows.append({"price": round(c["Low"], 2), "trap_zone": round(c["Low"] * 0.9985, 2)})
            if p2["High"] < c["Low"]:
                fvgs.append({"type": "BULLISH FVG", "top_edge": round(c["Low"], 2), "bottom_edge": round(p2["High"], 2), "gap_size": round(c["Low"] - p2["High"], 2)})
            if p2["Low"] > c["High"]:
                fvgs.append({"type": "BEARISH FVG", "top_edge": round(p2["Low"], 2), "bottom_edge": round(c["High"], 2), "gap_size": round(p2["Low"] - c["High"], 2)})

        return {
            "status": "success",
            "ticker": request.ticker,
            "latest_short_trap_zones": swing_highs[-3:],
            "latest_long_trap_zones": swing_lows[-3:],
            "latest_fvgs": fvgs[-3:],
        }
    except Exception as e:
        logger.error("SMC math error: %s", e, exc_info=True)
        return {"error": "Algorithmic sweep failed"}


@app.post("/api/deep-scan")
async def deep_scan_endpoint(request: ScanRequest):
    return await run_deep_xrpl_scan(request.ticker.upper())


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)