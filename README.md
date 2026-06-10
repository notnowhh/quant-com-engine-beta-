# QUANT-COM Terminal
**Enterprise-Grade Real-Time Quantitative Trading Terminal**

[![Live Demo](https://img.shields.io/badge/Live_Demo-quantcom.qzz.io-D4AF37?style=for-the-badge)](https://quantcom.qzz.io/)
[![Tech Stack](https://img.shields.io/badge/Stack-React_|_FastAPI_|_Python-blue?style=for-the-badge)]()

QUANT-COM is a full-stack quantitative trading terminal designed to aggregate, normalize, and process market data across Crypto, Forex, and Real World Assets (RWAs). It feeds real-time price action into a decoupled Python algorithmic engine to compute volume-weighted Smart Money Concepts (SMC) metrics and structural market zones.

---

## ✨ Core Features

* **Decoupled SMC Algorithmic Engine:** A pure Python mathematical engine that computes Fair Value Gaps (FVG) and institutional trap zones (Bull/Bear traps) using volume-weighted heuristics.
* **Prop-Firm Risk Matrix:** Mathematical backend module that calculates optimal lot sizing based on user-defined daily drawdown limits, stop-loss parameters, and account equity.
* **Consolidated Order Book (COB):** Simultaneously maps and merges bid/ask arrays across centralized exchanges to calculate global market depth.
* **BlackRock RWA Wallet Tracker:** Automated on-chain monitor tracking dedicated Ethereum institutional addresses for real-time mint/burn events via the Blockchair API.
* **Proxy-Liquidity Routing:** Automatically maps RWAs to highly liquid ETF proxies (e.g., XAU → GLD) to extract accurate institutional volume profiles, with graceful degradation to `yfinance` for Forex pairs.
* **WebGL-Accelerated UI:** Frontend dashboard built with React, TypeScript, and Vite, leveraging TradingView's `lightweight-charts` and strict React memoization to eliminate render thrashing.

---

## 🛠️ Tech Stack

| Frontend | Backend | APIs & Data Feeds |
| :--- | :--- | :--- |
| React 18, TypeScript | Python, FastAPI | Binance, Kraken COB |
| Vite | Uvicorn | Blockchair API (On-Chain) |
| Tailwind CSS, Shadcn UI | Pandas, NumPy | Alpaca IEX, yfinance |
| Lightweight Charts (TradingView) | Math & SMC Algorithms | Custom Proxy Routing |

---

## 🚀 Getting Started

Get into the web and type your Asset (eg:BTC).
If the Asset is in XRPL , you have a extra deep scan feature too!
