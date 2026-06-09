# Quant-Com
**Enterprise-Grade Real-Time Quantitative Trading Terminal**
>>App Link: https://quantcom.qzz.io/
## 1. Project Overview & Architecture Blueprint
QUANT-COM is a full-stack quantitative trading terminal that aggregates, normalizes, and processes market data across multiple asset classes (Crypto, Forex, and Real World Assets). 
Built on an asynchronous FastAPI backend, the system feeds normalized price action into a decoupled, pure Python algorithmic engine that computes volume-weighted Smart Money Concepts (SMC) metrics. 
The frontend is built using React, TypeScript, and Vite, utilizing memoized data streams to render real-time technical indicators and structural market zones.

## 2. Core Technical Features (Production Implemented)

*   **Consolidated Order Book (COB):**
    *   Simultaneously maps and merges bid/ask arrays across centralized exchanges to calculate global market depth.
*   **BlackRock RWA Wallet Tracker:**
    *   Automated on-chain monitor tracking dedicated Ethereum institutional addresses for real-time mint/burn events and transactional capital flows via the Blockchair API.
*   **Prop-Firm Risk Matrix Engine:**
    *  Mathematical backend module that enforces risk management by automatically calculating optimal lot sizing based on user-defined daily drawdown limits, stop-loss parameters, and account tier equity.
*   **Optimised Real-Time UI:**
    *   Frontend dashboard constructed with Vite, React, and TypeScriptpt.
    *   Leverages TradingView's optimized `lightweight-charts` for WebGL-accelerated rendering.
    *   Utilizes deep React structural memoization (`useMemo`, `useCallback`) and lifecycle optimization to completely eliminate UI render thrashing.
    *  Styled with a dark glassmorphism theme and dynamic, state-driven visual indicators.

## 3. Advanced Analytics & Algorithmic Implementation

### Decoupled Volume-Weighted SMC Engine
The core Smart Money Concepts (SMC) algorithm is implemented as a pure Python function (run_smc_engine). It is completely decoupled from data ingestion, accepting a standardized list[{"h", "l", "c", "v"}] payload. This modularity allows the exact same mathematical engine to compute structural setups across any data source without code modifications

### Institutional Liquidity & Trap Zone Processor
The engine analyzes historical bars and volume metrics to map out key institutional market zones:
*   **Short Traps (Bear Traps):**
    *   Detected at structural swing lows (5-candle window) accompanied by a relative volume spike ($rel\_vol > 1.25$), signaling institutional stop-sweeps and potential upward reversals.
*   **Long Traps (Bull Traps):**
    *   Detected at structural swing highs accompanied by a volume drop-off ($rel\_vol < 0.80$), signaling breakout exhaustion due to a lack of institutional volume.
*   **Fair Value Gaps (FVG):**
    *  Tracks 3-candle price imbalances to dynamically draw structural target zones where price is statistically likely to rebalance.

### Proxy-Liquidity Mapping Layer
To calculate volume-weighted logic on assets without a centralized exchange tape, the system handles data ingestion with an automated fallback mechanism:
*   **RWA Proxy Routing:** Real World Assets are programmatically mapped to highly liquid ETF proxies (e.g., XAU $\rightarrow$ GLD, XAG $\rightarrow$ SLV) to extract accurate institutional volume profiles using the Alpaca IEX data feed.
*   **Graceful Degradation:** For Forex pairs, the system automatically falls back to yfinance price action data, downgrading the SMC calculation confidence score to MODERATE while keeping the terminal fully operational
