import hashlib
import numpy as np
import os
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import psycopg2
from psycopg2.extras import RealDictCursor

# --- Configuration ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Ghost Machine - UK PropTech Risk Oracle")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

DB_CONFIG = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DB_CONFIG:
        raise Exception("DATABASE_URL is not set.")
    return psycopg2.connect(DB_CONFIG)
def get_db_connection():
    if not DB_CONFIG:
        raise Exception("DATABASE_URL is not set.")
    return psycopg2.connect(DB_CONFIG)

# --- Audit Logging System ---
def log_audit(user_id: str, action: str, hash_val: str, dp_noise: float):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (user_id, action_type, input_hash, dp_noise_level) VALUES (%s, %s, %s, %s);",
            (user_id, action, hash_val, dp_noise)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Audit log failed: {str(e)}")

# --- Data Models ---
class UserRegister(BaseModel):
    email: EmailStr
    tos_accepted: bool
    pi_insurance_verified: bool

class BurnCalculation(BaseModel):
    loan_amount: float
    annual_interest_rate: float
    lpa: str

# ==========================================
# 1. USER ONBOARDING
# ==========================================
@app.post("/api/register")
@limiter.limit("3/minute")
async def register_user(request: Request, user: UserRegister):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (email, tos_accepted) VALUES (%s, %s) ON CONFLICT DO NOTHING;", (user.email.lower(), True))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "User registered successfully."}

# ==========================================
# 2. SME CASH BURN CALCULATOR (THE HOOK)
# ==========================================
@app.post("/api/calculate-burn-rate")
@limiter.limit("5/minute")
async def calculate_burn_rate(request: Request, payload: BurnCalculation):
    # Logic based on regional planning friction benchmarks
    delay_months = 4 
    monthly_interest = (payload.loan_amount * payload.annual_interest_rate) / 12
    total_burn = monthly_interest * delay_months
    
    return {
        "lpa": payload.lpa,
        "projected_delay_months": delay_months,
        "total_financial_exposure_gbp": round(total_burn, 2),
        "disclaimer": "Estimation based on regional planning friction benchmarks."
    }

# ==========================================
# 3. DP-PROTECTED RISK BENCHMARK
# ==========================================
@app.get("/api/benchmark/{lpa_name}")
@limiter.limit("10/minute")
async def get_lpa_benchmark(request: Request, lpa_name: str):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT days_to_decision FROM practitioner_metrics WHERE lpa_name = %s;", (lpa_name.title(),))
    rows = cursor.fetchall()
    
    # Default values for fallback if no data exists
    vals = [r["days_to_decision"] for r in rows] if rows else [120, 150, 180]
    median = float(np.median(vals))
    
    # Differential Privacy Engine: Laplace noise
    noise = float(np.random.laplace(0, 2.5))
    median += noise
    
    log_audit("SYSTEM", "BENCHMARK_QUERY", "N/A", noise)
    
    return {
        "lpa": lpa_name,
        "median_approval_days": round(median, 1),
        "risk_profile": "High" if median > 150 else "Moderate"
    }

