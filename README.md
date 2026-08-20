<div align="center">
  <h1>🏦 Amanat Credit Decision System</h1>
  <p>AI-powered credit decision tool built for <strong>Amanat.az</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.13-blue?style=flat-square&logo=python" />
    <img src="https://img.shields.io/badge/FastAPI-0.139-green?style=flat-square&logo=fastapi" />
    <img src="https://img.shields.io/badge/XGBoost-1.7.6-orange?style=flat-square" />
    <img src="https://img.shields.io/badge/PostgreSQL-17-blue?style=flat-square&logo=postgresql" />
    <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker" />
  </p>
</div>

---

## What it does

Amanat is a two-stage credit decision system:

**Stage 1 — Hard Rules**
- Age < 18 → instant reject
- AKB score < 300 → instant reject

**Stage 2 — XGBoost ML Model**
- Trained on 8,656 customers and 70 features
- Pulls real-time data from 6 PostgreSQL databases
- Returns probability score + loan recommendation

---

## Features

- 🤖 **XGBoost ML model** — 70 features, ROC-AUC 1.0
- 💰 **Loan recommender** — suggests max amount and interest rate
- 🚨 **Fraud detection** — flags suspicious submissions
- 📊 **Admin dashboard** — analytics, heatmap, submissions table
- 🎯 **2-step new customer flow** — hard rules → ML assessment
- 🔄 **Existing customer lookup** — pulls history from DB automatically
- 🎉 **Confetti on approval** — because why not

---

## Project Structure

```
Amanat Credit Decision Tool/
├── Back-end/
│   ├── customer_decision_amanat_2.py   # FastAPI backend
│   ├── train_model_2.py                # XGBoost training
│   ├── score_all_customers_2.py        # Batch scoring
│   ├── save_to_ml.py                   # Save ML features
│   ├── load_6_databases.py             # Load Excel → PostgreSQL
│   ├── create_databases.py             # Create all databases
│   ├── amanat_model.pkl                # Trained model (not in git)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── init.sql
│   └── .env.example
└── Front-end/
    └── index.html                      # Revolut-style dark UI
```

---

## Quick Start with Docker

### Prerequisites
- [Docker Desktop](https://docker.com/products/docker-desktop)
- `amanat_model.pkl` — train it first (see below)

### Run

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/amanat-credit.git
cd amanat-credit/Back-end

# 2. Copy env file
cp .env.example .env

# 3. Start everything
docker-compose up --build
```

Backend runs at `http://localhost:8003`
Swagger docs at `http://localhost:8003/docs`

Open `Front-end/index.html` in your browser.

### Stop

```bash
docker-compose down          # stop
docker-compose down -v       # stop + delete all data
```

---

## Manual Setup (without Docker)

### Requirements
- Python 3.13
- PostgreSQL 17 ([Postgres.app](https://postgresapp.com) for Mac)

### Steps

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create databases
python3 create_databases.py

# 3. Load Excel data into PostgreSQL
python3 load_6_databases.py

# 4. Train the XGBoost model
python3 train_model_2.py

# 5. Score all customers
python3 score_all_customers_2.py

# 6. Start the server
uvicorn customer_decision_amanat_2:app --reload --port 8003

# 7. Open the frontend
# Open Front-end/index.html in your browser
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | Health check |
| `POST` | `/submit-customer` | Submit customer for decision |
| `GET`  | `/check-customer/{user_id}` | Check existing customer by ID |
| `GET`  | `/export-all` | Export all decisions to Excel |
| `GET`  | `/admin/submissions` | All submissions (admin) |
| `GET`  | `/admin/analytics` | Analytics data (admin) |
| `GET`  | `/admin/heatmap` | Risk heatmap data (admin) |

Full docs: `http://localhost:8003/docs`

---

## ML Model

### Features (70 total)
| Group | Features | Importance |
|-------|----------|------------|
| 🏦 Loan History | loans_paid_count, total_loans, loans_overdue | **49.2%** |
| 💳 Payment Behavior | successful_payments, payment_success_rate | **43.8%** |
| 📊 Debt Quality | total_overdue_interest, overdue_interest_to_debt | **3.4%** |
| 📈 AKB Credit | akb_score, akb_check_count | **0.8%** |
| Everything else | — | **2.8%** |

### Model Performance

Evaluated on the held-out test set (20%, `random_state=42`, n = 1,732):

| Metric | Score |
|--------|-------|
| Accuracy | **0.9994** |
| Precision | **0.9992** |
| Recall | **1.0000** |
| F1-score | **0.9996** |
| ROC-AUC | **1.0000** |

Confusion matrix: `TN=452 · FP=1 · FN=0 · TP=1279`

> ⚠️ **Note — target leakage.** These near-perfect scores are inflated. The target
> (good borrower) is derived from `loans_paid`, `loans_overdue`, `loans_written_off`
> and `failed_payments_30plus`, and those same columns are also used as input
> features — so the model largely reads the label off its own inputs. To get a
> realistic estimate, drop the leaking features (`loans_paid_count`, `loans_overdue`,
> `loans_written_off`, `failed_payments_30plus`, `failed_payment_30plus_rate`,
> `has_written_off`, `has_overdue_history`) and retrain.

Reproduce the metrics:

```bash
python3 evaluate_model.py
```

### Retrain the model

```bash
python3 train_model_2.py
```

---

## Database Structure

| Database | Tables | Description |
|----------|--------|-------------|
| `loan_users_db` | users, questionnaires | Customer profiles |
| `loans_db` | loans, loan_states, loan_conditions, credit_products, credit_intervals, loan_actions | Loan data |
| `payments_db` | payments, cards | Payment history |
| `akb_score_db` | akb_scores | Credit bureau scores |
| `akb_history_db` | akb_history_summary, akb_liabilities | Credit history |
| `doc_front_db` | doc_front_all, doc_front_last_per_user | Document uploads |
| `amanat_ml_db` | customer_features | Merged ML features |
| `submissions_db` | customer_submissions, customer_decisions | Results |

---

## Admin Panel

Login at the 🔐 Admin button in the top right:
- **Username:** `AdminAMNT`
- **Password:** `amanat_admin_panel`

Features:
- 📊 Overview — daily submissions chart, AKB distribution, rejection reasons
- 📋 Submissions — full table with fraud flags
- 🔥 Risk Heatmap — scatter plot of all customers

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.13 |
| ML Model | XGBoost (70 features) |
| Database | PostgreSQL 17 |
| Frontend | HTML + CSS + JavaScript (dark theme) |
| Container | Docker + Docker Compose |
| Charts | Chart.js |

---

<div align="center">
  <p>Built for <strong>Amanat.az</strong> · Internal Use Only</p>
</div>
