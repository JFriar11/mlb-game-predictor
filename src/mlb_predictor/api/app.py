"""Application factory for the read-only prediction ledger API."""

import hashlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from mlb_predictor.api.sandbox import (
    RetainedLineup,
    SandboxCatalog,
    SandboxRequest,
    SandboxResult,
    catalog,
    retained_lineup,
    run_sandbox,
)
from mlb_predictor.api.schemas import (
    ArtifactStatus,
    ErrorResponse,
    GameDetail,
    ISODate,
    Liveness,
    ModelMetadata,
    PredictionList,
    Readiness,
)
from mlb_predictor.api.service import StoredPredictionError, get_game_detail, list_predictions
from mlb_predictor.config import Settings, get_settings
from mlb_predictor.db.models import LiveGameState, LivePredictionRecord, PredictionInputSnapshot
from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    CALIBRATION_VERSION,
    DISTRIBUTION_VERSION,
    FEATURE_VERSION,
    MODEL_VERSION,
)
from mlb_predictor.logging import configure_logging

LOGGER = logging.getLogger(__name__)


def artifact_status(path: Path) -> ArtifactStatus:
    """Check bytes only; HTTP handlers never unpickle a model."""
    try:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    return "verified" if checksum == ACCEPTED_ARTIFACT_SHA256 else "checksum_mismatch"


def create_api_engine(settings: Settings) -> Engine:
    """Bound connection/query waits without changing the CLI's database behavior."""
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        raise ValueError("The API runtime requires PostgreSQL")
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"},
    )


@contextmanager
def read_transaction(engine: Engine) -> Iterator[Session]:
    """Close and roll back each read transaction, including on serialization failure."""
    with Session(engine, autoflush=False) as session:
        if session.bind.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))
        yield session


def read_session(request: Request) -> Iterator[Session]:
    """One rollback-only session per request; PostgreSQL additionally enforces READ ONLY."""
    with read_transaction(request.app.state.engine) as session:
        yield session


