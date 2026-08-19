from fastapi import FastAPI, HTTPException
from datetime import date
import pandas as pd
from sqlalchemy import create_engine, text

app = FastAPI(title="Customer Decision Tool Amanat")

PG_USER = "huseynmajidov"
PG_HOST = "localhost"
PG_PORT = "5432"

def get_engine(dbname):
    return create_engine(f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}")

def make_decision(dob, akb_score):
    if dob is None:
        return None, "REJECTED — No birth date found"
    today = date.today()
    age = today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )
    if age < 18:
        return age, "REJECTED — Age is below 18"
    elif akb_score is None:
        return age, "REJECTED — AKB Score is empty"
    elif float(akb_score) < 300:
        return age, "REJECTED — AKB Score too low"
    else:
        return age, "APPROVED"

@app.get("/")
def root():
    return {"status": "Customer Decision Tool Amanat is running"}

@app.get("/check-customer/{user_id}")
def check_customer_by_id(user_id: str):
    try:
        with get_engine("loan_users_db").connect() as conn:
            result = conn.execute(text("""
                SELECT q.birth_date
                FROM users u
                LEFT JOIN questionnaires q ON q.user_id = u.id
                WHERE u.id = :user_id
            """), {"user_id": user_id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="User not found")

        dob = result[0]

        with get_engine("akb_score_db").connect() as conn:
            akb_result = conn.execute(text("""
                SELECT response_score_point, response_score_response
                FROM akb_scores
                WHERE user_id = :user_id AND is_successful = TRUE
                ORDER BY timestamp DESC
                LIMIT 1
            """), {"user_id": user_id}).fetchone()

        akb_score = akb_result[0] if akb_result else None
        akb_grade = akb_result[1] if akb_result else None

        age, decision = make_decision(dob, akb_score)

        return {
            "user_id": user_id,
            "date_of_birth": str(dob),
            "age": age,
            "akb_score": akb_score,
            "akb_letter_grade": akb_grade,
            "decision": decision
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export-all")
def export_all():
    try:
        with get_engine("loan_users_db").connect() as conn:
            users = conn.execute(text("""
                SELECT u.id, q.birth_date
                FROM users u
                LEFT JOIN questionnaires q ON q.user_id = u.id
            """)).fetchall()

        with get_engine("akb_score_db").connect() as conn:
            akb_scores = conn.execute(text("""
                SELECT DISTINCT ON (user_id)
                    user_id, response_score_point, response_score_response
                FROM akb_scores
                WHERE is_successful = TRUE
                ORDER BY user_id, timestamp DESC
            """)).fetchall()

        akb_lookup = {row[0]: (row[1], row[2]) for row in akb_scores}

        approved = []
        rejected = []

        for user_id, dob in users:
            akb_score, akb_grade = akb_lookup.get(user_id, (None, None))
            age, decision = make_decision(dob, akb_score)

            row = {
                "user_id": user_id,
                "date_of_birth": str(dob),
                "age": age,
                "akb_score": akb_score,
                "akb_letter_grade": akb_grade,
                "decision": decision
            }

            if "APPROVED" in decision:
                approved.append(row)
            else:
                rejected.append(row)

        output_path = "customer_decisions.xlsx"
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            pd.DataFrame(approved).to_excel(writer, sheet_name="Approved", index=False)
            pd.DataFrame(rejected).to_excel(writer, sheet_name="Rejected", index=False)

        return {
            "status": "Export complete ✅",
            "file": output_path,
            "total_customers": len(users),
            "approved": len(approved),
            "rejected": len(rejected)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))