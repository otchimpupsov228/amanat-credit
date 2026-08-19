import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import date
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
import matplotlib.pyplot as plt
import pickle
import warnings
warnings.filterwarnings("ignore")

PG_USER = "huseynmajidov"
PG_HOST = "localhost"
PG_PORT = "5432"

def get_engine(dbname):
    return create_engine(f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}")

print("=" * 60)
print("  Amanat.az — XGBoost Credit Risk Model v2")
print("=" * 60)

print("\n📂 Pulling users from loan_users_db...")
users_engine = get_engine("loan_users_db")
users_df = pd.read_sql("""
    SELECT
        u.id                        AS user_id,
        u.loans_paid,
        u.locale,
        q.sex,
        q.birth_date,
        q.monthly_income,
        q.monthly_expenses,
        q.additional_income,
        q.marital_status,
        q.citizenship,
        q.registration_region,
        q.job_title,
        q.is_pep,
        q.is_beneficial_owner,
        q.is_related_to_pep
    FROM users u
    LEFT JOIN questionnaires q ON q.user_id = u.id
""", users_engine)
print(f"  ✅ {len(users_df)} users loaded")

print("\n📂 Pulling loans from loans_db...")
loans_engine = get_engine("loans_db")

loans_df = pd.read_sql("""
    SELECT
        user_id,
        COUNT(*)                                                        AS total_loans,
        SUM(amount)                                                     AS total_amount_borrowed,
        AVG(amount)                                                     AS avg_loan_amount,
        AVG(term)                                                       AS avg_loan_term,
        SUM(CASE WHEN tag = 'paid' THEN 1 ELSE 0 END)                  AS loans_paid_count,
        SUM(CASE WHEN tag = 'overdue' THEN 1 ELSE 0 END)               AS loans_overdue,
        SUM(CASE WHEN tag = 'active' THEN 1 ELSE 0 END)                AS loans_active,
        MAX(amount)                                                     AS max_loan_amount,
        MIN(amount)                                                     AS min_loan_amount,
        EXTRACT(EPOCH FROM (MAX(created) - MIN(created))) / 86400       AS days_between_first_last_loan
    FROM loans
    GROUP BY user_id
""", loans_engine)

loan_states_df = pd.read_sql("""
    SELECT
        l.user_id,
        SUM(CASE WHEN ls.transaction_type = 'payment'
            AND EXTRACT(DAY FROM (ls.created - ls.target_date)) BETWEEN 1 AND 30
            THEN 1 ELSE 0 END)                                          AS delayed_payments,
        SUM(CASE WHEN ls.transaction_type = 'payment'
            AND EXTRACT(DAY FROM (ls.created - ls.target_date)) > 30
            THEN 1 ELSE 0 END)                                          AS failed_payments_30plus,
        AVG(CASE WHEN ls.transaction_type = 'payment'
            AND ls.created > ls.target_date
            THEN EXTRACT(DAY FROM (ls.created - ls.target_date))
            ELSE 0 END)                                                 AS avg_delay_days,
        MAX(CASE WHEN ls.transaction_type = 'payment'
            AND ls.created > ls.target_date
            THEN EXTRACT(DAY FROM (ls.created - ls.target_date))
            ELSE 0 END)                                                 AS max_delay_days,
        SUM(ls.overdue_interest)                                        AS total_overdue_interest,
        SUM(ls.debt)                                                    AS total_debt_accumulated
    FROM loan_states ls
    JOIN loans l ON l.id = ls.loan_id
    GROUP BY l.user_id
""", loans_engine)
print(f"  ✅ {len(loans_df)} loan records, {len(loan_states_df)} loan state records loaded")

print("\n📂 Pulling payments from payments_db...")
payments_engine = get_engine("payments_db")
payments_df = pd.read_sql("""
    SELECT
        user_id,
        COUNT(*)                                                        AS total_payments,
        SUM(amount)                                                     AS total_paid,
        SUM(CASE WHEN is_successful = TRUE THEN 1 ELSE 0 END)          AS successful_payments,
        SUM(CASE WHEN is_successful = FALSE THEN 1 ELSE 0 END)         AS failed_payments,
        AVG(amount)                                                     AS avg_payment_amount,
        MAX(amount)                                                     AS max_payment_amount,
        COUNT(DISTINCT card_id)                                         AS num_cards_used
    FROM payments
    GROUP BY user_id
""", payments_engine)
print(f"  ✅ {len(payments_df)} payment records loaded")

