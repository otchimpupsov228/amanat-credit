from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime, timedelta
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

model_data = None
if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        model_data = pickle.load(f)
    print(f"✅ XGBoost model loaded with {len(model_data['features'])} features")
else:
    print("⚠️  No model found — running on hard rules only")

class CustomerInput(BaseModel):
    customer_type: str = "new"
    step: int = 2
    name: Optional[str] = None
    surname: Optional[str] = None
    date_of_birth: Optional[str] = None
    residency: Optional[str] = None
    user_id: Optional[str] = None
    akb_score: Optional[float] = None
    akb_letter_grade: Optional[str] = None
    generated_user_id: Optional[str] = None
    monthly_income: Optional[float] = None
    monthly_expenses: Optional[float] = None
    outstanding_debt: Optional[float] = None
    overdue_amount: Optional[float] = None
    has_overdue: Optional[bool] = False

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
        from datetime import date
        import numpy as np

        today = date.today()

        with get_engine("loan_users_db").connect() as conn:
            user = conn.execute(text("""
                SELECT q.sex, q.birth_date, q.monthly_income, q.monthly_expenses,
                    q.additional_income, q.marital_status, q.is_pep,
                    q.is_beneficial_owner, q.is_related_to_pep
                FROM users u
                LEFT JOIN questionnaires q ON q.user_id = u.id
                WHERE u.id = :uid
            """), {"uid": user_id}).fetchone()

        with get_engine("loans_db").connect() as conn:
            loan = conn.execute(text("""
                SELECT COUNT(*) AS total_loans, SUM(amount) AS total_amount_borrowed,
                    AVG(amount) AS avg_loan_amount, AVG(term) AS avg_loan_term,
                    MAX(amount) AS max_loan_amount, MIN(amount) AS min_loan_amount,
                    SUM(CASE WHEN tag='paid' THEN 1 ELSE 0 END) AS loans_paid_count,
                    SUM(CASE WHEN tag='overdue' THEN 1 ELSE 0 END) AS loans_overdue,
                    SUM(CASE WHEN tag='active' THEN 1 ELSE 0 END) AS loans_active,
                    SUM(CASE WHEN tag='written_off' THEN 1 ELSE 0 END) AS loans_written_off,
                    EXTRACT(EPOCH FROM (MAX(created)-MIN(created)))/86400 AS days_between_first_last_loan
                FROM loans WHERE user_id = :uid
            """), {"uid": user_id}).fetchone()

            actions = conn.execute(text("""
                SELECT
                    SUM(CASE WHEN tag='approved' THEN 1 ELSE 0 END) AS times_approved,
                    SUM(CASE WHEN tag='in_review' THEN 1 ELSE 0 END) AS times_in_review,
                    SUM(CASE WHEN tag='paid' THEN 1 ELSE 0 END) AS times_paid_action,
                    SUM(CASE WHEN tag='written_off' THEN 1 ELSE 0 END) AS times_written_off,
                    SUM(CASE WHEN tag='active' THEN 1 ELSE 0 END) AS times_active
                FROM loan_actions WHERE user_id = :uid
            """), {"uid": user_id}).fetchone()

            states = conn.execute(text("""
                SELECT
                    SUM(CASE WHEN ls.transaction_type='payment' AND EXTRACT(DAY FROM (ls.created-ls.target_date)) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS delayed_payments,
                    SUM(CASE WHEN ls.transaction_type='payment' AND EXTRACT(DAY FROM (ls.created-ls.target_date)) > 30 THEN 1 ELSE 0 END) AS failed_payments_30plus,
                    AVG(CASE WHEN ls.transaction_type='payment' AND ls.created>ls.target_date THEN EXTRACT(DAY FROM (ls.created-ls.target_date)) ELSE 0 END) AS avg_delay_days,
                    MAX(CASE WHEN ls.transaction_type='payment' AND ls.created>ls.target_date THEN EXTRACT(DAY FROM (ls.created-ls.target_date)) ELSE 0 END) AS max_delay_days,
                    SUM(ls.overdue_interest) AS total_overdue_interest,
                    SUM(ls.debt) AS total_debt_accumulated
                FROM loan_states ls JOIN loans l ON l.id=ls.loan_id
                WHERE l.user_id = :uid
            """), {"uid": user_id}).fetchone()

        with get_engine("payments_db").connect() as conn:
            pay = conn.execute(text("""
                SELECT COUNT(*) AS total_payments,
                    SUM(CASE WHEN is_successful=TRUE THEN 1 ELSE 0 END) AS successful_payments,
                    SUM(CASE WHEN is_successful=FALSE THEN 1 ELSE 0 END) AS failed_payments,
                    AVG(amount) AS avg_payment_amount, MAX(amount) AS max_payment_amount,
                    COUNT(DISTINCT card_id) AS num_cards_used
                FROM payments WHERE user_id = :uid
            """), {"uid": user_id}).fetchone()

            cards = conn.execute(text("""
                SELECT COUNT(*) AS total_cards,
                    SUM(CASE WHEN is_verified=TRUE THEN 1 ELSE 0 END) AS verified_cards,
                    SUM(CASE WHEN is_main=TRUE THEN 1 ELSE 0 END) AS has_main_card,
                    SUM(CASE WHEN is_for_disbursement=TRUE THEN 1 ELSE 0 END) AS has_disbursement_card,
                    SUM(CASE WHEN deleted IS NOT NULL THEN 1 ELSE 0 END) AS deleted_cards
                FROM cards WHERE user_id = :uid
            """), {"uid": user_id}).fetchone()

        with get_engine("akb_score_db").connect() as conn:
            akb = conn.execute(text("""
                SELECT response_score_point AS akb_score,
                    response_score_calculated AS akb_calculated,
                    response_score_exclusion AS akb_exclusion,
                    COUNT(*) OVER () AS akb_check_count
                FROM akb_scores WHERE user_id=:uid AND is_successful=TRUE
                ORDER BY timestamp DESC LIMIT 1
            """), {"uid": user_id}).fetchone()

        with get_engine("akb_history_db").connect() as conn:
            hist = conn.execute(text("""
                SELECT liab_count, liab_outstanding_debt_main_sum AS total_outstanding_debt,
                    liab_outstanding_debt_interest_sum AS total_outstanding_interest,
                    liab_days_main_overdue_max AS max_days_overdue,
                    liab_days_main_overdue_sum AS total_days_overdue,
                    response_score_point AS history_score,
                    response_balance AS credit_balance
                FROM akb_history_summary WHERE user_id=:uid
                ORDER BY timestamp DESC LIMIT 1
            """), {"uid": user_id}).fetchone()

        with get_engine("doc_front_db").connect() as conn:
            docs = conn.execute(text("""
                SELECT COUNT(*) AS total_docs_uploaded,
                    COUNT(DISTINCT loan_id) AS loans_with_docs
                FROM doc_front_all WHERE user_id=:uid
            """), {"uid": user_id}).fetchone()

        def v(row, key, default=-999):
            if row is None: return default
            try: val = row._mapping.get(key)
            except: val = None
            return float(val) if val is not None else default

        dob = user._mapping.get("birth_date") if user else None
        age = -999
        if dob:
            dob = pd.to_datetime(dob).date()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        sex = user._mapping.get("sex") if user else None
        sex_encoded = 1 if sex == "male" else (0 if sex == "female" else -999)
        monthly_income = v(user, "monthly_income")
        monthly_expenses = v(user, "monthly_expenses")
        additional_income = v(user, "additional_income")
        net_income = (monthly_income if monthly_income != -999 else 0) - (monthly_expenses if monthly_expenses != -999 else 0)
        income_total = (monthly_income if monthly_income != -999 else 0) + (additional_income if additional_income != -999 else 0)
        total_payments = v(pay, "total_payments")
        successful_payments = v(pay, "successful_payments")
        delayed_payments = v(states, "delayed_payments", 0)
        failed_30plus = v(states, "failed_payments_30plus", 0)
        total_outstanding_debt = v(hist, "total_outstanding_debt", 0)
        avg_loan_amount = v(loan, "avg_loan_amount", 0)
        total_overdue_interest = v(states, "total_overdue_interest", 0)
        total_debt_accumulated = v(states, "total_debt_accumulated", 0)
        times_in_review = v(actions, "times_in_review", 0)
        times_approved = v(actions, "times_approved", 0)
        max_days_overdue = v(hist, "max_days_overdue", 0)
        total_cards = v(cards, "total_cards", 0)
        verified_cards = v(cards, "verified_cards", 0)
        total_docs = v(docs, "total_docs_uploaded", 0)
        loans_written_off = v(loan, "loans_written_off", 0)
        akb_score_val = v(akb, "akb_score")

        row = {
            "age": age, "sex_encoded": sex_encoded,
            "marital_status": v(user, "marital_status", -1),
            "monthly_income": monthly_income, "monthly_expenses": monthly_expenses,
            "additional_income": additional_income, "net_income": net_income, "income_total": income_total,
            "akb_score": akb_score_val, "akb_calculated": v(akb, "akb_calculated"),
            "akb_exclusion": v(akb, "akb_exclusion"), "akb_check_count": v(akb, "akb_check_count"),
            "has_akb_score": 1 if akb_score_val != -999 else 0,
            "history_score": v(hist, "history_score"),
            "total_loans": v(loan, "total_loans"), "total_amount_borrowed": v(loan, "total_amount_borrowed"),
            "avg_loan_amount": avg_loan_amount, "avg_loan_term": v(loan, "avg_loan_term"),
            "max_loan_amount": v(loan, "max_loan_amount"), "min_loan_amount": v(loan, "min_loan_amount"),
            "loans_paid_count": v(loan, "loans_paid_count"), "loans_overdue": v(loan, "loans_overdue"),
            "loans_active": v(loan, "loans_active"), "loans_written_off": loans_written_off,
            "days_between_first_last_loan": v(loan, "days_between_first_last_loan"),
            "times_approved": times_approved, "times_in_review": times_in_review,
            "times_paid_action": v(actions, "times_paid_action"),
            "times_written_off": v(actions, "times_written_off"),
            "times_active": v(actions, "times_active"),
            "approval_rate": times_approved / max(times_in_review, 1),
            "total_payments": total_payments, "successful_payments": successful_payments,
            "failed_payments": v(pay, "failed_payments"), "avg_payment_amount": v(pay, "avg_payment_amount"),
            "max_payment_amount": v(pay, "max_payment_amount"), "num_cards_used": v(pay, "num_cards_used"),
            "payment_success_rate": successful_payments / max(total_payments, 1) if total_payments != -999 else -999,
            "delayed_payments": delayed_payments, "delayed_payment_rate": delayed_payments / max(total_payments, 1) if total_payments != -999 else -999,
            "failed_payments_30plus": failed_30plus, "failed_payment_30plus_rate": failed_30plus / max(total_payments, 1) if total_payments != -999 else -999,
            "avg_delay_days": v(states, "avg_delay_days"), "max_delay_days": v(states, "max_delay_days"),
            "total_overdue_interest": total_overdue_interest, "total_debt_accumulated": total_debt_accumulated,
            "liab_count": v(hist, "liab_count"), "total_outstanding_debt": total_outstanding_debt,
            "total_outstanding_interest": v(hist, "total_outstanding_interest"),
            "max_days_overdue": max_days_overdue, "total_days_overdue": v(hist, "total_days_overdue"),
            "credit_balance": v(hist, "credit_balance"),
            "debt_to_income": total_outstanding_debt / max(income_total, 1),
            "loan_amount_to_income": avg_loan_amount / max(income_total, 1),
            "overdue_interest_to_debt": total_overdue_interest / max(total_debt_accumulated, 1),
            "is_repeat_borrower": 1 if v(loan, "total_loans", 0) > 1 else 0,
            "has_overdue_history": 1 if max_days_overdue > 0 else 0,
            "has_written_off": 1 if loans_written_off > 0 else 0,
            "total_cards": total_cards, "verified_cards": verified_cards,
            "has_main_card": v(cards, "has_main_card"), "has_disbursement_card": v(cards, "has_disbursement_card"),
            "deleted_cards": v(cards, "deleted_cards"),
            "card_verified_rate": verified_cards / max(total_cards, 1),
            "total_docs_uploaded": total_docs,
            "loans_with_docs": v(docs, "loans_with_docs"),
            "has_uploaded_docs": 1 if total_docs > 0 else 0,
            "is_pep": int(bool(user._mapping.get("is_pep"))) if user else 0,
            "is_beneficial_owner": int(bool(user._mapping.get("is_beneficial_owner"))) if user else 0,
            "is_related_to_pep": int(bool(user._mapping.get("is_related_to_pep"))) if user else 0,
        }
        return row
    except Exception as e:
        print(f"get_ml_features error: {e}")
        return None

