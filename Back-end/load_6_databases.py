import os
import pandas as pd
from sqlalchemy import create_engine, text


PG_USER = "postgres"
PG_HOST = "localhost"
PG_PORT = "5432"
IF_EXISTS = "append" 
DDL_FILE  = "pgadmin_6_databases_ddl.sql"  

def db_url(dbname):
    return f"postgresql://{PG_USER}@{PG_HOST}:{PG_PORT}/{dbname}"

def run_ddl(dbname, marker_start, marker_end):
    """Extract and run the CREATE TABLE statements for one database section."""
    with open(DDL_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find(marker_start)
    end = content.find(marker_end) if marker_end else len(content)
    section = content[start:end]

    
    statements = [s.strip() + ");" for s in section.split(");") if "CREATE TABLE" in s]

    engine = create_engine(db_url(dbname), future=True)
    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()
    print(f"  🔧 Tables ensured in {dbname}")


def to_bool(series):
    return series.map({0.0: False, 1.0: True, 0: False, 1: True, True: True, False: False})

def load(df, table, engine):
    df.to_sql(table, engine, if_exists=IF_EXISTS, index=False, chunksize=500)
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    return count

def verify(excel_rows, db_rows, table):
    status = "✅ OK" if excel_rows == db_rows else "❌ MISMATCH"
    print(f"    {status}  {table}: Excel={excel_rows:,}  DB={db_rows:,}")



def process_loan_users_db():
    print("\n📂 01_users-db.xlsx  →  🗄️  loan_users_db")
    run_ddl("loan_users_db", "-- DATABASE 1: loan_users_db", "-- DATABASE 2:")
    raw = pd.read_excel("01_users-db.xlsx", sheet_name=None)
    engine = create_engine(db_url("loan_users_db"), future=True)
    results = []

    df = raw["User"].rename(columns={
        "Id": "id", "Login": "login", "PhoneNumber": "phone_number",
        "PhoneNumberConfirmed": "phone_number_confirmed",
        "EmailConfirmed": "email_confirmed", "Role": "role",
        "Locale": "locale", "QuestionnaireId": "questionnaire_id",
        "Created": "created", "Disabled": "disabled", "IsLocked": "is_locked",
        "QuestionnaireCompletion": "questionnaire_completion",
        "LoansPaid": "loans_paid", "PIN": "pin",
        "FailedLoginAttempts": "failed_login_attempts", "LockoutEnd": "lockout_end",
    })
    for col in ("disabled", "lockout_end"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ("phone_number_confirmed", "email_confirmed", "is_locked"):
        df[col] = df[col].astype(bool)
    for col in ("questionnaire_id", "questionnaire_completion", "loans_paid", "failed_login_attempts"):
        df[col] = df[col].astype("Int64")
    print(f"  Loading users ({len(df):,} rows) ...")
    results.append(("users", len(df), load(df, "users", engine)))

    df = raw["Questionnaire"].rename(columns={
        "Id": "id", "UserId": "user_id", "Email": "email",
        "Name": "name", "Patronymic": "patronymic", "Surname": "surname",
        "Sex": "sex", "BirthDate": "birth_date", "Hometown": "hometown",
        "PIN": "pin", "IdExpires": "id_expires", "JobTitle": "job_title",
        "MonthlyIncome": "monthly_income", "MonthlyExpenses": "monthly_expenses",
        "RegistrationStreet": "registration_street",
        "RegistrationHouseNumber": "registration_house_number",
        "RegistrationApartmentNumber": "registration_apartment_number",
        "RegistrationRegion": "registration_region",
        "ResidenceStreet": "residence_street",
        "ResidenceHouseNumber": "residence_house_number",
        "ResidenceApartmentNumber": "residence_apartment_number",
        "ResidenceRegion": "residence_region", "Created": "created",
        "IdNumber": "id_number", "IdSeries": "id_series",
        "CompanyName": "company_name", "AdditionalIncome": "additional_income",
        "BusinessNumber": "business_number", "Citizenship": "citizenship",
        "MaritalStatus": "marital_status", "PreviousName": "previous_name",
        "PreviousPatronymic": "previous_patronymic", "PreviousSurname": "previous_surname",
        "IsBeneficialOwner": "is_beneficial_owner", "IsPEP": "is_pep",
        "IsRelatedToPEP": "is_related_to_pep", "PoliticalPosition": "political_position",
        "PoliticalPositionTaken": "political_position_taken",
        "RelatedPEPFullName": "related_pep_full_name",
        "RelatedPEPPosition": "related_pep_position",
    })
    for col in ("birth_date", "id_expires", "political_position_taken"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    for col in ("monthly_income", "monthly_expenses", "additional_income"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("is_beneficial_owner", "is_pep", "is_related_to_pep"):
        df[col] = to_bool(df[col])
    df["marital_status"] = df["marital_status"].astype("Int64")
    print(f"  Loading questionnaires ({len(df):,} rows) ...")
    results.append(("questionnaires", len(df), load(df, "questionnaires", engine)))

    return results


def process_loans_db():
    print("\n📂 02_loans-db.xlsx  →  🗄️  loans_db")
    run_ddl("loans_db", "-- DATABASE 2: loans_db", "-- DATABASE 3:")
    raw = pd.read_excel("02_loans-db.xlsx", sheet_name=None)
    engine = create_engine(db_url("loans_db"), future=True)
    results = []

    df = raw["Loan"].rename(columns={
        "Id": "id", "UserId": "user_id",
        "RequestedConditionsId": "requested_conditions_id",
        "OfferedConditionsId": "offered_conditions_id",
        "CreditProductId": "credit_product_id",
        "Amount": "amount", "Term": "term", "Start": "start",
        "Tag": "tag", "StateId": "state_id", "Created": "created", "Number": "number"
    })
    df["offered_conditions_id"] = df["offered_conditions_id"].astype("Int64")
    print(f"  Loading loans ({len(df):,} rows) ...")
    results.append(("loans", len(df), load(df, "loans", engine)))

    df = raw["LoanState"].rename(columns={
        "Id": "id", "LoanId": "loan_id", "TargetDate": "target_date",
        "Principal": "principal", "Fee": "fee", "Interest": "interest",
        "OverdueInterest": "overdue_interest",
        "TotalCalculatedInterest": "total_calculated_interest",
        "Created": "created", "Debt": "debt",
        "TransactionAmount": "transaction_amount",
        "TransactionRemainder": "transaction_remainder",
        "TransactionType": "transaction_type"
    })
    print(f"  Loading loan_states ({len(df):,} rows) ...")
    results.append(("loan_states", len(df), load(df, "loan_states", engine)))

    df = raw["LoanConditions"].rename(columns={
        "Id": "id", "CreditProductId": "credit_product_id",
        "Amount": "amount", "Term": "term", "Created": "created"
    })
    print(f"  Loading loan_conditions ({len(df):,} rows) ...")
    results.append(("loan_conditions", len(df), load(df, "loan_conditions", engine)))

    df = raw["CreditProduct"].rename(columns={
        "Id": "id", "Description": "description",
        "MinAmount": "min_amount", "MaxAmount": "max_amount",
        "MinTerm": "min_term", "MaxTerm": "max_term",
        "ServiceFee": "service_fee", "IsOneTimeOnly": "is_one_time_only",
        "IsActive": "is_active", "Archived": "archived",
        "Created": "created", "IsVip": "is_vip"
    })
    df["archived"] = pd.to_datetime(df["archived"], errors="coerce")
    print(f"  Loading credit_products ({len(df):,} rows) ...")
    results.append(("credit_products", len(df), load(df, "credit_products", engine)))

    df = raw["CreditInterval"].rename(columns={
        "Id": "id", "CreditProductId": "credit_product_id",
        "OrderNumber": "order_number", "Days": "days",
        "Rate": "rate", "IsOverdue": "is_overdue", "Created": "created"
    })
    print(f"  Loading credit_intervals ({len(df):,} rows) ...")
    results.append(("credit_intervals", len(df), load(df, "credit_intervals", engine)))

    df = raw["LoanAction"].rename(columns={
        "Id": "id", "LoanId": "loan_id", "UserId": "user_id",
        "Tag": "tag", "Created": "created"
    })
    print(f"  Loading loan_actions ({len(df):,} rows) ...")
    results.append(("loan_actions", len(df), load(df, "loan_actions", engine)))

    return results


def process_payments_db():
    print("\n📂 03_payments-db.xlsx  →  🗄️  payments_db")
    run_ddl("payments_db", "-- DATABASE 3: payments_db", "-- DATABASE 4:")
    raw = pd.read_excel("03_payments-db.xlsx", sheet_name=None)
    engine = create_engine(db_url("payments_db"), future=True)
    results = []

    df = raw["Payment"].rename(columns={
        "Id": "id", "UserId": "user_id", "LoanId": "loan_id",
        "Amount": "amount", "IsDisbursement": "is_disbursement",
        "IsSuccessful": "is_successful",
        "ExternalTransactionId": "external_transaction_id",
        "BankTransactionId": "bank_transaction_id",
        "BankResponse": "bank_response", "Rrn": "rrn",
        "CardMask": "card_mask", "CardName": "card_name",
        "Created": "created", "CardId": "card_id", "Provider": "provider"
    })
    df["is_successful"] = to_bool(df["is_successful"])
    print(f"  Loading payments ({len(df):,} rows) ...")
    results.append(("payments", len(df), load(df, "payments", engine)))

    df = raw["Card"].rename(columns={
        "Id": "id", "UserId": "user_id", "IsMain": "is_main",
        "IsForDisbursement": "is_for_disbursement",
        "EpointCardId": "epoint_card_id", "IsVerified": "is_verified",
        "Mask": "mask", "Name": "name", "ExpiryDate": "expiry_date",
        "Created": "created", "Deleted": "deleted"
    })
    df["deleted"] = pd.to_datetime(df["deleted"], errors="coerce")
    print(f"  Loading cards ({len(df):,} rows) ...")
    results.append(("cards", len(df), load(df, "cards", engine)))

    return results



def process_akb_score_db():
    print("\n📂 04_elastic_akb-score.xlsx  →  🗄️  akb_score_db")
    run_ddl("akb_score_db", "-- DATABASE 4: akb_score_db", "-- DATABASE 5:")
    raw = pd.read_excel("04_elastic_akb-score.xlsx", sheet_name=None)
    engine = create_engine(db_url("akb_score_db"), future=True)
    results = []

    df = raw["akb_score"].rename(columns={
        "id": "id", "@timestamp": "timestamp", "userId": "user_id",
        "isSuccessful": "is_successful", "request.accepted": "request_accepted",
        "request.purposeCode": "request_purpose_code",
        "request.docSerie": "request_doc_serie",
        "request.documentNo": "request_document_no",
        "request.docType": "request_doc_type",
        "request.pinCode": "request_pin_code",
        "request.birthDate": "request_birth_date",
        "response.reportId": "response_report_id",
        "response.reportingDate": "response_reporting_date",
        "response.borrower.documentNo": "response_borrower_document_no",
        "response.borrower.name": "response_borrower_name",
        "response.borrower.fin": "response_borrower_fin",
        "response.borrower.dateOfBirth": "response_borrower_date_of_birth",
        "response.borrower.placeOfBirth": "response_borrower_place_of_birth",
        "response.borrower.personType": "response_borrower_person_type",
        "response.borrower.fileDate": "response_borrower_file_date",
        "response.borrower.locationCity": "response_borrower_location_city",
        "response.borrower.registeredAddress": "response_borrower_registered_address",
        "response.borrower.status": "response_borrower_status",
        "response.borrower.participantOfPatrioticWar": "response_borrower_participant_of_patriotic_war",
        "response.score.calculated": "response_score_calculated",
        "response.score.point": "response_score_point",
        "response.score.response": "response_score_response",
        "response.score.scoreExclusion": "response_score_exclusion",
        "responseJson": "response_json",
        "errorResponse.error": "error_response_error",
        "errorResponse.message": "error_response_message",
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["response_report_id"] = df["response_report_id"].astype("Int64")
    print(f"  Loading akb_scores ({len(df):,} rows) ...")
    results.append(("akb_scores", len(df), load(df, "akb_scores", engine)))

    return results


# ── DB 5: akb_history_db ──────────────────────────────────────
def process_akb_history_db():
    print("\n📂 05_elastic_akb-history.xlsx  →  🗄️  akb_history_db")
    run_ddl("akb_history_db", "-- DATABASE 5: akb_history_db", "-- DATABASE 6:")
    raw = pd.read_excel("05_elastic_akb-history.xlsx", sheet_name=None)
    engine = create_engine(db_url("akb_history_db"), future=True)
    results = []

    df = raw["summary"].rename(columns={
        "id": "id", "@timestamp": "timestamp", "userId": "user_id",
        "isSuccessful": "is_successful",
        "request.purposeCode": "request_purpose_code",
        "request.accept": "request_accept",
        "request.documentSerial": "request_document_serial",
        "request.documentNo": "request_document_no",
        "request.pin": "request_pin",
        "request.orgId": "request_org_id",
        "request.branchId": "request_branch_id",
        "request.userId": "request_user_id",
        "response.reportId": "response_report_id",
        "response.reportingDate": "response_reporting_date",
        "response.borrower.documentNo": "response_borrower_document_no",
        "response.borrower.name": "response_borrower_name",
        "response.borrower.fin": "response_borrower_fin",
        "response.borrower.dateOfBirth": "response_borrower_date_of_birth",
        "response.borrower.placeOfBirth": "response_borrower_place_of_birth",
        "response.borrower.personType": "response_borrower_person_type",
        "response.borrower.locationCity": "response_borrower_location_city",
        "response.borrower.registeredAddress": "response_borrower_registered_address",
        "response.borrower.status": "response_borrower_status",
        "response.borrower.participantOfPatrioticWar": "response_borrower_participant_of_patriotic_war",
        "response.guarantees": "response_guarantees",
        "response.inquiryHistory.items": "response_inquiry_history_items",
        "response.score.calculated": "response_score_calculated",
        "response.score.point": "response_score_point",
        "response.balance": "response_balance",
        "response.comments": "response_comments",
        "responseXml": "response_xml",
        "liab_count": "liab_count",
        "liab_outstandingDebtMain_sum": "liab_outstanding_debt_main_sum",
        "liab_outstandingDebtInterest_sum": "liab_outstanding_debt_interest_sum",
        "liab_daysMainOverdue_max": "liab_days_main_overdue_max",
        "liab_daysMainOverdue_sum": "liab_days_main_overdue_sum",
        "response.borrower.fileDate": "response_borrower_file_date",
        "response.borrower.fileDateString": "response_borrower_file_date_string",
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["response_report_id"] = df["response_report_id"].astype("Int64")
    print(f"  Loading akb_history_summary ({len(df):,} rows) ...")
    results.append(("akb_history_summary", len(df), load(df, "akb_history_summary", engine)))

    df = raw["liabilities"].rename(columns={
        "id": "id", "bankId": "bank_id", "bankName": "bank_name",
        "accountNo": "account_no", "creditType": "credit_type",
        "orgIDType": "org_id_type", "grantedOn": "granted_on",
        "initialAmount": "initial_amount", "lineAmount": "line_amount",
        "daysInterestOverdue": "days_interest_overdue",
        "daysMainSumOverdue": "days_main_sum_overdue",
        "contractDueOn": "contract_due_on", "interestRate": "interest_rate",
        "lastUpdatedDate": "last_updated_date",
        "outstandingDebtMain": "outstanding_debt_main",
        "outstandingDebtInterest": "outstanding_debt_interest",
        "monthlyPaymentAmount": "monthly_payment_amount",
        "prolongations": "prolongations", "creditStatus": "credit_status",
        "creditPurpose": "credit_purpose", "currency": "currency",
        "mkrId": "mkr_id", "collateralCode": "collateral_code",
        "collateralMarketValue": "collateral_market_value",
        "collateralRegistryAgency": "collateral_registry_agency",
        "collateralRegistryNo": "collateral_registry_no",
        "collateralAnyInfo": "collateral_any_info",
        "history.historyItems": "history_history_items",
        "userId": "user_id",
        "creditStatusCloseDate": "credit_status_close_date",
        "collateralRegistryDate": "collateral_registry_date",
        "lastPaymentDate": "last_payment_date",
    })
    print(f"  Loading akb_liabilities ({len(df):,} rows) ...")
    results.append(("akb_liabilities", len(df), load(df, "akb_liabilities", engine)))

    return results


# ── DB 6: doc_front_db ────────────────────────────────────────
def process_doc_front_db():
    print("\n📂 06_doc_front_files.xlsx  →  🗄️  doc_front_db")
    run_ddl("doc_front_db", "-- DATABASE 6: doc_front_db", None)
    raw = pd.read_excel("06_doc_front_files.xlsx", sheet_name=None)
    engine = create_engine(db_url("doc_front_db"), future=True)
    results = []

    df = raw["doc_front_all"].rename(columns={
        "UserId": "user_id", "FileName": "file_name", "Created": "created",
        "LoanId": "loan_id", "Number": "number", "Tag": "tag",
        "Amount": "amount", "Term": "term", "Start": "start"
    })
    print(f"  Loading doc_front_all ({len(df):,} rows) ...")
    results.append(("doc_front_all", len(df), load(df, "doc_front_all", engine)))

    df = raw["doc_front_last_per_user"].rename(columns={
        "UserId": "user_id", "FileName": "file_name", "Created": "created"
    })
    print(f"  Loading doc_front_last_per_user ({len(df):,} rows) ...")
    results.append(("doc_front_last_per_user", len(df), load(df, "doc_front_last_per_user", engine)))

    return results


# ── Main ──────────────────────────────────────────────────────
def main():
    all_results = {}
    all_results["loan_users_db"] = process_loan_users_db()
    all_results["loans_db"] = process_loans_db()
    all_results["payments_db"] = process_payments_db()
    all_results["akb_score_db"] = process_akb_score_db()
    all_results["akb_history_db"] = process_akb_history_db()
    all_results["doc_front_db"] = process_doc_front_db()

    print("\n\n══════════════════════════════════════════════════════════")
    print("  ROW-COUNT VERIFICATION (per database)")
    print("══════════════════════════════════════════════════════════")
    for dbname, results in all_results.items():
        print(f"\n🗄️  {dbname}")
        for table, excel_rows, db_rows in results:
            verify(excel_rows, db_rows, table)
    print("══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
