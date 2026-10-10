"""Load a built world into the database and trusted document store."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings, load_json
from app.domain.banner import REGULATORY_REVIEW_NOTICE
from app.domain.dates import fixed_calculated_at
from app.ingestion.pipeline import ingest_pending
from app.ingestion.store import TrustedDocumentStore
from app.models import tables as models
from synthetic_data.build import Builder

TABLE_MODELS = {
    "portfolios": models.Portfolio,
    "users": models.User,
    "user_portfolios": models.UserPortfolio,
    "customer_groups": models.CustomerGroup,
    "products": models.Product,
    "customers": models.Customer,
    "beneficial_owners": models.BeneficialOwner,
    "customer_products": models.CustomerProduct,
    "facilities": models.Facility,
    "facility_snapshots": models.FacilitySnapshot,
    "deposit_balances": models.DepositBalance,
    "fx_rates": models.FxRate,
    "risk_metrics": models.RiskMetric,
    "rating_history": models.RatingHistory,
    "qualitative_assessments": models.QualitativeAssessment,
    "collateral_items": models.CollateralItem,
    "collateral_valuations": models.CollateralValuation,
    "covenants": models.Covenant,
    "covenant_observations": models.CovenantObservation,
    "reported_figures": models.ReportedFigure,
    "alerts": models.Alert,
    "risk_events": models.RiskEvent,
    "management_actions": models.ManagementAction,
    "reviews": models.Review,
    "early_warning_indicators": models.EarlyWarning,
    "watchlist_entries": models.WatchlistEntry,
    "transactions": models.Transaction,
    "legal_matters": models.LegalMatter,
    "documents": models.Document,
    "document_customers": models.DocumentCustomer,
    "evidence_statements": models.EvidenceStatement,
    "data_quality_issues": models.DataQualityIssue,
    "dataset_meta": models.DatasetMeta,
}

INSERT_ORDER = list(TABLE_MODELS)


def persist_world(session: Session, world: Builder, store: TrustedDocumentStore) -> dict[str, int]:
    for table in INSERT_ORDER:
        model = TABLE_MODELS[table]
        for row in world.tables.get(table, []):
            session.add(model(**row))
        session.flush()
    _governance(session)
    session.commit()
    for item in world.files:
        store.put(item["key"], item["data"])
    counts = ingest_pending(session, store, actor="synthetic-generator")
    session.commit()
    return counts


def _governance(session: Session) -> None:
    settings = get_settings()
    for item in load_json("risk_taxonomy.json"):
        session.add(models.RiskTaxon(**item))
    for item in load_json("regulatory_references.json"):
        session.add(models.RegulatoryReference(**item, disclaimer=REGULATORY_REVIEW_NOTICE))
    rbac = load_json("rbac.json")
    for role, spec in rbac["roles"].items():
        for permission in spec["permissions"]:
            session.add(models.RolePermission(role=role, permission=permission))
    governance = load_json("governance.json")
    for item in governance["models"]:
        session.add(
            models.ModelRegistry(
                model_id=item["model_id"],
                provider=item["provider"],
                purpose=item["purpose"],
                creates_numeric_scores=item["creates_numeric_scores"],
                status=item["status"],
                version=item["model_id"].rsplit("-", 1)[-1],
            )
        )
    for item in governance["prompts"]:
        session.add(models.PromptRegistry(**item))
    for item in governance["prohibited_uses"]:
        session.add(models.ProhibitedUse(**item))
    for item in governance["third_parties"]:
        session.add(models.ThirdParty(**item))
    now = fixed_calculated_at()
    session.add(
        models.ControlState(
            key="ai_kill_switch",
            value="true" if settings.ai_kill_switch_default else "false",
            updated_by="synthetic-generator",
            updated_at=now,
            note="When true, narrative commentary is suppressed. Deterministic figures remain available.",
        )
    )
    session.add(
        models.ControlState(
            key="demo_mode",
            value="true" if settings.demo_mode_default else "false",
            updated_by="synthetic-generator",
            updated_at=now,
            note="Controlled demonstration mode for upload checks. Default is off.",
        )
    )
    session.add(
        models.DatasetMeta(key="intended_purpose", value=governance["intended_purpose"])
    )
    session.add(models.DatasetMeta(key="system_owner", value=governance["system_owner"]))
    session.add(models.DatasetMeta(key="risk_owner", value=governance["risk_owner"]))
    session.add(models.DatasetMeta(key="periodic_review_date", value=governance["periodic_review_date"]))
    session.add(
        models.DatasetMeta(key="independent_validation", value=governance["independent_validation"])
    )
    session.add(
        models.DatasetMeta(key="training_data_declaration", value=governance["training_data_declaration"])
    )
    session.add(
        models.DatasetMeta(key="residual_risks", value="\n".join(governance["residual_risks"]))
    )
