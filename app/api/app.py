"""FastAPI application. Authorisation is enforced in the service layer before retrieval."""

from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session_factory
from app.domain.banner import FICTIONAL_BANK, FICTIONAL_BANK_NOTICE, SYNTHETIC_BANNER
from app.domain.errors import AccessDeniedError, IngestionError, SeparationOfDutiesError
from app.evaluation.runner import run_evaluation
from app.rag.pipeline import ask
from app.reporting.generator import generate_customer_report, load_report_bytes, record_review
from app.security.principal import Principal, load_principal
from app.security.tokens import read_token
from app.services import analytics, sources, uploads
from app.services.serialise import jsonable

settings = get_settings()
app = FastAPI(
    title="Harbour Meridian Risk Intelligence",
    version="0.1.0",
    description=(
        f"{SYNTHETIC_BANNER} {FICTIONAL_BANK_NOTICE} "
        "Hackathon proof of concept. Not production-ready and not a statement of regulatory compliance."
    ),
)


def get_session():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except AccessDeniedError:
        session.commit()
        raise
    except IngestionError:
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def principal(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="A bearer token is required.")
    username = read_token(authorization.split(" ", 1)[1].strip())
    if not username:
        raise HTTPException(status_code=401, detail="The session token is not valid.")
    loaded = load_principal(session, username)
    if loaded is None:
        raise HTTPException(status_code=401, detail="The session token is not valid.")
    return loaded


@app.exception_handler(AccessDeniedError)
def denied(_request, exc: AccessDeniedError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=403, content={"detail": str(exc), "banner": SYNTHETIC_BANNER})


@app.exception_handler(IngestionError)
def ingestion_error(_request, exc: IngestionError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=422, content={"detail": str(exc), "banner": SYNTHETIC_BANNER})


@app.exception_handler(SeparationOfDutiesError)
def duties(_request, exc: SeparationOfDutiesError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": str(exc), "banner": SYNTHETIC_BANNER})


class LoginBody(BaseModel):
    username: str
    password: str


class AskBody(BaseModel):
    question: str
    focus_customer_id: str | None = None


class ReportBody(BaseModel):
    customer_id: str


class ReviewBody(BaseModel):
    note: str


class ControlBody(BaseModel):
    key: str
    enabled: bool


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "bank": FICTIONAL_BANK, "banner": SYNTHETIC_BANNER}


@app.get("/ready")
def ready(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ready", "banner": SYNTHETIC_BANNER, "profile": settings.app_env}


@app.post("/auth/login")
def login(body: LoginBody, session: Session = Depends(get_session)) -> dict:
    try:
        return analytics.authenticate(session, body.username, body.password)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/me")
def me(user: Principal = Depends(principal)) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": user.role_label,
        "line": user.line,
        "permissions": sorted(user.permissions),
        "portfolio_ids": sorted(user.portfolio_ids),
        "read_only": user.read_only,
        "banner": SYNTHETIC_BANNER,
    }


@app.get("/dashboard")
def dashboard_route(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.dashboard(session, user))


@app.get("/customers")
def customers(
    session: Session = Depends(get_session),
    user: Principal = Depends(principal),
    q: str | None = None,
    customer_id: str | None = None,
    group_id: str | None = None,
    industry: str | None = None,
    jurisdiction: str | None = None,
    place_of_incorporation: str | None = None,
    relationship_manager: str | None = None,
    internal_risk_rating: str | None = None,
    customer_risk_classification: str | None = None,
    aml_risk_classification: str | None = None,
    facility_type: str | None = None,
    product: str | None = None,
    limit_status: str | None = None,
    early_warning: str | None = None,
    watchlist_status: str | None = None,
):
    return jsonable(
        analytics.search_customers(
            session,
            user,
            {
                "q": q,
                "customer_id": customer_id,
                "group_id": group_id,
                "industry": industry,
                "jurisdiction": jurisdiction,
                "place_of_incorporation": place_of_incorporation,
                "relationship_manager": relationship_manager,
                "internal_risk_rating": internal_risk_rating,
                "customer_risk_classification": customer_risk_classification,
                "aml_risk_classification": aml_risk_classification,
                "facility_type": facility_type,
                "product": product,
                "limit_status": limit_status,
                "early_warning": early_warning,
                "watchlist_status": watchlist_status,
            },
        )
    )


@app.get("/customers/{customer_id}")
def customer(customer_id: str, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.customer_360(session, user, customer_id))


@app.get("/groups")
def groups(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.list_groups(session, user))


