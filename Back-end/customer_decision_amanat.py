from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import pickle
import os
from sqlalchemy import create_engine, text

app = FastAPI(title="Customer Decision Tool Amanat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PG_USER = "huseynmajidov"
PG_HOST = "localhost"
PG_PORT = "5432"
EXCEL_PATH = "customer_decisions.xlsx"
MODEL_PATH = "amanat_model.pkl"

def get_engine(dbname):
    return create_engine(f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}")

# Load XGBoost model
model_data = None
if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        model_data = pickle.load(f)
    print(f"✅ XGBoost model loaded with {len(model_data['features'])} features")
else:
    print("⚠️  No model found — running on hard rules only")

class CustomerInput(BaseModel):
    name: str
    surname: str
    date_of_birth: str
    residency: str
    akb_score: Optional[float] = None
    akb_letter_grade: Optional[str] = None

def make_hard_decision(dob, akb_score):
    if dob is None:
        return None, "REJECTED — No birth date found"
    today = date.today()
    if isinstance(dob, str):
        dob = datetime.strptime(dob, "%d/%m/%Y").date()
    age = today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )
    if age < 18:
        return age, "REJECTED — Age is below 18"
    elif akb_score is None:
        return age, "REJECTED — AKB Score is empty"
    elif float(akb_score) < 300:
        return age, "REJECTED — AKB Score too low"
    return age, "PASSED"

def get_customer_from_db(name: str, surname: str):
    try:
        with get_engine("loan_users_db").connect() as conn:
            result = conn.execute(text("""
                SELECT
                    u.id AS user_id,
                    q.birth_date,
                    q.monthly_income,
                    q.monthly_expenses,
                    q.additional_income,
                    q.marital_status,
                    q.sex,
                    q.is_pep,
                    q.is_beneficial_owner,
                    q.is_related_to_pep
                FROM users u
                LEFT JOIN questionnaires q ON q.user_id = u.id
                WHERE LOWER(u.login) LIKE :name
                LIMIT 1
            """), {"name": f"%{name.lower()}%"}).fetchone()
        return result
    except:
        return None