print("\n📂 Pulling AKB scores from akb_score_db...")
akb_engine = get_engine("akb_score_db")
akb_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id)
        user_id,
        response_score_point                                AS akb_score,
        response_score_response                             AS akb_grade,
        response_score_calculated                           AS akb_calculated,
        response_score_exclusion                            AS akb_exclusion,
        response_borrower_status                            AS borrower_status,
        response_borrower_participant_of_patriotic_war      AS is_war_participant,
        COUNT(*) OVER (PARTITION BY user_id)               AS akb_check_count
    FROM akb_scores
    WHERE is_successful = TRUE
    ORDER BY user_id, timestamp DESC
""", akb_engine)
print(f"  ✅ {len(akb_df)} AKB score records loaded")

print("\n📂 Pulling AKB history from akb_history_db...")
akb_hist_engine = get_engine("akb_history_db")
akb_hist_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id)
        user_id,
        liab_count,
        liab_outstanding_debt_main_sum                      AS total_outstanding_debt,
        liab_outstanding_debt_interest_sum                  AS total_outstanding_interest,
        liab_days_main_overdue_max                          AS max_days_overdue,
        liab_days_main_overdue_sum                          AS total_days_overdue,
        response_score_point                                AS history_score,
        response_balance                                    AS credit_balance
    FROM akb_history_summary
    ORDER BY user_id, timestamp DESC
""", akb_hist_engine)
print(f"  ✅ {len(akb_hist_df)} AKB history records loaded")

print("\n🔗 Merging all data...")
df = users_df.copy()
df = df.merge(loans_df,       on="user_id", how="left")
df = df.merge(loan_states_df, on="user_id", how="left")
df = df.merge(payments_df,    on="user_id", how="left")
df = df.merge(akb_df,         on="user_id", how="left")
df = df.merge(akb_hist_df,    on="user_id", how="left")
print(f"  ✅ Final dataset: {len(df)} rows × {len(df.columns)} columns")

print("\n🔧 Engineering features...")

today = date.today()
def calc_age(dob):
    if pd.isnull(dob):
        return None
    dob = pd.to_datetime(dob).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

df["age"] = df["birth_date"].apply(calc_age)
df["net_income"] = df["monthly_income"].fillna(0) - df["monthly_expenses"].fillna(0)
df["income_total"] = df["monthly_income"].fillna(0) + df["additional_income"].fillna(0)
df["payment_success_rate"] = df["successful_payments"] / df["total_payments"].replace(0, 1)
df["delayed_payment_rate"] = df["delayed_payments"].fillna(0) / df["total_payments"].replace(0, 1)
df["failed_payment_30plus_rate"] = df["failed_payments_30plus"].fillna(0) / df["total_payments"].replace(0, 1)
df["debt_to_income"] = df["total_outstanding_debt"].fillna(0) / df["income_total"].replace(0, 1)
df["loan_amount_to_income"] = df["avg_loan_amount"].fillna(0) / df["income_total"].replace(0, 1)
df["overdue_interest_to_debt"] = df["total_overdue_interest"].fillna(0) / df["total_debt_accumulated"].replace(0, 1)
df["is_repeat_borrower"] = (df["total_loans"].fillna(0) > 1).astype(int)
df["has_akb_score"] = df["akb_score"].notna().astype(int)
df["has_overdue_history"] = (df["max_days_overdue"].fillna(0) > 0).astype(int)
df["sex_encoded"] = df["sex"].map({"male": 1, "female": 0})
df["is_pep"] = df["is_pep"].fillna(False).astype(int)
df["is_beneficial_owner"] = df["is_beneficial_owner"].fillna(False).astype(int)
df["is_related_to_pep"] = df["is_related_to_pep"].fillna(False).astype(int)
df["marital_status"] = df["marital_status"].fillna(-1).astype(int)

df["target"] = (
    (df["loans_paid"].fillna(0) > 0) &
    (df["loans_overdue"].fillna(0) == 0) &
    (df["failed_payments_30plus"].fillna(0) == 0)
).astype(int)

