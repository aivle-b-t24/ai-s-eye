"""PostgreSQL 연결과 SQLAlchemy 공통 기반을 정의한다.

DATABASE_URL이 설정된 환경에서는 DatabaseRepository가 이 연결과 세션을
사용하고, 설정되지 않은 로컬 테스트에서는 기존 메모리 저장소를 사용한다.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """모든 데이터베이스 모델이 상속하는 기본 클래스."""


def get_sqlalchemy_database_url() -> str:
    """환경변수의 PostgreSQL 주소를 SQLAlchemy용 주소로 바꾼다."""
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """필요할 때만 연결 엔진을 만든다.

    테스트처럼 DATABASE_URL 없이 API를 실행하는 경우에도 기존 메모리 기반
    기능이 동작하도록 import 시점에는 DB 연결을 만들지 않는다.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(get_sqlalchemy_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Repository에서 사용할 SQLAlchemy 세션 팩토리를 반환한다."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI 의존성으로 쓸 수 있는 세션 제공 함수."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
