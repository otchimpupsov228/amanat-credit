import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date

PG_USER = "huseynmajidov"
PG_HOST = "localhost"
PG_PORT = "5432"

def get_engine(dbname):
    return create_engine(f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}")

print("📂 Pulling and merging data from all databases...")

users_df = pd.read_sql("""
    SELECT
        u.id AS user_id, u.loans_paid, u.locale,
        q.birth_date, q.monthly_income, q.monthly_expenses,
        q.is_pep, q.is_beneficial_owner, q.is_related_to_pep
    FROM users u
    LEFT JOIN questionnaires q ON q.user_id = u.id
""", get_engine("loan_users_db"))

loans_df = pd.read_sql("""
    SELECT user_id,
        COUNT(*) AS total_loans,
        SUM(amount) AS total_amount_borrowed,
        AVG(term) AS avg_loan_term,
        SUM(CASE WHEN tag = 'paid' THEN 1 ELSE 0 END) AS loans_paid_count,
        SUM(CASE WHEN tag = 'overdue' THEN 1 ELSE 0 END) AS loans_overdue
    FROM loans GROUP BY user_id
""", get_engine("loans_db"))

loan_states_df = pd.read_sql("""
    SELECT l.user_id,
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
        AVG(amount) AS avg_payment_amount
    FROM payments GROUP BY user_id
""", get_engine("payments_db"))

akb_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id)
        user_id,
        response_score_point AS akb_score,
        response_score_response AS akb_grade,
        COUNT(*) OVER (PARTITION BY user_id) AS akb_check_count
    FROM akb_scores WHERE is_successful = TRUE
    ORDER BY user_id, timestamp DESC
""", get_engine("akb_score_db"))

akb_hist_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id)
        user_id,
        liab_count,
        liab_outstanding_debt_main_sum AS total_outstanding_debt,
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

df["age"]                      = df["birth_date"].apply(calc_age)
df["payment_success_rate"]     = df["successful_payments"] / df["total_payments"].replace(0, 1)
df["overdue_interest_to_debt"] = df["total_overdue_interest"].fillna(0) / df["total_debt_accumulated"].replace(0, 1)
df["borrower_label"]           = "unknown"
df.loc[(df["loans_paid"].fillna(0) > 0) & (df["loans_overdue"].fillna(0) == 0), "borrower_label"] = "good"
df.loc[df["loans_overdue"].fillna(0) > 0, "borrower_label"] = "bad"
df["created_at"]               = pd.Timestamp.now()

KEEP_COLUMNS = [
    "user_id",
    "age",
    "loans_paid_count",
    "successful_payments",
    "total_overdue_interest",
    "total_loans",
    "overdue_interest_to_debt",
    "total_payments",
    "total_amount_borrowed",
    "payment_success_rate",
    "avg_payment_amount",
    "akb_check_count",
    "total_debt_accumulated",
    "avg_loan_term",
    "total_outstanding_debt",
    "liab_count",
    "failed_payments",
    "akb_score",
    "akb_grade",
    "credit_balance",
    "borrower_label",
    "created_at",
]

df = df[KEEP_COLUMNS]
print(f"  ✅ {len(df)} rows, {len(df.columns)} columns (only important features)")

print("💾 Saving to amanat_ml_db.customer_features...")
ml_engine = get_engine("amanat_ml_db")
df.to_sql("customer_features", ml_engine, if_exists="replace", index=False, chunksize=500)

with ml_engine.connect() as conn:
    count = conn.execute(text("SELECT COUNT(*) FROM customer_features")).scalar()

print(f"  ✅ {count:,} rows saved to amanat_ml_db → customer_features!")
print("\nNow run in pgAdmin:")
print("  SELECT * FROM customer_features LIMIT 10;")