FEATURES = [
    "age", "sex_encoded", "marital_status",
    "monthly_income", "monthly_expenses", "additional_income",
    "net_income", "income_total",
    "akb_score", "akb_calculated", "akb_exclusion", "akb_check_count", "has_akb_score",
    "history_score",
    "total_loans", "total_amount_borrowed", "avg_loan_amount", "avg_loan_term",
    "max_loan_amount", "loans_paid_count", "loans_overdue", "loans_active",
    "days_between_first_last_loan",
    "total_payments", "successful_payments", "failed_payments",
    "avg_payment_amount", "num_cards_used", "payment_success_rate",
    "delayed_payments", "delayed_payment_rate",
    "failed_payments_30plus", "failed_payment_30plus_rate",
    "avg_delay_days", "max_delay_days",
    "total_overdue_interest", "total_debt_accumulated",
    "liab_count", "total_outstanding_debt", "total_outstanding_interest",
    "max_days_overdue", "total_days_overdue", "credit_balance",
    "debt_to_income", "loan_amount_to_income", "overdue_interest_to_debt",
    "is_repeat_borrower", "has_overdue_history",
    "is_pep", "is_beneficial_owner", "is_related_to_pep",
]

df_model = df[FEATURES + ["target"]].copy()
df_model = df_model.dropna(subset=["target"])
df_model[FEATURES] = df_model[FEATURES].fillna(-999)

X = df_model[FEATURES]
y = df_model["target"]

print(f"  ✅ Features ready: {len(FEATURES)} features, {len(X)} samples")
print(f"  Target distribution: {y.value_counts().to_dict()}")

print("\n🤖 Training XGBoost model...")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

model = xgb.XGBClassifier(
    n_estimators=300,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    gamma=0.1,
    use_label_encoder=False,
    eval_metric="logloss",
    random_state=42
)

model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

print("\n📊 Model Performance:")
print(classification_report(y_test, y_pred, target_names=["Bad Borrower", "Good Borrower"]))
print(f"  ROC-AUC Score: {roc_auc_score(y_test, y_prob):.4f}")

print("\n📈 Top 20 Most Important Features:")
importance = pd.DataFrame({
    "feature": FEATURES,
    "importance": model.feature_importances_
}).sort_values("importance", ascending=False)
print(importance.head(20).to_string(index=False))

plt.figure(figsize=(12, 9))
top20 = importance.head(20)
colors = ["#2563eb" if i < 5 else "#93c5fd" for i in range(len(top20))]
plt.barh(top20["feature"][::-1], top20["importance"][::-1], color=colors[::-1])
plt.xlabel("Importance Score")
plt.title("Amanat.az — XGBoost Feature Importance v2")
plt.tight_layout()
plt.savefig("feature_importance_v2.png", dpi=150)
print("\n  ✅ Feature importance chart saved → feature_importance_v2.png")

with open("amanat_model.pkl", "wb") as f:
    pickle.dump({"model": model, "features": FEATURES}, f)
print("  ✅ Model saved → amanat_model.pkl")

print("\n📋 Feature Groups Analysis:")
payment_features = ["successful_payments", "failed_payments", "payment_success_rate",
                    "delayed_payments", "delayed_payment_rate",
                    "failed_payments_30plus", "failed_payment_30plus_rate",
                    "avg_delay_days", "max_delay_days"]
credit_features = ["akb_score", "akb_calculated", "history_score", "has_akb_score",
                   "liab_count", "total_outstanding_debt", "max_days_overdue"]
income_features = ["monthly_income", "monthly_expenses", "net_income",
                   "income_total", "debt_to_income", "loan_amount_to_income"]
loan_features = ["total_loans", "loans_paid_count", "loans_overdue",
                 "total_amount_borrowed", "avg_loan_amount"]

for group_name, features in [
    ("💳 Payment Behavior", payment_features),
    ("📊 Credit History (AKB)", credit_features),
    ("💰 Income & Debt", income_features),
    ("🏦 Loan History", loan_features),
]:
    group_imp = importance[importance["feature"].isin(features)]["importance"].sum()
    print(f"  {group_name}: {group_imp:.1%}")

print("\n" + "=" * 60)
print("  Training complete!")
print("=" * 60)