@app.get("/groups/{group_id}")
def group(group_id: str, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.group_360(session, user, group_id))


@app.post("/ask")
def ask_route(body: AskBody, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(ask(session, user, body.question, focus_customer_id=body.focus_customer_id))


@app.post("/reports")
def create_report(body: ReportBody, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return generate_customer_report(session, user, body.customer_id)


@app.get("/reports/{report_id}/{kind}")
def download_report(
    report_id: str,
    kind: str,
    session: Session = Depends(get_session),
    user: Principal = Depends(principal),
):
    if kind not in {"html", "pdf"}:
        raise HTTPException(status_code=404, detail="Unknown report format.")
    data, media = load_report_bytes(session, user, report_id, kind)
    return Response(content=data, media_type=media)


@app.post("/reports/{report_id}/review")
def review_report(
    report_id: str,
    body: ReviewBody,
    session: Session = Depends(get_session),
    user: Principal = Depends(principal),
):
    return record_review(session, user, report_id, body.note)


@app.get("/portfolio")
def portfolio(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.portfolio_view(session, user))


@app.get("/facilities")
def facilities(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.facilities_view(session, user))


@app.get("/covenants")
def covenants(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.covenants_view(session, user))


@app.get("/collateral")
def collateral(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.collateral_view(session, user))


@app.get("/early-warnings")
def early_warnings(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.ewi_view(session, user))


@app.get("/aml")
def aml(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.aml_view(session, user))


@app.get("/documents")
def documents(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.documents_view(session, user))


@app.get("/documents/{document_id}")
def document(document_id: str, session: Session = Depends(get_session), user: Principal = Depends(principal), page: int | None = None, sheet: str | None = None):
    payload = sources.open_source(session, user, document_id, page=page, sheet=sheet)
    preview = payload.get("preview") or {}
    if "png" in preview:
        preview = {key: value for key, value in preview.items() if key != "png"}
        preview["image_route"] = f"/documents/{document_id}/page.png"
    payload["preview"] = preview
    return jsonable(payload)


@app.get("/documents/{document_id}/page.png")
def document_page(
    document_id: str,
    page: int = Query(default=1),
    session: Session = Depends(get_session),
    user: Principal = Depends(principal),
):
    payload = sources.open_source(session, user, document_id, page=page)
    png = (payload.get("preview") or {}).get("png")
    if not png:
        raise HTTPException(status_code=404, detail="This source has no page image.")
    return Response(content=png, media_type="image/png")


@app.get("/documents/{document_id}/file")
def document_file(document_id: str, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    data, media, filename = sources.document_bytes(session, user, document_id)
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/source")
def source(document_id: str, page: int | None = None, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return document(document_id, session, user, page, None)


@app.post("/uploads")
async def upload(
    session: Session = Depends(get_session),
    user: Principal = Depends(principal),
    file: UploadFile = File(...),
    customer_id: str = Form(...),
    risk_domain: str = Form("credit"),
    document_type: str = Form("uploaded_report"),
    reporting_date: date = Form(...),
):
    data = await file.read()
    return uploads.accept_upload(
        session,
        user,
        filename=file.filename or "upload.bin",
        data=data,
        customer_id=customer_id,
        risk_domain=risk_domain,
        document_type=document_type,
        reporting_date=reporting_date,
    )


@app.get("/data-quality")
def quality(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.data_quality_view(session, user))


@app.get("/governance")
def governance(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.governance_view(session, user))


@app.get("/audit")
def audit(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.audit_view(session, user))


@app.get("/admin")
def admin(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.admin_view(session, user))


@app.post("/admin/controls")
def controls(body: ControlBody, session: Session = Depends(get_session), user: Principal = Depends(principal)):
    return jsonable(analytics.set_control(session, user, body.key, body.enabled))


@app.post("/evaluation/run")
def evaluation(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    if not user.can("evaluation.run"):
        raise AccessDeniedError("This role cannot run the evaluation.")
    return run_evaluation(session)


@app.get("/taxonomy")
def taxonomy(session: Session = Depends(get_session), user: Principal = Depends(principal)):
    from sqlalchemy import select

    from app.models.tables import RiskTaxon

    if not user.can("customer.read") and not user.can("governance.read"):
        raise AccessDeniedError("This role cannot read the taxonomy.")
    rows = session.scalars(select(RiskTaxon).order_by(RiskTaxon.name)).all()
    return jsonable(
        [{"code": row.code, "name": row.name, "description": row.description, "owner_function": row.owner_function} for row in rows]
    )
