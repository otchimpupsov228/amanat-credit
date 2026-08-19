-- ============================================================
-- DDL  |  6 SEPARATE DATABASES  |  Run in pgAdmin 4
-- ============================================================
-- Each Excel file gets its own database. Each sheet = one table.
--
-- HOW TO USE IN pgAdmin 4:
-- 1. Right-click "Databases" → Create → Database → name it (see below) → Save
-- 2. Click on that new database to select it
-- 3. Open Query Tool (right-click DB → Query Tool)
-- 4. Copy ONLY that database's section below and run it
-- 5. Repeat for all 6 databases
-- ============================================================


-- ============================================================
-- DATABASE 1: loan_users_db
-- File: 01_users-db.xlsx  |  2 sheets → 2 tables
-- ============================================================
-- Create this database first in pgAdmin, named: loan_users_db
-- Then run the below INSIDE that database's Query Tool:

CREATE TABLE IF NOT EXISTS users (
    id                       VARCHAR(36)   NOT NULL,
    login                    TEXT          NOT NULL,
    phone_number             TEXT          NOT NULL,
    phone_number_confirmed   BOOLEAN       NOT NULL DEFAULT FALSE,
    email_confirmed          BOOLEAN       NOT NULL DEFAULT FALSE,
    role                     VARCHAR(50)   NOT NULL,
    locale                   VARCHAR(10)   NOT NULL,
    questionnaire_id         BIGINT        NOT NULL,
    created                  TIMESTAMP     NOT NULL,
    disabled                 TIMESTAMP     NULL,
    is_locked                BOOLEAN       NOT NULL DEFAULT FALSE,
    questionnaire_completion BIGINT        NOT NULL DEFAULT 0,
    loans_paid               INTEGER       NOT NULL DEFAULT 0,
    pin                      TEXT          NULL,
    failed_login_attempts    INTEGER       NOT NULL DEFAULT 0,
    lockout_end              TIMESTAMP     NULL
);

CREATE TABLE IF NOT EXISTS questionnaires (
    id                            BIGINT        NOT NULL,
    user_id                       VARCHAR(36)   NOT NULL,
    email                         TEXT          NULL,
    name                          TEXT          NULL,
    patronymic                    TEXT          NULL,
    surname                       TEXT          NULL,
    sex                           VARCHAR(10)   NULL,
    birth_date                    DATE          NULL,
    hometown                      TEXT          NULL,
    pin                           TEXT          NULL,
    id_expires                    DATE          NULL,
    job_title                     TEXT          NULL,
    monthly_income                NUMERIC(15,2) NULL,
    monthly_expenses              NUMERIC(15,2) NULL,
    registration_street           TEXT          NULL,
    registration_house_number     TEXT          NULL,
    registration_apartment_number TEXT          NULL,
    registration_region           TEXT          NULL,
    residence_street              TEXT          NULL,
    residence_house_number        TEXT          NULL,
    residence_apartment_number    TEXT          NULL,
    residence_region              TEXT          NULL,
    created                       TIMESTAMP     NOT NULL,
    id_number                     TEXT          NULL,
    id_series                     TEXT          NULL,
    company_name                  TEXT          NULL,
    additional_income             NUMERIC(15,2) NULL,
    business_number               TEXT          NULL,
    citizenship                   VARCHAR(50)   NULL,
    marital_status                SMALLINT      NULL,
    previous_name                 TEXT          NULL,
    previous_patronymic           TEXT          NULL,
    previous_surname               TEXT         NULL,
    is_beneficial_owner           BOOLEAN       NULL,
    is_pep                        BOOLEAN       NULL,
    is_related_to_pep             BOOLEAN       NULL,
    political_position            TEXT          NULL,
    political_position_taken      DATE          NULL,
    related_pep_full_name         TEXT          NULL,
    related_pep_position          TEXT          NULL
);


-- ============================================================
-- DATABASE 2: loans_db
-- File: 02_loans-db.xlsx  |  6 sheets → 6 tables
-- ============================================================
-- Create database named: loans_db
-- Then run the below INSIDE that database's Query Tool:

