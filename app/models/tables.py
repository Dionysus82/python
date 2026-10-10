"""Relational model for the hackathon profile.

SQLite and PostgreSQL share these types. Monetary amounts use Numeric.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Portfolio(Base):
    __tablename__ = "portfolios"
    portfolio_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    fictional_notice: Mapped[str] = mapped_column(String(300))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(64))
    permission: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("role", "permission", name="uq_role_permission"),)


class UserPortfolio(Base):
    __tablename__ = "user_portfolios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.portfolio_id"))
    __table_args__ = (UniqueConstraint("user_id", "portfolio_id", name="uq_user_portfolio"),)


class CustomerGroup(Base):
    __tablename__ = "customer_groups"
    group_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    headquarters_jurisdiction: Mapped[str] = mapped_column(String(120))
    primary_industry: Mapped[str] = mapped_column(String(160))


class Customer(Base):
    __tablename__ = "customers"
    customer_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(300), index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("customer_groups.group_id"), index=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.portfolio_id"), index=True)
    industry: Mapped[str] = mapped_column(String(160), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(120), index=True)
    place_of_incorporation: Mapped[str] = mapped_column(String(160))
    relationship_manager: Mapped[str] = mapped_column(String(200), index=True)
    onboarding_status: Mapped[str] = mapped_column(String(80))
    customer_risk_classification: Mapped[str] = mapped_column(String(32), index=True)
    aml_risk_classification: Mapped[str] = mapped_column(String(32))
    watchlist_status: Mapped[str] = mapped_column(String(40), index=True)
    business_summary: Mapped[str] = mapped_column(Text)
    registered_address: Mapped[str] = mapped_column(String(300))
    incorporation_date: Mapped[date] = mapped_column(Date)
    synthetic_lei: Mapped[str] = mapped_column(String(40))
    profile: Mapped[str] = mapped_column(String(40))
    data_freshness_date: Mapped[date] = mapped_column(Date)


class BeneficialOwner(Base):
    __tablename__ = "beneficial_owners"
    owner_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    ownership_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    pep_indicator: Mapped[bool] = mapped_column(Boolean, default=False)
    fictional_notice: Mapped[str] = mapped_column(String(200))


class Product(Base):
    __tablename__ = "products"
    product_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))


class CustomerProduct(Base):
    __tablename__ = "customer_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.product_code"))
    started_on: Mapped[date] = mapped_column(Date)


class Facility(Base):
    __tablename__ = "facilities"
    facility_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.product_code"))
    facility_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(40))


class FacilitySnapshot(Base):
    __tablename__ = "facility_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.facility_id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    committed_limit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    drawn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    undrawn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    contingent: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    ccr: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    fx_rate_date: Mapped[date] = mapped_column(Date)
    fx_source: Mapped[str] = mapped_column(String(200))
    fx_method: Mapped[str] = mapped_column(String(80))
    hkd_committed: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    hkd_drawn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    hkd_undrawn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    hkd_contingent: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    hkd_ccr: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    hkd_notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    utilisation_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(40))
    source_system: Mapped[str] = mapped_column(String(200))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_snapshot_customer_date", "customer_id", "as_of_date"),)


class DepositBalance(Base):
    __tablename__ = "deposit_balances"
    balance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    fx_rate_date: Mapped[date] = mapped_column(Date)
    fx_source: Mapped[str] = mapped_column(String(200))
    fx_method: Mapped[str] = mapped_column(String(80))
    hkd_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    source_system: Mapped[str] = mapped_column(String(200))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FxRate(Base):
    __tablename__ = "fx_rates"
    rate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    rate_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(80))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiskMetric(Base):
    __tablename__ = "risk_metrics"
    metric_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    domain: Mapped[str] = mapped_column(String(40))
    metric_key: Mapped[str] = mapped_column(String(80))
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    hkd_equivalent: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_quality: Mapped[str] = mapped_column(String(40))
    source_system: Mapped[str] = mapped_column(String(200))
    calculation_basis: Mapped[str] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RatingHistory(Base):
    __tablename__ = "rating_history"
    rating_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    rating: Mapped[int] = mapped_column(Integer)
    probability_of_default: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    source_system: Mapped[str] = mapped_column(String(200))
    scale_note: Mapped[str] = mapped_column(String(200))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QualitativeAssessment(Base):
    __tablename__ = "qualitative_assessments"
    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    domain: Mapped[str] = mapped_column(String(40))
    as_of_date: Mapped[date] = mapped_column(Date)
    severity: Mapped[str] = mapped_column(String(20))
    statement: Mapped[str] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(String(200))
    data_quality: Mapped[str] = mapped_column(String(40))
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")


class CollateralItem(Base):
    __tablename__ = "collateral_items"
    collateral_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    facility_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    collateral_type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3))
    eligible: Mapped[bool] = mapped_column(Boolean, default=True)


class CollateralValuation(Base):
    __tablename__ = "collateral_valuations"
    valuation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collateral_id: Mapped[str] = mapped_column(ForeignKey("collateral_items.collateral_id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    fx_rate_date: Mapped[date] = mapped_column(Date)
    fx_source: Mapped[str] = mapped_column(String(200))
    fx_method: Mapped[str] = mapped_column(String(80))
    hkd_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    eligible: Mapped[bool] = mapped_column(Boolean)
    source_system: Mapped[str] = mapped_column(String(200))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Covenant(Base):
    __tablename__ = "covenants"
    covenant_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    facility_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    metric_key: Mapped[str] = mapped_column(String(80))
    operator: Mapped[str] = mapped_column(String(8))
    threshold: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    unit: Mapped[str] = mapped_column(String(40))


class CovenantObservation(Base):
    __tablename__ = "covenant_observations"
    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    covenant_id: Mapped[str] = mapped_column(ForeignKey("covenants.covenant_id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date)
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    source_system: Mapped[str] = mapped_column(String(200))
    data_quality: Mapped[str] = mapped_column(String(40))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportedFigure(Base):
    __tablename__ = "reported_figures"
    figure_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(80))
    as_of_date: Mapped[date] = mapped_column(Date)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    unit: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_label: Mapped[str] = mapped_column(String(300))
    value_status: Mapped[str] = mapped_column(String(40))


class EvidenceStatement(Base):
    __tablename__ = "evidence_statements"
    statement_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    group_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    numeric_value: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locator: Mapped[dict] = mapped_column(JSON)
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    claim_type: Mapped[str] = mapped_column(String(40), default="sourced_fact")
    stale: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"
    alert_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    domain: Mapped[str] = mapped_column(String(40))
    alert_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    opened_on: Mapped[date] = mapped_column(Date)
    sensitivity: Mapped[str] = mapped_column(String(20))
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    source_system: Mapped[str] = mapped_column(String(200))


class RiskEvent(Base):
    __tablename__ = "risk_events"
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    domain: Mapped[str] = mapped_column(String(40))
    event_date: Mapped[date] = mapped_column(Date)
    severity: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    source_system: Mapped[str] = mapped_column(String(200))


class ManagementAction(Base):
    __tablename__ = "management_actions"
    action_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_function: Mapped[str] = mapped_column(String(80))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    source_system: Mapped[str] = mapped_column(String(200))


class Review(Base):
    __tablename__ = "reviews"
    review_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    review_type: Mapped[str] = mapped_column(String(40))
    due_date: Mapped[date] = mapped_column(Date)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    source_system: Mapped[str] = mapped_column(String(200))


class EarlyWarning(Base):
    __tablename__ = "early_warning_indicators"
    ewi_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    triggered_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    threshold: Mapped[str] = mapped_column(String(80))
    observed_value: Mapped[str] = mapped_column(String(80))
    domain: Mapped[str] = mapped_column(String(40))
    source_system: Mapped[str] = mapped_column(String(200))


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    entry_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), unique=True)
    status: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    since_date: Mapped[date] = mapped_column(Date)
    source_system: Mapped[str] = mapped_column(String(200))


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    value_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    hkd_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    fx_rate_date: Mapped[date] = mapped_column(Date)
    fx_source: Mapped[str] = mapped_column(String(200))
    fx_method: Mapped[str] = mapped_column(String(80))
    product_code: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    alert_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LegalMatter(Base):
    __tablename__ = "legal_matters"
    matter_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    as_of_date: Mapped[date] = mapped_column(Date)
    source_system: Mapped[str] = mapped_column(String(200))


class Document(Base):
    __tablename__ = "documents"
    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    controlled_reference: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(400))
    document_type: Mapped[str] = mapped_column(String(80))
    original_filename: Mapped[str] = mapped_column(String(300))
    safe_filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(400))
    mime_type: Mapped[str] = mapped_column(String(120))
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    file_size: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    portfolio_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enterprise: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_domain: Mapped[str] = mapped_column(String(40), index=True)
    authoring_function: Mapped[str] = mapped_column(String(80))
    reporting_date: Mapped[date] = mapped_column(Date, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploader: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidentiality: Mapped[str] = mapped_column(String(40))
    synthetic_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    ingestion_status: Mapped[str] = mapped_column(String(40))
    malware_scan_status: Mapped[str] = mapped_column(String(40))
    parser_status: Mapped[str] = mapped_column(String(40))
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    section_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_viewer_route: Mapped[str] = mapped_column(String(200))
    retention_classification: Mapped[str] = mapped_column(String(80))
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard")
    prompt_injection_suspected: Mapped[bool] = mapped_column(Boolean, default=False)
    incomplete: Mapped[bool] = mapped_column(Boolean, default=False)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentCustomer(Base):
    __tablename__ = "document_customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    __table_args__ = (UniqueConstraint("document_id", "customer_id", name="uq_document_customer"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[dict] = mapped_column(JSON)
    sensitivity: Mapped[str] = mapped_column(String(20))
    prompt_injection_suspected: Mapped[bool] = mapped_column(Boolean, default=False)
    token_count: Mapped[int] = mapped_column(Integer)


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(64))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(64))
    aml_access: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(20))


class RiskTaxon(Base):
    __tablename__ = "risk_taxonomy"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    owner_function: Mapped[str] = mapped_column(String(80))


class RegulatoryReference(Base):
    __tablename__ = "regulatory_references"
    reference_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    issuing_authority: Mapped[str] = mapped_column(String(200))
    version_or_issue_date: Mapped[str] = mapped_column(String(300))
    risk_domain: Mapped[str] = mapped_column(String(80))
    design_consideration: Mapped[str] = mapped_column(Text)
    implementation_status: Mapped[str] = mapped_column(String(200))
    application_owner: Mapped[str] = mapped_column(String(200))
    validation_requirement: Mapped[str] = mapped_column(String(200))
    disclaimer: Mapped[str] = mapped_column(Text)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    model_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(Text)
    creates_numeric_scores: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(40))


class PromptRegistry(Base):
    __tablename__ = "prompt_registry"
    prompt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)


class ProhibitedUse(Base):
    __tablename__ = "prohibited_uses"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    statement: Mapped[str] = mapped_column(Text)


class ThirdParty(Base):
    __tablename__ = "third_parties"
    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    data_shared: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
    review_status: Mapped[str] = mapped_column(String(80))


class ControlState(Base):
    __tablename__ = "control_states"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(40))
    updated_by: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    generated_by: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval_status: Mapped[str] = mapped_column(String(200))
    html_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    pdf_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ReportReview(Base):
    __tablename__ = "report_reviews"
    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("generated_reports.report_id"))
    reviewer: Mapped[str] = mapped_column(String(64))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(200))


class AiIncident(Base):
    __tablename__ = "ai_incidents"
    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opened_on: Mapped[date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20))


class DatasetMeta(Base):
    __tablename__ = "dataset_meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class JobRecord(Base):
    __tablename__ = "jobs"
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