def run_xgboost(features_row, akb_score, age):
    try:
        if model_data is None:
            return None, None

        feature_names = model_data["features"]
        model = model_data["model"]

        if isinstance(features_row, dict):
            row = features_row
        else:
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

def build_reasons(age, akb_score, decision, features_row=None, ml_score=None):
    reasons = []

    if age is not None and age < 18:
        reasons.append({"type": "red", "text": f"Age {age} is below the minimum requirement of 18"})
    elif age is not None and age >= 18:
        reasons.append({"type": "green", "text": f"Age {age} meets the minimum requirement"})

    if akb_score is None:
        reasons.append({"type": "red", "text": "No AKB credit score found"})
    elif akb_score < 300:
        reasons.append({"type": "red", "text": f"AKB score {akb_score} is below the minimum of 300"})
    elif akb_score < 500:
        reasons.append({"type": "yellow", "text": f"AKB score {akb_score} is acceptable but low"})
    else:
        reasons.append({"type": "green", "text": f"AKB score {akb_score} is good"})

    if features_row and isinstance(features_row, dict):
        loans_paid = features_row.get("loans_paid_count", -999)
        if loans_paid != -999 and loans_paid > 0:
            reasons.append({"type": "green", "text": f"{int(loans_paid)} loan(s) fully paid back"})
        elif loans_paid == 0:
            reasons.append({"type": "yellow", "text": "No loans paid back yet"})

        loans_overdue = features_row.get("loans_overdue", -999)
        if loans_overdue != -999 and loans_overdue > 0:
            reasons.append({"type": "red", "text": f"{int(loans_overdue)} overdue loan(s) on record"})

        success_rate = features_row.get("payment_success_rate", -999)
        if success_rate != -999 and success_rate > 0:
            pct = round(success_rate * 100, 1)
            color = "green" if pct >= 80 else ("yellow" if pct >= 50 else "red")
            reasons.append({"type": color, "text": f"Payment success rate: {pct}%"})

        overdue_interest = features_row.get("total_overdue_interest", -999)
        if overdue_interest != -999 and overdue_interest > 0:
            reasons.append({"type": "red", "text": f"Total overdue interest: {round(overdue_interest, 2)} AZN"})

        written_off = features_row.get("loans_written_off", -999)
        if written_off != -999 and written_off > 0:
            reasons.append({"type": "red", "text": f"{int(written_off)} loan(s) written off"})

    if ml_score is not None:
        if ml_score >= 80:
            reasons.append({"type": "green", "text": f"ML model confidence: {ml_score}% — very low risk"})
        elif ml_score >= 50:
            reasons.append({"type": "yellow", "text": f"ML model confidence: {ml_score}% — moderate risk"})
        else:
            reasons.append({"type": "red", "text": f"ML model confidence: {ml_score}% — high risk"})

    return reasons