ReadSession = Annotated[Session, Depends(read_session)]


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    """Create the service without contacting PostgreSQL or starting background tasks."""
    configuration = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.engine = (
            engine if engine is not None else create_api_engine(configuration)
        )
        try:
            yield
        finally:
            if engine is None:
                application.state.engine.dispose()

    application = FastAPI(
        title="MLB Game Predictor API",
        version="1.0.0",
        docs_url=None if configuration.web_directory else "/docs",
        redoc_url=None if configuration.web_directory else "/redoc",
        lifespan=lifespan,
        description="Read-only access to saved official forecasts from the accepted model. "
        "Optional local sandbox inference is ephemeral; no ingestion, settlement or fitting.",
    )

    @application.middleware("http")
    async def no_cache(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        return response

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        LOGGER.warning("api_database_unavailable")
        return _error(503, "database_unavailable", "Prediction storage is temporarily unavailable.")

    @application.exception_handler(StoredPredictionError)
    @application.exception_handler(ResponseValidationError)
    async def stored_data_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.error("api_stored_prediction_invalid")
        return _error(503, "invalid_stored_prediction", "Stored prediction data failed validation.")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        if request.url.path.startswith("/api/v1/sandbox"):
            message = "; ".join(str(e["msg"]) for e in exc.errors())
            return _error(422, "invalid_sandbox_input", message)
        return _error(422, "invalid_request", "Use a valid ISO date and positive integer game ID.")

    @application.get("/health/live", response_model=Liveness, tags=["health"])
    def liveness() -> Liveness:
        return Liveness()

    @application.get(
        "/health/ready",
        response_model=Readiness,
        responses={503: {"model": Readiness}},
        tags=["health"],
    )
    def readiness(response: Response, request: Request) -> Readiness:
        artifact = artifact_status(configuration.artifact_path)
        database = "ready"
        try:
            # Exercise every column used by data routes without reading any records.
            with read_transaction(request.app.state.engine) as session:
                session.execute(select(LivePredictionRecord).limit(0))
                session.execute(select(LiveGameState).limit(0))
                session.execute(select(PredictionInputSnapshot).limit(0))
        except SQLAlchemyError:
            database = "unavailable"
        ready = database == "ready" and artifact == "verified"
        if not ready:
            response.status_code = 503
        return Readiness(
            status="ready" if ready else "not_ready", database=database, artifact=artifact
        )

    @application.get("/api/v1/model", response_model=ModelMetadata, tags=["predictions"])
    def model_metadata() -> ModelMetadata:
        return ModelMetadata(
            model_version=MODEL_VERSION,
            feature_version=FEATURE_VERSION,
            calibration_version=CALIBRATION_VERSION,
            distribution_version=DISTRIBUTION_VERSION,
            mean_model="stabilized histogram gradient boosting with Poisson loss",
            distribution="independent negative binomial with a censored 12+ run bucket",
            calibration="Platt logistic calibration of raw home-win probability",
            training_start_season=2021,
            training_end_season=2025,
            retrospective_evidence_only=True,
            artifact_sha256_expected=ACCEPTED_ARTIFACT_SHA256,
            artifact_status=artifact_status(configuration.artifact_path),
            known_limitations=[
                "Historical starting lineups are reconstructed, not archived T-minus-30 snapshots.",
                "Home and away regulation scoring is conditionally independent.",
                "Extra innings use a prior-training home-win approximation.",
                "12+ is a censored run bin, including interval endpoints and score combinations.",
                "2021-2025 results are retrospective development evidence.",
                "This endpoint does not certify prospective ledger performance.",
                "Observed weather and unpromoted component features are excluded.",
            ],
        )

    errors = {503: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}

    @application.get(
        "/api/v1/predictions", response_model=PredictionList, responses=errors, tags=["predictions"]
    )
    def predictions(
        session: ReadSession,
        requested_date: Annotated[
            ISODate, Query(alias="date", description="MLB official game date")
        ],
    ) -> PredictionList:
        rows = list_predictions(session, requested_date)
        return PredictionList(
            date=requested_date,
            model_version=MODEL_VERSION,
            generated_at=datetime.now(UTC),
            count=len(rows),
            predictions=rows,
        )

    @application.get(
        "/api/v1/games/{game_pk}",
        response_model=GameDetail,
        responses={**errors, 404: {"model": ErrorResponse}},
        tags=["predictions"],
    )
    def game_detail(
        session: ReadSession,
        game_pk: Annotated[int, ApiPath(gt=0, le=2_147_483_647)],
    ) -> GameDetail | JSONResponse:
        detail = get_game_detail(session, game_pk)
        if detail is None:
            return _error(
                404, "game_not_found", "No retained game or official prediction was found."
            )
        return detail

    if configuration.sandbox_enabled:
        inference_lock = Lock()

        @application.get("/api/v1/sandbox/catalog", response_model=SandboxCatalog)
        def sandbox_catalog(session: ReadSession) -> SandboxCatalog:
            return catalog(session)

        @application.get("/api/v1/sandbox/lineup", response_model=RetainedLineup)
        def sandbox_lineup(
            session: ReadSession,
            team_id: Annotated[int, Query(gt=0)],
            as_of: datetime,
        ) -> RetainedLineup | JSONResponse:
            if as_of.tzinfo is None:
                return _error(422, "invalid_cutoff", "Include a timezone in the cutoff.")
            value = retained_lineup(session, team_id, as_of)
            return (
                value
                if value
                else _error(
                    404,
                    "lineup_unavailable",
                    "No prior starting lineup is retained for this team and cutoff.",
                )
            )

        @application.post("/api/v1/sandbox/predict", response_model=SandboxResult)
        def sandbox_predict(
            inputs: SandboxRequest, session: ReadSession
        ) -> SandboxResult | JSONResponse:
            if not inference_lock.acquire(blocking=False):
                return _error(
                    503, "sandbox_busy", "Another local prediction is running. Try again shortly."
                )
            try:
                if artifact_status(configuration.artifact_path) != "verified":
                    return _error(
                        503,
                        "artifact_unavailable",
                        "The accepted local model is missing or failed checksum verification.",
                    )
                return run_sandbox(session, inputs, configuration.artifact_path)
            except ValueError as exc:
                return _error(422, "invalid_sandbox_input", str(exc))
            finally:
                inference_lock.release()

    if configuration.web_directory is not None:
        root = configuration.web_directory
        if not (root / "index.html").is_file():
            raise ValueError("MLB_WEB_DIRECTORY must contain a built dashboard index.html")
        # Registered API routes win. Query-string UI routes need no SPA fallback.
        application.mount("/", StaticFiles(directory=root, html=True), name="dashboard")

    return application


def main() -> None:
    """Run the local API; public hosting is a separate, approved deployment step."""
    configuration = get_settings()
    configure_logging(configuration.log_level)
    uvicorn.run(
        create_app(configuration),
        host=configuration.api_host,
        port=configuration.api_port,
        log_config=None,
    )