CREATE TABLE IF NOT EXISTS loans (
    id                      VARCHAR(36)    NOT NULL,
    user_id                 VARCHAR(36)    NOT NULL,
    requested_conditions_id BIGINT         NOT NULL,
    offered_conditions_id   BIGINT         NULL,
    credit_product_id       BIGINT         NOT NULL,
    amount                  BIGINT         NOT NULL,
    term                    INTEGER        NOT NULL,
    start                   TIMESTAMP      NOT NULL,
    tag                     VARCHAR(50)    NOT NULL,
    state_id                BIGINT         NOT NULL,
    created                 TIMESTAMP      NOT NULL,
    number                  BIGINT         NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_states (
    id                         BIGINT         NOT NULL,
    loan_id                    VARCHAR(36)    NOT NULL,
    target_date                TIMESTAMP      NOT NULL,
    principal                  NUMERIC(15,4)  NOT NULL,
    fee                        NUMERIC(15,4)  NOT NULL,
    interest                   NUMERIC(15,4)  NOT NULL,
    overdue_interest           NUMERIC(15,4)  NOT NULL,
    total_calculated_interest  NUMERIC(15,4)  NOT NULL,
    created                    TIMESTAMP      NOT NULL,
    debt                       NUMERIC(15,4)  NOT NULL,
    transaction_amount         NUMERIC(15,4)  NOT NULL,
    transaction_remainder      NUMERIC(15,4)  NOT NULL,
    transaction_type           VARCHAR(50)    NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_conditions (
    id                BIGINT     NOT NULL,
    credit_product_id BIGINT     NOT NULL,
    amount            BIGINT     NOT NULL,
    term              INTEGER    NOT NULL,
    created           TIMESTAMP  NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_products (
    id              BIGINT         NOT NULL,
    description     TEXT           NOT NULL,
    min_amount      BIGINT         NOT NULL,
    max_amount      BIGINT         NOT NULL,
    min_term        INTEGER        NOT NULL,
    max_term        INTEGER        NOT NULL,
    service_fee     NUMERIC(10,6)  NOT NULL,
    is_one_time_only BOOLEAN       NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN        NOT NULL DEFAULT FALSE,
    archived        TIMESTAMP      NULL,
    created         TIMESTAMP      NOT NULL,
    is_vip          BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS credit_intervals (
    id                BIGINT         NOT NULL,
    credit_product_id BIGINT         NOT NULL,
    order_number      INTEGER        NOT NULL,
    days              INTEGER        NOT NULL,
    rate              NUMERIC(10,6)  NOT NULL,
    is_overdue        BOOLEAN        NOT NULL DEFAULT FALSE,
    created           TIMESTAMP      NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_actions (
    id       BIGINT       NOT NULL,
    loan_id  VARCHAR(36)  NOT NULL,
    user_id  VARCHAR(36)  NOT NULL,
    tag      VARCHAR(50)  NOT NULL,
    created  TIMESTAMP    NOT NULL
);


-- ============================================================
-- DATABASE 3: payments_db
-- File: 03_payments-db.xlsx  |  2 sheets → 2 tables
-- ============================================================
-- Create database named: payments_db
-- Then run the below INSIDE that database's Query Tool:

CREATE TABLE IF NOT EXISTS payments (
    id                      VARCHAR(36)    NOT NULL,
    user_id                 VARCHAR(36)    NOT NULL,
    loan_id                 VARCHAR(36)    NOT NULL,
    amount                  NUMERIC(15,2)  NOT NULL,
    is_disbursement         BOOLEAN        NOT NULL DEFAULT FALSE,
    is_successful           BOOLEAN        NULL,
    external_transaction_id TEXT           NULL,
    bank_transaction_id     TEXT           NULL,
    bank_response           TEXT           NULL,
    rrn                     TEXT           NULL,
    card_mask               TEXT           NULL,
    card_name               TEXT           NULL,
    created                 TIMESTAMP      NOT NULL,
    card_id                 VARCHAR(36)    NULL,
    provider                SMALLINT       NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id                  VARCHAR(36)  NOT NULL,
    user_id             VARCHAR(36)  NOT NULL,
    is_main             BOOLEAN      NOT NULL DEFAULT FALSE,
    is_for_disbursement BOOLEAN      NOT NULL DEFAULT FALSE,
    epoint_card_id      TEXT         NOT NULL,
    is_verified         BOOLEAN      NOT NULL DEFAULT FALSE,
    mask                TEXT         NULL,
    name                TEXT         NULL,
    expiry_date         VARCHAR(10)  NULL,
    created              TIMESTAMP    NOT NULL,
    deleted             TIMESTAMP    NULL
);


-- ============================================================
-- DATABASE 4: akb_score_db
-- File: 04_elastic_akb-score.xlsx  |  1 sheet → 1 table
-- ============================================================
-- Create database named: akb_score_db
-- Then run the below INSIDE that database's Query Tool:

CREATE TABLE IF NOT EXISTS akb_scores (
    id                                  VARCHAR(36)    NOT NULL,
    timestamp                           TIMESTAMP      NOT NULL,
    user_id                             VARCHAR(36)    NOT NULL,
    is_successful                       BOOLEAN        NOT NULL,
    request_accepted                    BOOLEAN        NOT NULL,
    request_purpose_code                INTEGER        NOT NULL,
    request_doc_serie                   VARCHAR(20)    NOT NULL,
    request_document_no                 TEXT           NOT NULL,
    request_doc_type                    VARCHAR(50)    NOT NULL,
    request_pin_code                    TEXT           NOT NULL,
    request_birth_date                  VARCHAR(20)    NOT NULL,
    response_report_id                  BIGINT         NULL,
    response_reporting_date             TEXT           NULL,
    response_borrower_document_no       TEXT           NULL,
    response_borrower_name              TEXT           NULL,
    response_borrower_fin               TEXT           NULL,
    response_borrower_date_of_birth     VARCHAR(20)    NULL,
    response_borrower_place_of_birth    TEXT           NULL,
    response_borrower_person_type       VARCHAR(50)    NULL,
    response_borrower_file_date         TEXT           NULL,
    response_borrower_location_city     TEXT           NULL,
    response_borrower_registered_address TEXT          NULL,
    response_borrower_status            VARCHAR(20)    NULL,
    response_borrower_participant_of_patriotic_war SMALLINT NULL,
    response_score_calculated           SMALLINT       NULL,
    response_score_point                NUMERIC(8,2)   NULL,
    response_score_response             VARCHAR(10)    NULL,
    response_score_exclusion            SMALLINT       NULL,
    response_json                       TEXT           NULL,
    error_response_error                TEXT           NULL,
    error_response_message              TEXT           NULL
);


-- ============================================================
-- DATABASE 5: akb_history_db
-- File: 05_elastic_akb-history.xlsx  |  2 sheets → 2 tables
-- ============================================================
-- Create database named: akb_history_db
-- Then run the below INSIDE that database's Query Tool:

CREATE TABLE IF NOT EXISTS akb_history_summary (
    id                                        VARCHAR(36)    NOT NULL,
    timestamp                                 TIMESTAMP      NOT NULL,
    user_id                                   VARCHAR(36)    NOT NULL,
    is_successful                             BOOLEAN        NOT NULL,
    request_purpose_code                      INTEGER        NOT NULL,
    request_accept                            BOOLEAN        NOT NULL,
    request_document_serial                   TEXT           NOT NULL,
    request_document_no                       TEXT           NOT NULL,
    request_pin                               TEXT           NOT NULL,
    request_org_id                            INTEGER        NOT NULL,
    request_branch_id                         INTEGER        NOT NULL,
    request_user_id                           INTEGER        NOT NULL,
    response_report_id                        BIGINT         NULL,
    response_reporting_date                   TEXT           NULL,
    response_borrower_document_no             TEXT           NULL,
    response_borrower_name                    TEXT           NULL,
    response_borrower_fin                     TEXT           NULL,
    response_borrower_date_of_birth           VARCHAR(20)    NULL,
    response_borrower_place_of_birth          TEXT           NULL,
    response_borrower_person_type             VARCHAR(50)    NULL,
    response_borrower_location_city           TEXT           NULL,
    response_borrower_registered_address      TEXT           NULL,
    response_borrower_status                  VARCHAR(20)    NULL,
    response_borrower_participant_of_patriotic_war SMALLINT  NULL,
    response_guarantees                       TEXT           NULL,
    response_inquiry_history_items            TEXT           NULL,
    response_score_calculated                 NUMERIC(8,2)   NULL,
    response_score_point                      NUMERIC(8,2)   NULL,
    response_balance                          NUMERIC(15,2)  NULL,
    response_comments                         TEXT           NULL,
    response_xml                              TEXT           NULL,
    liab_count                                INTEGER        NOT NULL,
    liab_outstanding_debt_main_sum            NUMERIC(15,2)  NOT NULL,
    liab_outstanding_debt_interest_sum        NUMERIC(15,2)  NOT NULL,
    liab_days_main_overdue_max                INTEGER        NOT NULL,
    liab_days_main_overdue_sum                INTEGER        NOT NULL,
    response_borrower_file_date               TEXT           NULL,
    response_borrower_file_date_string        TEXT           NULL
);

CREATE TABLE IF NOT EXISTS akb_liabilities (
    id                          BIGINT         NOT NULL,
    bank_id                     BIGINT         NOT NULL,
    bank_name                   TEXT           NOT NULL,
    account_no                  TEXT           NOT NULL,
    credit_type                 INTEGER        NOT NULL,
    org_id_type                 INTEGER        NOT NULL,
    granted_on                  TEXT           NOT NULL,
    initial_amount              NUMERIC(15,2)  NOT NULL,
    line_amount                 NUMERIC(15,2)  NOT NULL,
    days_interest_overdue       INTEGER        NOT NULL,
    days_main_sum_overdue       INTEGER        NOT NULL,
    contract_due_on             TEXT           NOT NULL,
    interest_rate               NUMERIC(8,2)   NOT NULL,
    last_updated_date           TEXT           NOT NULL,
    outstanding_debt_main       NUMERIC(15,2)  NOT NULL,
    outstanding_debt_interest   NUMERIC(15,2)  NOT NULL,
    monthly_payment_amount      NUMERIC(15,2)  NOT NULL,
    prolongations               INTEGER        NOT NULL,
    credit_status               INTEGER        NOT NULL,
    credit_purpose              INTEGER        NOT NULL,
    currency                    VARCHAR(10)    NOT NULL,
    mkr_id                      BIGINT         NOT NULL,
    collateral_code              INTEGER        NOT NULL,
    collateral_market_value     NUMERIC(15,2)  NOT NULL,
    collateral_registry_agency  TEXT           NULL,
    collateral_registry_no      TEXT           NULL,
    collateral_any_info         TEXT           NULL,
    history_history_items       TEXT           NULL,
    user_id                     VARCHAR(36)    NOT NULL,
    credit_status_close_date    TEXT           NULL,
    collateral_registry_date    TEXT           NULL,
    last_payment_date           TEXT           NULL
);


-- ============================================================
-- DATABASE 6: doc_front_db
-- File: 06_doc_front_files.xlsx  |  2 sheets → 2 tables
-- ============================================================
-- Create database named: doc_front_db
-- Then run the below INSIDE that database's Query Tool:

CREATE TABLE IF NOT EXISTS doc_front_all (
    user_id   TEXT        NOT NULL,
    file_name TEXT        NOT NULL,
    created   TIMESTAMP   NOT NULL,
    loan_id   VARCHAR(36) NOT NULL,
    number    BIGINT      NOT NULL,
    tag       VARCHAR(50) NOT NULL,
    amount    BIGINT      NOT NULL,
    term      INTEGER     NOT NULL,
    start     TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_front_last_per_user (
    user_id   TEXT       NOT NULL,
    file_name TEXT       NOT NULL,
    created   TIMESTAMP  NOT NULL
);
