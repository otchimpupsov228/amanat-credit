"""
Evaluate the saved XGBoost credit-risk model (amanat_model.pkl).

Rebuilds the exact dataset, features, and target used in train_model_2.py,
reproduces the same stratified train/test split (random_state=42, test_size=0.2),
loads the *already-trained* model from the pickle, and reports
precision, recall, and accuracy on the held-out test set.
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import date
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, accuracy_score, f1_score,
    confusion_matrix, classification_report, roc_auc_score,
)
import pickle
import warnings
warnings.filterwarnings("ignore")

PG_USER = "huseynmajidov"
PG_HOST = "localhost"
PG_PORT = "5432"

def get_engine(dbname):
    return create_engine(f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}")

# ── 1. Pull the same data as training ─────────────────────────
users_df = pd.read_sql("""
    SELECT u.id AS user_id, u.loans_paid, u.locale,
        q.sex, q.birth_date, q.monthly_income, q.monthly_expenses,
        q.additional_income, q.marital_status, q.citizenship,
        q.registration_region, q.is_pep, q.is_beneficial_owner, q.is_related_to_pep
    FROM users u LEFT JOIN questionnaires q ON q.user_id = u.id
""", get_engine("loan_users_db"))

loans_engine = get_engine("loans_db")
loans_df = pd.read_sql("""
    SELECT user_id, COUNT(*) AS total_loans, SUM(amount) AS total_amount_borrowed,
        AVG(amount) AS avg_loan_amount, AVG(term) AS avg_loan_term,
        MAX(amount) AS max_loan_amount, MIN(amount) AS min_loan_amount,
        SUM(CASE WHEN tag='paid' THEN 1 ELSE 0 END) AS loans_paid_count,
        SUM(CASE WHEN tag='overdue' THEN 1 ELSE 0 END) AS loans_overdue,
        SUM(CASE WHEN tag='active' THEN 1 ELSE 0 END) AS loans_active,
        SUM(CASE WHEN tag='written_off' THEN 1 ELSE 0 END) AS loans_written_off,
        EXTRACT(EPOCH FROM (MAX(created)-MIN(created)))/86400 AS days_between_first_last_loan
    FROM loans GROUP BY user_id
""", loans_engine)
loan_actions_df = pd.read_sql("""
    SELECT user_id,
        SUM(CASE WHEN tag='approved' THEN 1 ELSE 0 END) AS times_approved,
        SUM(CASE WHEN tag='in_review' THEN 1 ELSE 0 END) AS times_in_review,
        SUM(CASE WHEN tag='paid' THEN 1 ELSE 0 END) AS times_paid_action,
        SUM(CASE WHEN tag='written_off' THEN 1 ELSE 0 END) AS times_written_off,
        SUM(CASE WHEN tag='active' THEN 1 ELSE 0 END) AS times_active
    FROM loan_actions GROUP BY user_id
""", loans_engine)
loan_states_df = pd.read_sql("""
    SELECT l.user_id,
        SUM(CASE WHEN ls.transaction_type='payment' AND EXTRACT(DAY FROM (ls.created-ls.target_date)) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS delayed_payments,
        SUM(CASE WHEN ls.transaction_type='payment' AND EXTRACT(DAY FROM (ls.created-ls.target_date)) > 30 THEN 1 ELSE 0 END) AS failed_payments_30plus,
        AVG(CASE WHEN ls.transaction_type='payment' AND ls.created>ls.target_date THEN EXTRACT(DAY FROM (ls.created-ls.target_date)) ELSE 0 END) AS avg_delay_days,
        MAX(CASE WHEN ls.transaction_type='payment' AND ls.created>ls.target_date THEN EXTRACT(DAY FROM (ls.created-ls.target_date)) ELSE 0 END) AS max_delay_days,
        SUM(ls.overdue_interest) AS total_overdue_interest, SUM(ls.debt) AS total_debt_accumulated
    FROM loan_states ls JOIN loans l ON l.id=ls.loan_id GROUP BY l.user_id
""", loans_engine)

payments_engine = get_engine("payments_db")
payments_df = pd.read_sql("""
    SELECT user_id, COUNT(*) AS total_payments, SUM(amount) AS total_paid,
        SUM(CASE WHEN is_successful=TRUE THEN 1 ELSE 0 END) AS successful_payments,
        SUM(CASE WHEN is_successful=FALSE THEN 1 ELSE 0 END) AS failed_payments,
        AVG(amount) AS avg_payment_amount, MAX(amount) AS max_payment_amount,
        COUNT(DISTINCT card_id) AS num_cards_used
    FROM payments GROUP BY user_id
""", payments_engine)
cards_df = pd.read_sql("""
    SELECT user_id, COUNT(*) AS total_cards,
        SUM(CASE WHEN is_verified=TRUE THEN 1 ELSE 0 END) AS verified_cards,
        SUM(CASE WHEN is_main=TRUE THEN 1 ELSE 0 END) AS has_main_card,
        SUM(CASE WHEN is_for_disbursement=TRUE THEN 1 ELSE 0 END) AS has_disbursement_card,
        SUM(CASE WHEN deleted IS NOT NULL THEN 1 ELSE 0 END) AS deleted_cards
    FROM cards GROUP BY user_id
""", payments_engine)

akb_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id) user_id,
        response_score_point AS akb_score, response_score_response AS akb_grade,
        response_score_calculated AS akb_calculated, response_score_exclusion AS akb_exclusion,
        response_borrower_status AS borrower_status,
        COUNT(*) OVER (PARTITION BY user_id) AS akb_check_count
    FROM akb_scores WHERE is_successful=TRUE ORDER BY user_id, timestamp DESC
""", get_engine("akb_score_db"))
akb_hist_df = pd.read_sql("""
    SELECT DISTINCT ON (user_id) user_id, liab_count,
        liab_outstanding_debt_main_sum AS total_outstanding_debt,
        liab_outstanding_debt_interest_sum AS total_outstanding_interest,
        liab_days_main_overdue_max AS max_days_overdue,
        liab_days_main_overdue_sum AS total_days_overdue,
        response_score_point AS history_score, response_balance AS credit_balance
    FROM akb_history_summary ORDER BY user_id, timestamp DESC
""", get_engine("akb_history_db"))
doc_df = pd.read_sql("""
    SELECT user_id, COUNT(*) AS total_docs_uploaded,
        COUNT(DISTINCT loan_id) AS loans_with_docs, MAX(created) AS last_doc_uploaded
    FROM doc_front_all GROUP BY user_id
""", get_engine("doc_front_db"))

