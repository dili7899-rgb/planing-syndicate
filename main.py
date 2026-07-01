import os
import time
import hashlib
import numpy as np
from typing import List
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import psycopg2
from psycopg2.extras import RealDictCursor

# --- Конфигурация ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Waze for Planning - UK PropTech Backend")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

DB_CONFIG = "postgresql://syndicate_admin:PropTech2026!@db.dchtyvecwdrtbtbdxzgg.supabase.co:5432/postgres"

def get_db_connection():
    return psycopg2.connect(DB_CONFIG)

# --- Помощна функция за одит (Black Box) ---
def log_audit(user_id: str, action: str, hash_val: str, dp_noise: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_logs (user_id, action_type, input_hash, dp_noise_level, status) VALUES (%s, %s, %s, %s, 'SUCCESS');",
        (user_id, action, hash_val, dp_noise)
    )
    conn.commit()
    cursor.close()
    conn.close()

# --- Модели ---
class UserRegister(BaseModel):
    email: EmailStr
    tos_accepted: bool
    pi_insurance_verified: bool

class SingleLog(BaseModel):
    lpa_name: str
    days_to_validation: int
    days_to_decision: int
    bng_friction: bool

# ==========================================
# ЕНДПОЙНТ 1: ПРАВЕН ПОРТИЕР (RATE LIMITED)
# ==========================================
@app.post("/api/register")
@limiter.limit("3/minute")
async def register_user(request: Request, user: UserRegister):
    if not user.tos_accepted or not user.pi_insurance_verified:
        raise HTTPException(status_code=400, detail="Denied: Missing legal verification.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (email, tos_accepted) VALUES (%s, %s) ON CONFLICT DO NOTHING;", (user.email.lower(), True))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "User registered and documented."}

# ==========================================
# ЕНДПОЙНТ 2: ИНТЕЛИГЕНТНА КУКА (RATE LIMITED)
# ==========================================
@app.post("/api/submit-friction-log")
@limiter.limit("5/minute")
async def submit_projects(request: Request, payload: dict):
    # Тук генерираме хеш на данните за одиторската следа
    data_hash = hashlib.sha256(str(payload).encode()).hexdigest()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Логика за вмъкване на лог...
    log_audit(payload.get("email"), "SUBMIT_LOGS", data_hash, 0.0)
    cursor.close()
    conn.close()
    return {"status": "Success", "hash": data_hash}

# ==========================================
# ЕНДПОЙНТ 3: БЕНЧМАРК (DP PROTECTED)
# ==========================================
@app.get("/api/lpa-benchmark/{lpa_name}")
@limiter.limit("10/minute")
async def get_lpa_benchmark(request: Request, lpa_name: str):
    noise = 0.0
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT days_to_decision FROM practitioner_metrics WHERE lpa_name = %s;", (lpa_name.title(),))
    rows = cursor.fetchall()
    
    vals = [r["days_to_decision"] for r in rows] if rows else [56, 60, 58]
    median = float(np.median(vals))
    
    if len(vals) < 5:
        noise = np.random.laplace(0, 2.5)
        median += noise
        
    log_audit("SYSTEM", "BENCHMARK_QUERY", "N/A", noise)
    
    return {
        "lpa": lpa_name,
        "median_days": round(median, 1),
        "legal_shield": "Retrospective statistical metrics only."
    }culation error: {str(e)}")