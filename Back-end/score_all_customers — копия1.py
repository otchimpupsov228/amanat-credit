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

print("\n📂 Pulling all customers from amanat_ml_db...")
df = pd.read_sql("SELECT * FROM customer_features", get_engine("amanat_ml_db"))
print(f"✅ {len(df)} customers loaded")

print("\n🤖 Running XGBoost on all customers...")
today = date.today()

def calc_age(dob):
    if pd.isnull(dob):
        return None
    dob = pd.to_datetime(dob).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

X = df[features].fillna(-999)
probs = model.predict_proba(X)[:, 1]
predictions = model.predict(X)

df["ml_probability"] = (probs * 100).round(1)
df["ml_decision"] = ["APPROVED" if p == 1 else "REJECTED — High credit risk" for p in predictions]

def hard_rules(row):
    age = calc_age(row.get("birth_date")) if "birth_date" in row else None
    akb = row.get("akb_score")
    if age is not None and age < 18:
        return "REJECTED — Age is below 18", age
    if akb is None or (not pd.isnull(akb) and float(akb) < 300):
        return "REJECTED — AKB Score too low", age
    return None, age

results = []
for _, row in df.iterrows():
    hard_decision, age = hard_rules(row)
    if hard_decision:
        final_decision = hard_decision
        decision_type = "Hard Rules"
        ml_prob = None
    else:
        final_decision = row["ml_decision"]
        decision_type = "XGBoost ML Model"
        ml_prob = row["ml_probability"]

    results.append({
        "user_id":          row["user_id"],
        "age":              age,
        "akb_score":        row.get("akb_score"),
        "akb_grade":        row.get("akb_grade"),
        "loans_paid_count": row.get("loans_paid_count"),
        "total_loans":      row.get("total_loans"),
        "successful_payments": row.get("successful_payments"),
        "failed_payments":  row.get("failed_payments"),
        "payment_success_rate": row.get("payment_success_rate"),
        "total_overdue_interest": row.get("total_overdue_interest"),
        "borrower_label":   row.get("borrower_label"),
        "ml_probability":   ml_prob,
        "decision":         final_decision,
        "decision_type":    decision_type,
        "created_at":       pd.Timestamp.now()
    })

results_df = pd.DataFrame(results)

approved = results_df[results_df["decision"] == "APPROVED"]
rejected = results_df[results_df["decision"] != "APPROVED"]

print(f"\n📊 Results:")
print(f"  ✅ Approved: {len(approved):,}")
print(f"  ❌ Rejected: {len(rejected):,}")
print(f"  Total:      {len(results_df):,}")

print("\n💾 Saving to submissions_db.customer_decisions...")
results_df.to_sql(
    "customer_decisions",
    get_engine("submissions_db"),
    if_exists="replace",
    index=False,
    chunksize=500
)

with get_engine("submissions_db").connect() as conn:
    count = conn.execute(text("SELECT COUNT(*) FROM customer_decisions")).scalar()

print(f"✅ {count:,} decisions saved to submissions_db → customer_decisions!")
print("\nNow run in pgAdmin (submissions_db):")
print("  SELECT * FROM customer_decisions ORDER BY ml_probability DESC LIMIT 50;")
print("  SELECT * FROM customer_decisions WHERE decision = 'APPROVED' ORDER BY ml_probability DESC;")
print("  SELECT * FROM customer_decisions WHERE decision != 'APPROVED' ORDER BY ml_probability ASC;")