def get_ml_features(user_id: str):
    try:
        with get_engine("amanat_ml_db").connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM customer_features WHERE user_id = :user_id
            """), {"user_id": user_id}).fetchone()
        return result
    except:
        return None

def run_xgboost(features_row, akb_score, age):
    try:
        if model_data is None:
            return None, None
        
        feature_names = model_data["features"]
        model = model_data["model"]
        
        row = dict(features_row._mapping) if features_row else {}
        
        feature_values = []
        for feat in feature_names:
            val = row.get(feat, -999)
            if val is None:
                val = -999
            feature_values.append(float(val))
        
        import numpy as np
        X = np.array([feature_values])
        prob = model.predict_proba(X)[0][1]
        prediction = "APPROVED" if prob >= 0.5 else "REJECTED — High credit risk"
        return round(float(prob) * 100, 1), prediction
    except Exception as e:
        print(f"XGBoost error: {e}")
        return None, None

def append_to_excel(row: dict):
    try:
        if os.path.exists(EXCEL_PATH):
            existing = pd.read_excel(EXCEL_PATH, sheet_name=None)
            approved_df = existing.get("Approved", pd.DataFrame())
            rejected_df = existing.get("Rejected", pd.DataFrame())
        else:
            approved_df = pd.DataFrame()
            rejected_df = pd.DataFrame()

        new_row = pd.DataFrame([row])
        if "APPROVED" in row["decision"]:
            approved_df = pd.concat([approved_df, new_row], ignore_index=True)
        else:
            rejected_df = pd.concat([rejected_df, new_row], ignore_index=True)

        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            approved_df.to_excel(writer, sheet_name="Approved", index=False)
            rejected_df.to_excel(writer, sheet_name="Rejected", index=False)
    except Exception as e:
        print(f"Excel error: {e}")

@app.get("/")
def root():
    return {"status": "Customer Decision Tool Amanat is running"}

@app.post("/submit-customer")
def submit_customer(customer: CustomerInput):
    try:
        # Stage 1 — Hard rules
        age, hard_decision = make_hard_decision(customer.date_of_birth, customer.akb_score)

        ml_score = None
        ml_decision = None
        decision_type = "Hard Rules"

        if hard_decision != "PASSED":
            final_decision = hard_decision
        else:
            # Stage 2 — Try to find customer in DB and run XGBoost
            db_customer = get_customer_from_db(customer.name, customer.surname)

            if db_customer:
                user_id = db_customer[0]
                features_row = get_ml_features(user_id)

                if features_row:
                    ml_score, ml_decision = run_xgboost(features_row, customer.akb_score, age)
                    decision_type = "XGBoost ML Model"

            if ml_decision:
                final_decision = ml_decision
            else:
                final_decision = "APPROVED"
                decision_type = "Hard Rules"

        row = {
            "name":             customer.name,
            "surname":          customer.surname,
            "date_of_birth":    customer.date_of_birth,
            "residency":        customer.residency,
            "age":              age,
            "akb_score":        customer.akb_score,
            "akb_letter_grade": customer.akb_letter_grade,
            "decision":         final_decision,
            "decision_type":    decision_type,
            "ml_score":         ml_score,
            "submitted_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        append_to_excel(row)

        try:
            with get_engine("submissions_db").connect() as conn:
                conn.execute(text("""
                    INSERT INTO customer_submissions
                        (name, surname, date_of_birth, residency, akb_score, akb_letter_grade, age, decision, submitted_at)
                    VALUES
                        (:name, :surname, :date_of_birth, :residency, :akb_score, :akb_letter_grade, :age, :decision, :submitted_at)
                """), row)
                conn.commit()
        except Exception as db_err:
            print(f"DB ERROR: {db_err}")

        return {
            "age":              age,
            "akb_score":        customer.akb_score,
            "akb_letter_grade": customer.akb_letter_grade,
            "decision":         final_decision,
            "decision_type":    decision_type,
            "ml_score":         ml_score,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
                ORDER BY timestamp DESC LIMIT 1
            """), {"user_id": user_id}).fetchone()

        akb_score = akb_result[0] if akb_result else None
        akb_grade = akb_result[1] if akb_result else None

        age, hard_decision = make_hard_decision(dob, akb_score)

        if hard_decision != "PASSED":
            final_decision = hard_decision
            ml_score = None
            decision_type = "Hard Rules"
        else:
            features_row = get_ml_features(user_id)
            ml_score, ml_decision = run_xgboost(features_row, akb_score, age)
            final_decision = ml_decision if ml_decision else "APPROVED"
            decision_type = "XGBoost ML Model" if ml_decision else "Hard Rules"

        return {
            "user_id":          user_id,
            "date_of_birth":    str(dob),
            "age":              age,
            "akb_score":        akb_score,
            "akb_letter_grade": akb_grade,
            "decision":         final_decision,
            "decision_type":    decision_type,
            "ml_score":         ml_score,
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
                FROM akb_scores WHERE is_successful = TRUE
                ORDER BY user_id, timestamp DESC
            """)).fetchall()

        akb_lookup = {row[0]: (row[1], row[2]) for row in akb_scores}

        approved = []
        rejected = []

        for user_id, dob in users:
            akb_score, akb_grade = akb_lookup.get(user_id, (None, None))
            age, hard_decision = make_hard_decision(dob, akb_score)

            if hard_decision != "PASSED":
                final_decision = hard_decision
                ml_score = None
                decision_type = "Hard Rules"
            else:
                features_row = get_ml_features(user_id)
                ml_score, ml_decision = run_xgboost(features_row, akb_score, age)
                final_decision = ml_decision if ml_decision else "APPROVED"
                decision_type = "XGBoost ML Model" if ml_decision else "Hard Rules"

            row = {
                "user_id":       user_id,
                "date_of_birth": str(dob),
                "age":           age,
                "akb_score":     akb_score,
                "akb_grade":     akb_grade,
                "decision":      final_decision,
                "decision_type": decision_type,
                "ml_score":      ml_score,
            }

            if "APPROVED" in final_decision:
                approved.append(row)
            else:
                rejected.append(row)

        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            pd.DataFrame(approved).to_excel(writer, sheet_name="Approved", index=False)
            pd.DataFrame(rejected).to_excel(writer, sheet_name="Rejected", index=False)

        return {
            "status":          "Export complete ✅",
            "file":            EXCEL_PATH,
            "total_customers": len(users),
            "approved":        len(approved),
            "rejected":        len(rejected)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