@app.get("/admin/submissions")
def admin_submissions():
    try:
        with get_engine("submissions_db").connect() as conn:
            rows = conn.execute(text("""
                SELECT name, surname, date_of_birth, age, akb_score,
                       akb_letter_grade, decision, decision_type, user_id, submitted_at
                FROM customer_submissions
                ORDER BY submitted_at DESC
                LIMIT 200
            """)).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/submit-customer")
def submit_customer(customer: CustomerInput):
    try:
        generated_user_id = None

        if customer.customer_type == "new":
            # Check duplicate
            try:
                with get_engine("submissions_db").connect() as conn:
                    existing = conn.execute(text("""
                        SELECT name, surname, date_of_birth, id
                        FROM customer_submissions
                        WHERE LOWER(name) = LOWER(:name)
                        AND LOWER(surname) = LOWER(:surname)
                        AND date_of_birth = :dob
                        LIMIT 1
                    """), {"name": customer.name, "surname": customer.surname, "dob": customer.date_of_birth}).fetchone()
                if existing:
                    return {
                        "already_exists": True,
                        "message": "You already have an account! Your User ID is below.",
                        "existing_user_id": str(existing[3]),
                        "age": None, "akb_score": None, "akb_letter_grade": None,
                        "decision": None, "decision_type": None, "ml_score": None, "generated_user_id": None,
                    }
            except Exception as e:
                print(f"Duplicate check error: {e}")

            import uuid
            generated_user_id = customer.generated_user_id or str(uuid.uuid4())
            dob = customer.date_of_birth
            age, hard_decision = make_hard_decision(dob, customer.akb_score)

            # Step 1 — just hard rules check
            if customer.step == 1:
                if hard_decision != "PASSED":
                    return {
                        "hard_rejected": True,
                        "decision": hard_decision,
                        "decision_type": "Hard Rules",
                        "age": age,
                        "akb_score": customer.akb_score,
                        "akb_letter_grade": customer.akb_letter_grade,
                        "ml_score": None,
                        "generated_user_id": generated_user_id,
                        "reasons": build_reasons(age, customer.akb_score, hard_decision, None, None),
                        "loan_recommendation": None,
                        "fraud_flags": [],
                    }
                return {
                    "hard_rejected": False,
                    "decision": "PASSED",
                    "generated_user_id": generated_user_id,
                    "age": age,
                    "akb_score": customer.akb_score,
                    "akb_letter_grade": customer.akb_letter_grade,
                }

            # Step 2 — run XGBoost with financial inputs
            if hard_decision != "PASSED":
                final_decision = hard_decision
                decision_type = "Hard Rules"
                ml_score = None
            else:
                import numpy as np
                income = customer.monthly_income or 0
                expenses = customer.monthly_expenses or 0
                debt = customer.outstanding_debt or 0
                overdue = customer.overdue_amount or 0

                manual_features = {feat: -999 for feat in model_data["features"]}
                manual_features.update({
                    "age": age,
                    "akb_score": customer.akb_score or -999,
                    "monthly_income": income,
                    "monthly_expenses": expenses,
                    "net_income": income - expenses,
                    "income_total": income,
                    "total_outstanding_debt": debt,
                    "debt_to_income": debt / max(income, 1),
                    "total_overdue_interest": overdue,
                    "overdue_interest_to_debt": overdue / max(debt, 1) if debt > 0 else 0,
                    "has_overdue_history": 1 if customer.has_overdue else 0,
                    "has_akb_score": 1 if customer.akb_score else 0,
                    "payment_success_rate": 0 if customer.has_overdue else 1,
                    "successful_payments": 0,
                    "failed_payments": 0,
                    "total_payments": 0,
                    "loans_paid_count": 0,
                    "total_loans": 0,
                    "is_pep": 0,
                    "is_beneficial_owner": 0,
                    "is_related_to_pep": 0,
                })

                X = np.array([[manual_features.get(f, -999) for f in model_data["features"]]])
                prob = model_data["model"].predict_proba(X)[0][1]
                ml_score = round(float(prob) * 100, 1)
                final_decision = "APPROVED" if prob >= 0.5 else "REJECTED — High credit risk"
                decision_type = "XGBoost ML Model"

            fraud_flags = check_fraud(customer.name, customer.surname, customer.date_of_birth, customer.akb_score)
            loan_recommendation = recommend_loan(ml_score, customer.akb_score, customer.monthly_income) if final_decision == "APPROVED" else None

        else:
            # Existing customer — look up by user_id, run XGBoost
            if not customer.user_id:
                raise HTTPException(status_code=400, detail="User ID is required for existing customers")

            dob = None
            try:
                with get_engine("loan_users_db").connect() as conn:
                    result = conn.execute(text("""
                        SELECT q.birth_date FROM users u
                        LEFT JOIN questionnaires q ON q.user_id = u.id
                        WHERE u.id = :user_id
                    """), {"user_id": customer.user_id}).fetchone()
                if result:
                    dob = result[0]
            except:
                pass

            # If not found in DB, use provided DOB
            if dob is None:
                dob = customer.date_of_birth

            if dob is None:
                raise HTTPException(status_code=400, detail="Date of birth required — user not found in database")

            age, hard_decision = make_hard_decision(dob, customer.akb_score)

            ml_score = None
            ml_decision = None
            decision_type = "Hard Rules"

            if hard_decision != "PASSED":
                final_decision = hard_decision
            else:
                features_row = get_ml_features(customer.user_id)
                if features_row and features_row.get("total_loans", -999) != -999 and features_row.get("total_loans", 0) > 0:
                    ml_score, ml_decision = run_xgboost(features_row, customer.akb_score, age)
                    decision_type = "XGBoost ML Model"
                final_decision = ml_decision if ml_decision else "APPROVED"

        row = {
            "name":             customer.name or "N/A",
            "surname":          customer.surname or "N/A",
            "date_of_birth":    customer.date_of_birth or "N/A",
            "residency":        customer.residency or "N/A",
            "age":              age,
            "akb_score":        customer.akb_score,
            "akb_letter_grade": customer.akb_letter_grade,
            "decision":         final_decision,
            "decision_type":    decision_type,
            "ml_score":         ml_score,
            "user_id":          generated_user_id or customer.user_id,
            "submitted_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        append_to_excel(row)

        if customer.customer_type == "new":
            try:
                with get_engine("submissions_db").connect() as conn:
                    conn.execute(text("""
                        INSERT INTO customer_submissions
                            (name, surname, date_of_birth, residency, akb_score, akb_letter_grade, age, decision, user_id, submitted_at)
                        VALUES
                            (:name, :surname, :date_of_birth, :residency, :akb_score, :akb_letter_grade, :age, :decision, :user_id, :submitted_at)
                    """), row)
                    conn.commit()
            except Exception as db_err:
                print(f"DB ERROR: {db_err}")

        features_row_for_reasons = get_ml_features(customer.user_id) if customer.customer_type == "existing" and customer.user_id else None

        # Fraud detection
        fraud_flags = []
        if customer.customer_type == "new" and customer.name:
            fraud_flags = check_fraud(customer.name, customer.surname, customer.date_of_birth, customer.akb_score)

        # Loan recommendation
        income = None
        if features_row_for_reasons and isinstance(features_row_for_reasons, dict):
            income = features_row_for_reasons.get("monthly_income")
        loan_recommendation = None
        if final_decision == "APPROVED":
            loan_recommendation = recommend_loan(ml_score if ml_score else 55, customer.akb_score, income)

        return {
            "age":               age,
            "akb_score":         customer.akb_score,
            "akb_letter_grade":  customer.akb_letter_grade,
            "decision":          final_decision,
            "decision_type":     decision_type,
            "ml_score":          ml_score,
            "generated_user_id": generated_user_id,
            "reasons":           build_reasons(age, customer.akb_score, final_decision, features_row_for_reasons, ml_score),
            "loan_recommendation": loan_recommendation,
            "fraud_flags":       fraud_flags,
        }

    except HTTPException:
        raise
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


# ── Loan Amount Recommender ───────────────────────────────────
def recommend_loan(ml_score, akb_score, monthly_income=None):
    if ml_score is None or akb_score is None:
        return None

    # Base amount by ML score
    if ml_score >= 90:
        base = 10000
    elif ml_score >= 80:
        base = 7000
    elif ml_score >= 70:
        base = 5000
    elif ml_score >= 60:
        base = 3000
    elif ml_score >= 50:
        base = 1500
    else:
        return None

    # AKB score multiplier
    if akb_score >= 750:
        multiplier = 1.3
    elif akb_score >= 600:
        multiplier = 1.1
    elif akb_score >= 400:
        multiplier = 1.0
    else:
        multiplier = 0.8

    # Income cap — max 3x monthly income
    recommended = round(base * multiplier / 100) * 100
    if monthly_income and monthly_income > 0:
        income_cap = monthly_income * 3
        recommended = min(recommended, income_cap)

    # Interest rate by risk
    if ml_score >= 80:
        rate = 12
    elif ml_score >= 65:
        rate = 18
    else:
        rate = 24

    return {
        "max_amount": int(recommended),
        "interest_rate": rate,
        "term_months": 12 if recommended <= 3000 else 24,
        "monthly_payment": round(recommended * (rate/100/12) / (1 - (1 + rate/100/12)**(-12 if recommended <= 3000 else -24)), 2)
    }


# ── Fraud Detection ───────────────────────────────────────────
def check_fraud(name, surname, dob, akb_score):
    flags = []
    try:
        with get_engine("submissions_db").connect() as conn:
            # Same person different AKB scores today
            rows = conn.execute(text("""
                SELECT akb_score, submitted_at FROM customer_submissions
                WHERE LOWER(name) = LOWER(:name)
                AND LOWER(surname) = LOWER(:surname)
                AND date_of_birth = :dob
                AND submitted_at > :today
                ORDER BY submitted_at DESC
            """), {
                "name": name or "",
                "surname": surname or "",
                "dob": dob or "",
                "today": (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            }).fetchall()

            if len(rows) >= 3:
                flags.append("Multiple submissions in 24 hours")

            scores = [r[0] for r in rows if r[0] is not None]
            if akb_score and scores:
                if any(abs(float(s) - float(akb_score)) > 100 for s in scores):
                    flags.append("AKB score varies significantly across submissions")

    except Exception as e:
        print(f"Fraud check error: {e}")

    return flags


# ── Admin Analytics ───────────────────────────────────────────
@app.get("/admin/analytics")
def admin_analytics():
    try:
        with get_engine("submissions_db").connect() as conn:

            # Daily submissions last 14 days
            daily = conn.execute(text("""
                SELECT
                    DATE(submitted_at::timestamp) AS day,
                    COUNT(*) AS total,
                    SUM(CASE WHEN decision = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
                    SUM(CASE WHEN decision != 'APPROVED' THEN 1 ELSE 0 END) AS rejected
                FROM customer_submissions
                WHERE submitted_at::timestamp > NOW() - INTERVAL '14 days'
                GROUP BY DATE(submitted_at::timestamp)
                ORDER BY day ASC
            """)).fetchall()

            # Rejection reasons breakdown
            reasons = conn.execute(text("""
                SELECT decision, COUNT(*) AS cnt
                FROM customer_submissions
                WHERE decision != 'APPROVED'
                GROUP BY decision
                ORDER BY cnt DESC
            """)).fetchall()

            # AKB score distribution
            akb_dist = conn.execute(text("""
                SELECT
                    CASE
                        WHEN akb_score < 200 THEN 'E (0-199)'
                        WHEN akb_score < 600 THEN 'D (200-599)'
                        WHEN akb_score < 750 THEN 'C (600-749)'
                        WHEN akb_score < 825 THEN 'B (750-824)'
                        ELSE 'A (825+)'
                    END AS grade_range,
                    COUNT(*) AS cnt
                FROM customer_submissions
                WHERE akb_score IS NOT NULL
                GROUP BY grade_range
                ORDER BY MIN(akb_score)
            """)).fetchall()

            # Overall stats
            stats = conn.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN decision = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
                    SUM(CASE WHEN decision != 'APPROVED' THEN 1 ELSE 0 END) AS rejected,
                    ROUND(AVG(akb_score)::numeric, 1) AS avg_akb,
                    ROUND(AVG(age)::numeric, 1) AS avg_age
                FROM customer_submissions
            """)).fetchone()

        return {
            "daily": [{"day": str(r[0]), "total": r[1], "approved": r[2], "rejected": r[3]} for r in daily],
            "rejection_reasons": [{"reason": r[0], "count": r[1]} for r in reasons],
            "akb_distribution": [{"grade": r[0], "count": r[1]} for r in akb_dist],
            "stats": dict(stats._mapping) if stats else {}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Risk Heatmap Data ─────────────────────────────────────────
@app.get("/admin/heatmap")
def admin_heatmap():
    try:
        with get_engine("submissions_db").connect() as conn:
            rows = conn.execute(text("""
                SELECT akb_score, age, decision, name, surname
                FROM customer_submissions
                WHERE akb_score IS NOT NULL AND age IS NOT NULL
                ORDER BY submitted_at DESC
                LIMIT 500
            """)).fetchall()
        return [{"akb_score": r[0], "age": r[1], "decision": r[2], "name": f"{r[3] or ''} {r[4] or ''}".strip()} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))