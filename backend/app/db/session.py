from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.query_diagnostics import install_slow_query_monitor


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
install_slow_query_monitor(engine, threshold_ms=settings.slow_query_threshold_ms)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
