import hashlib
import os
import numpy as np
import psycopg2
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# --- CONFIGURATION & PATH SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

DATABASE_URL = os.getenv("DATABASE_URL")

# --- APP SETUP ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Ghost Machine - UK PropTech Risk Oracle")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

def get_db_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is not configured in the environment. Check your .env file.")
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        raise Exception(f"Database connection error: {str(e)}")

# --- AUDIT LOGGING SYSTEM ---
def log_audit(user_id: str, action: str, input_hash: str, dp_noise: float):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_logs (user_id, action_type, input_hash, dp_noise_level) VALUES (%s, %s, %s, %s);",
                (user_id, action, input_hash, dp_noise)
            )
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Audit log error: {str(e)}")

# --- DATA MODELS ---
class UserRegister(BaseModel):
    email: EmailStr
    tos_accepted: bool

class BurnCalculation(BaseModel):
    loan_amount: float
    annual_interest_rate: float
    lpa: str

# --- ENDPOINTS ---

@app.post("/api/register")
@limiter.limit("3/minute")
async def register_user(request: Request, user: UserRegister):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, tos_accepted) VALUES (%s, %s) ON CONFLICT (email) DO NOTHING;",
            (user.email.lower(), user.tos_accepted)
        )
        conn.commit()
    conn.close()
    return {"message": "User registered successfully."}

@app.post("/api/calculate-burn-rate")
@limiter.limit("5/minute")
async def calculate_burn_rate(request: Request, payload: BurnCalculation):
    # UK average planning friction baseline (4 months)
    delay_months = 4
    monthly_interest = (payload.loan_amount * payload.annual_interest_rate) / 12
    total_burn = monthly_interest * delay_months
    
    data_str = f"{payload.loan_amount}{payload.annual_interest_rate}{payload.lpa}"
    input_hash = hashlib.sha256(data_str.encode()).hexdigest()
    
    log_audit("ANON_USER", "CALCULATE_BURN", input_hash, 0.0)
    
    return {
        "lpa": payload.lpa,
        "projected_delay_months": delay_months,
        "total_financial_exposure_gbp": round(total_burn, 2),
        "disclaimer": "Estimates based on regional planning friction benchmarks."
    }

@app.get("/api/benchmark/{lpa_name}")
@limiter.limit("10/minute")
async def get_lpa_benchmark(request: Request, lpa_name: str):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT days_to_decision FROM practitioner_metrics WHERE lpa_name ILIKE %s;", (lpa_name,))
        rows = cur.fetchall()
    conn.close()
    
    vals = [r["days_to_decision"] for r in rows]
    
    # Differential Privacy Threshold (Minimum k-anonymity)
    if len(vals) < 3:
        raise HTTPException(status_code=404, detail="Insufficient data density for this region.")
    
    median = float(np.median(vals))
    # Laplace noise injection for regulatory durability
    noise = float(np.random.laplace(0, 2.5))
    
    log_audit("SYSTEM", "BENCHMARK_QUERY", "N/A", noise)
    
    return {
        "lpa": lpa_name,
        "median_approval_days": round(median + noise, 1),
        "risk_profile": "High" if median > 150 else "Moderate"
    }
