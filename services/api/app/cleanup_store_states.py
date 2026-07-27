"""보관기간이 지난 StoreState 이력을 안전하게 정리하는 수동 도구."""

import argparse
from datetime import datetime, timedelta, timezone

from .config import get_settings
from .db_repository import DatabaseRepository


DEFAULT_RETENTION_DAYS = 7


def retention_cutoff(
    retention_days: int,
    now: datetime | None = None,
) -> datetime:
    """보관일수를 기준으로 삭제 경계 시각을 계산한다."""
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    current_time = now or datetime.now(timezone.utc)
    return current_time - timedelta(days=retention_days)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "보관기간이 지난 StoreState 이력을 정리합니다. "
            "기본 실행은 삭제하지 않고 대상 건수만 확인합니다."
        )
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"보관할 일수 (기본값: {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="대상 이력을 실제로 삭제합니다.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL이 설정되지 않아 정리 대상을 확인할 수 없습니다.")
        return 2

    try:
        cutoff = retention_cutoff(args.older_than_days)
    except ValueError as exc:
        print(str(exc))
        return 2

    repository = DatabaseRepository()
    target_count = repository.count_expired_store_states(cutoff)
    print(
        f"기준 시각: {cutoff.isoformat()} / "
        f"정리 대상: {target_count}건 / "
        "매장별 최신 상태 1건은 보존"
    )

    if not args.apply:
        print("Dry-run 완료: 실제 데이터는 삭제하지 않았습니다.")
        return 0

    deleted_count = repository.delete_expired_store_states(cutoff)
    print(f"정리 완료: {deleted_count}건 삭제")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
