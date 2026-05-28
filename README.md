# (QUANT-COM Engine) (Beta)
LINK: https://app-bobntlm0j9q9.appmedo.com/
A high-performance, multi-threaded order flow imbalance engine built for the XRPL ledger. Designed to intercept massive on-chain whale sweeps and calculate resting depth liquidity biases in real-time.

## 🧠 Core Architecture
* **Core 1: Exchange Scanner** - Tracks resting depth imbalances (Bids vs. Asks) across major centralized exchanges.
* **Core 2: XRPL Gatekeeper** - A highly resilient WebSocket stream monitoring the XRPL for massive block transactions over a dynamic threshold.
* **Core 3: Accumulation Processor** - Captures 15-second volume bursts to calculate quantitative order book skew (Bullish/Bearish/Neutral).
* **Macro Volatility Agent** - Intercepts global RSS news feeds to halt limit orders during high-impact macroeconomic events.

## ⚙️ Production Hardening
* **Native LRU Hash Cache:** Bound to 50,000 entries to prevent long-term memory leaks.
* **Async Resiliency:** Implements `asyncio.Lock()` to prevent UI thread deadlocks and features auto-reconnecting WebSocket loops.
* **Graceful Teardown:** OS-level signal trapping (`os._exit(0)`) prevents hanging background threads during shutdown.

## 🛠️ Quick Start
1. Clone the repository.
2. Install dependencies: `pip install websockets`
3. Run the engine: `python omni_matrix.py`
Working on it !
