from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import omni_matrix 
import asyncio # Added this

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# WAKES UP THE BACKGROUND SYNCER WHEN THE SERVER STARTS!
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(omni_matrix.live_order_book_syncer())

class TokenQuery(BaseModel):
    ticker: str

@app.get("/")
def root():
    return {"status": "Master QUANT-COM API Online"}

@app.post("/scan")
async def scan_flow(query: TokenQuery):
    token = query.ticker.upper()
    return await omni_matrix.get_live_state(token)

@app.post("/deep-scan")
async def deep_scan_flow(query: TokenQuery):
    token = query.ticker.upper()
    return await omni_matrix.run_deep_xrpl_scan(token)