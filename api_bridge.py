from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import omni_matrix 

app = FastAPI()

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
async def scan_flow(query: TokenQuery):
    token = query.ticker.upper()
    
    # Calls the new API-specific hook inside your matrix
    final_data = await omni_matrix.run_api_scan(token)
    
    return final_data