from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import omni_matrix 

app = FastAPI()

# This allows your MeDo frontend to talk to your local backend securely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenQuery(BaseModel):
    ticker: str

@app.get("/")
def root():
    return {"status": "Master QUANT-COM API Online"}

@app.post("/scan")
def scan_flow(query: TokenQuery):
    token = query.ticker.upper()
    
    # We will hook this directly into your real omni_matrix logic next.
    # For now, we return this to test the connection to the UI!
    return {
        "asset": token,
        "bias": "🟢 BULLISH (Strong Resting Support Skew)",
        "whale_blocks": 14,
        "macro_status": "Clear"
    }