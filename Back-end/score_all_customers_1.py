import pandas as pd
import pickle
import numpy as np
from sqlalchemy import create_engine, text
from datetime import date

PG_USER = "huseynmajidov"
PG_HOST = "localhost"
PG_PORT = "5432"

def get_engine(dbname):
    return create_engine(f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}")

print("Loading XGBoost model...")
with open("amanat_model.pkl", "rb") as f:
    model_data = pickle.load(f)
model = model_data["model"]
features = model_data["features"]
print(f"✅ Model loaded with {len(features)} features")

print("\n📂 Pulling all data from databases...")

users_df = pd.read_sql("""
    SELECT u.id AS user_id, u.loans_paid, u.locale,
        q.sex, q.birth_date, q.monthly_income, q.monthly_expenses,
        q.additional_income, q.marital_status, q.is_pep,
        q.is_beneficial_owner, q.is_related_to_pep
    FROM users u
    LEFT JOIN questionnaires q ON q.user_id = u.id
""", get_engine("loan_users_db"))

loans_df = pd.read_sql("""
    SELECT user_id,
        COUNT(*) AS total_loans,
        SUM(amount) AS total_amount_borrowed,
        AVG(amount) AS avg_loan_amount,
        AVG(term) AS avg_loan_term,
        MAX(amount) AS max_loan_amount,
        SUM(CASE WHEN tag = 'paid' THEN 1 ELSE 0 END) AS loans_paid_count,
        SUM(CASE WHEN tag = 'overdue' THEN 1 ELSE 0 END) AS loans_overdue,
        SUM(CASE WHEN tag = 'active' THEN 1 ELSE 0 END) AS loans_active,
        EXTRACT(EPOCH FROM (MAX(created) - MIN(created))) / 86400 AS days_between_first_last_loan
    FROM loans GROUP BY user_id
""", get_engine("loans_db"))

loan_states_df = pd.read_sql("""
    SELECT l.user_id,
        SUM(CASE WHEN ls.transaction_type = 'payment'
            AND EXTRACT(DAY FROM (ls.created - ls.target_date)) BETWEEN 1 AND 30
            THEN 1 ELSE 0 END) AS delayed_payments,
        SUM(CASE WHEN ls.transaction_type = 'payment'
            AND EXTRACT(DAY FROM (ls.created - ls.target_date)) > 30
            THEN 1 ELSE 0 END) AS failed_payments_30plus,
        AVG(CASE WHEN ls.transaction_type = 'payment' AND ls.created > ls.target_date
            THEN EXTRACT(DAY FROM (ls.created - ls.target_date)) ELSE 0 END) AS avg_delay_days,
        MAX(CASE WHEN ls.transaction_type = 'payment' AND ls.created > ls.target_date
            THEN EXTRACT(DAY FROM (ls.created - ls.target_date)) ELSE 0 END) AS max_delay_days,
        SUM(ls.overdue_interest) AS total_overdue_interest,
        SUM(ls.debt) AS total_debt_accumulated
    FROM loan_states ls
    JOIN loans l ON l.id = ls.loan_id
    GROUP BY l.user_id
""", get_engine("loans_db"))

payments_df = pd.read_sql("""
    SELECT user_id,
        COUNT(*) AS total_payments,
        SUM(CASE WHEN is_successful = TRUE THEN 1 ELSE 0 END) AS successful_payments,
        SUM(CASE WHEN is_successful = FALSE THEN 1 ELSE 0 END) AS failed_payments,
        AVG(amount) AS avg_payment_amount,
        COUNT(DISTINCT card_id) AS num_cards_used
    FROM payments GROUP BY user_id
""", get_engine("payments_db"))

akb_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id)
        user_id, response_score_point AS akb_score,
        response_score_response AS akb_grade,
        response_score_calculated AS akb_calculated,
        response_score_exclusion AS akb_exclusion,
        COUNT(*) OVER (PARTITION BY user_id) AS akb_check_count
    FROM akb_scores WHERE is_successful = TRUE
    ORDER BY user_id, timestamp DESC
""", get_engine("akb_score_db"))

akb_hist_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id)
        user_id, liab_count,
        liab_outstanding_debt_main_sum AS total_outstanding_debt,
        liab_outstanding_debt_interest_sum AS total_outstanding_interest,
        liab_days_main_overdue_max AS max_days_overdue,
        liab_days_main_overdue_sum AS total_days_overdue,
        response_score_point AS history_score,
        response_balance AS credit_balance
    FROM akb_history_summary
    ORDER BY user_id, timestamp DESC
""", get_engine("akb_history_db"))