# ── 2. Merge + engineer features (identical to training) ──────
df = users_df.copy()
for other in [loans_df, loan_actions_df, loan_states_df, payments_df, cards_df, akb_df, akb_hist_df, doc_df]:
    df = df.merge(other, on="user_id", how="left")

today = date.today()
def calc_age(dob):
    if pd.isnull(dob):
        return None
    dob = pd.to_datetime(dob).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

df["age"]                        = df["birth_date"].apply(calc_age)
df["net_income"]                 = df["monthly_income"].fillna(0) - df["monthly_expenses"].fillna(0)
df["income_total"]               = df["monthly_income"].fillna(0) + df["additional_income"].fillna(0)
df["payment_success_rate"]       = df["successful_payments"] / df["total_payments"].replace(0, 1)
df["delayed_payment_rate"]       = df["delayed_payments"].fillna(0) / df["total_payments"].replace(0, 1)
df["failed_payment_30plus_rate"] = df["failed_payments_30plus"].fillna(0) / df["total_payments"].replace(0, 1)
df["debt_to_income"]             = df["total_outstanding_debt"].fillna(0) / df["income_total"].replace(0, 1)
df["loan_amount_to_income"]      = df["avg_loan_amount"].fillna(0) / df["income_total"].replace(0, 1)
df["overdue_interest_to_debt"]   = df["total_overdue_interest"].fillna(0) / df["total_debt_accumulated"].replace(0, 1)
df["approval_rate"]              = df["times_approved"].fillna(0) / df["times_in_review"].replace(0, 1)
df["is_repeat_borrower"]         = (df["total_loans"].fillna(0) > 1).astype(int)
df["has_akb_score"]              = df["akb_score"].notna().astype(int)
df["has_overdue_history"]        = (df["max_days_overdue"].fillna(0) > 0).astype(int)
df["has_written_off"]            = (df["loans_written_off"].fillna(0) > 0).astype(int)
df["has_uploaded_docs"]          = (df["total_docs_uploaded"].fillna(0) > 0).astype(int)
df["card_verified_rate"]         = df["verified_cards"].fillna(0) / df["total_cards"].replace(0, 1)
df["sex_encoded"]                = df["sex"].map({"male": 1, "female": 0})
df["is_pep"]                     = df["is_pep"].fillna(False).astype(int)
df["is_beneficial_owner"]        = df["is_beneficial_owner"].fillna(False).astype(int)
df["is_related_to_pep"]          = df["is_related_to_pep"].fillna(False).astype(int)
df["marital_status"]             = df["marital_status"].fillna(-1).astype(int)

df["target"] = (
    (df["loans_paid"].fillna(0) > 0) &
    (df["loans_overdue"].fillna(0) == 0) &
    (df["loans_written_off"].fillna(0) == 0) &
    (df["failed_payments_30plus"].fillna(0) == 0)
).astype(int)

# ── 3. Load saved model + its feature list ────────────────────
with open("amanat_model.pkl", "rb") as f:
    saved = pickle.load(f)
model, FEATURES = saved["model"], saved["features"]

df_model = df[FEATURES + ["target"]].copy().dropna(subset=["target"])
df_model[FEATURES] = df_model[FEATURES].fillna(-999)
X, y = df_model[FEATURES], df_model["target"]

# ── 4. Reproduce the exact train/test split ───────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

def report(name, Xs, ys):
    pred = model.predict(Xs)
    prob = model.predict_proba(Xs)[:, 1]
    print(f"\n── {name}  (n={len(ys)}) ──")
    print(f"  Accuracy : {accuracy_score(ys, pred):.4f}")
    print(f"  Precision: {precision_score(ys, pred):.4f}")
    print(f"  Recall   : {recall_score(ys, pred):.4f}")
    print(f"  F1-score : {f1_score(ys, pred):.4f}")
    print(f"  ROC-AUC  : {roc_auc_score(ys, prob):.4f}")
    tn, fp, fn, tp = confusion_matrix(ys, pred).ravel()
    print(f"  Confusion matrix: TN={tn} FP={fp} FN={fn} TP={tp}")
    print(classification_report(ys, pred, target_names=["Bad Borrower", "Good Borrower"]))

print("=" * 60)
print("  Amanat XGBoost — Evaluation of saved amanat_model.pkl")
print("=" * 60)
print(f"Samples: {len(X)} | Features: {len(FEATURES)} | Target dist: {y.value_counts().to_dict()}")
report("HELD-OUT TEST SET (20%)", X_test, y_test)
report("TRAINING SET (80%)", X_train, y_train)
report("FULL DATASET (100%)", X, y)