print("🔗 Merging...")
df = users_df.copy()
df = df.merge(loans_df,       on="user_id", how="left")
df = df.merge(loan_states_df, on="user_id", how="left")
df = df.merge(payments_df,    on="user_id", how="left")
df = df.merge(akb_df,         on="user_id", how="left")
df = df.merge(akb_hist_df,    on="user_id", how="left")

print("🔧 Engineering features...")
today = date.today()
def calc_age(dob):
    if pd.isnull(dob):
        return None
    dob = pd.to_datetime(dob).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

df["age"]                       = df["birth_date"].apply(calc_age)
df["net_income"]                = df["monthly_income"].fillna(0) - df["monthly_expenses"].fillna(0)
df["income_total"]              = df["monthly_income"].fillna(0) + df["additional_income"].fillna(0)
df["payment_success_rate"]      = df["successful_payments"] / df["total_payments"].replace(0, 1)
df["delayed_payment_rate"]      = df["delayed_payments"].fillna(0) / df["total_payments"].replace(0, 1)
df["failed_payment_30plus_rate"]= df["failed_payments_30plus"].fillna(0) / df["total_payments"].replace(0, 1)
df["debt_to_income"]            = df["total_outstanding_debt"].fillna(0) / df["income_total"].replace(0, 1)
df["loan_amount_to_income"]     = df["avg_loan_amount"].fillna(0) / df["income_total"].replace(0, 1)
df["overdue_interest_to_debt"]  = df["total_overdue_interest"].fillna(0) / df["total_debt_accumulated"].replace(0, 1)
df["is_repeat_borrower"]        = (df["total_loans"].fillna(0) > 1).astype(int)
df["has_akb_score"]             = df["akb_score"].notna().astype(int)
df["has_overdue_history"]       = (df["max_days_overdue"].fillna(0) > 0).astype(int)
df["sex_encoded"]               = df["sex"].map({"male": 1, "female": 0})
df["is_pep"]                    = df["is_pep"].fillna(False).astype(int)
df["is_beneficial_owner"]       = df["is_beneficial_owner"].fillna(False).astype(int)
df["is_related_to_pep"]         = df["is_related_to_pep"].fillna(False).astype(int)
df["marital_status"]            = df["marital_status"].fillna(-1).astype(int)

print(f"✅ {len(df)} customers ready")

print("\n🤖 Running XGBoost on all customers...")
X = df[features].fillna(-999)
probs = model.predict_proba(X)[:, 1]
predictions = model.predict(X)

df["ml_probability"] = (probs * 100).round(1)
df["ml_prediction"]  = ["APPROVED" if p == 1 else "REJECTED — High credit risk" for p in predictions]

results = []
for _, row in df.iterrows():
    age = row["age"]
    akb = row["akb_score"]

    if age is not None and age < 18:
        final_decision = "REJECTED — Age is below 18"
        decision_type = "Hard Rules"
        ml_prob = None
    elif pd.isnull(akb) or float(akb) < 300:
        final_decision = "REJECTED — AKB Score too low"
        decision_type = "Hard Rules"
        ml_prob = None
    else:
        final_decision = row["ml_prediction"]
        decision_type = "XGBoost ML Model"
        ml_prob = row["ml_probability"]

    results.append({
        "user_id":              row["user_id"],
        "age":                  age,
        "akb_score":            row.get("akb_score"),
        "akb_grade":            row.get("akb_grade"),
        "loans_paid_count":     row.get("loans_paid_count"),
        "total_loans":          row.get("total_loans"),
        "successful_payments":  row.get("successful_payments"),
        "failed_payments":      row.get("failed_payments"),
        "payment_success_rate": row.get("payment_success_rate"),
        "total_overdue_interest": row.get("total_overdue_interest"),
        "ml_probability":       ml_prob,
        "decision":             final_decision,
        "decision_type":        decision_type,
        "created_at":           pd.Timestamp.now()
    })

results_df = pd.DataFrame(results)
approved = results_df[results_df["decision"] == "APPROVED"]
rejected = results_df[results_df["decision"] != "APPROVED"]

print(f"\n📊 Results:")
print(f"  ✅ Approved: {len(approved):,}")
print(f"  ❌ Rejected: {len(rejected):,}")
print(f"  Total:      {len(results_df):,}")

print("\n💾 Saving to submissions_db.customer_decisions...")
results_df.to_sql("customer_decisions", get_engine("submissions_db"), if_exists="replace", index=False, chunksize=500)

with get_engine("submissions_db").connect() as conn:
    count = conn.execute(text("SELECT COUNT(*) FROM customer_decisions")).scalar()

print(f"✅ {count:,} decisions saved to submissions_db → customer_decisions!")
print("\nRun in pgAdmin (submissions_db):")
print("  SELECT * FROM customer_decisions ORDER BY ml_probability DESC LIMIT 50;")
