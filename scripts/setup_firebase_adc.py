#!/usr/bin/env python3
"""기존 사용자 ADC를 보존하면서 Firebase 서비스 계정 위임 ADC를 만든다."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


DEFAULT_PROJECT_ID = "project-511b6816-d61a-47ab-b67"
DEFAULT_SERVICE_ACCOUNT = (
    "firebase-adminsdk-fbsvc@"
    "project-511b6816-d61a-47ab-b67.iam.gserviceaccount.com"
)
DEFAULT_SOURCE_ADC = Path("~/.config/gcloud/application_default_credentials.json")
DEFAULT_TARGET_ADC = Path("~/.config/ai-s-eye/firebase-adc.json")
SUPPORTED_SOURCE_TYPES = {"authorized_user", "external_account"}


class SetupError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "기존 Gemini ADC로 Firebase 서비스 계정을 위임하는 별도 ADC를 생성합니다."
        ),
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT)
    parser.add_argument(
        "--source-adc",
        type=Path,
        default=DEFAULT_SOURCE_ADC,
        help="기존 Gemini ADC 경로",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_TARGET_ADC,
        help="생성할 Firebase 위임 ADC 경로",
    )
    return parser.parse_args()


def load_source_adc(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SetupError(
            f"기존 ADC를 찾을 수 없습니다: {path}\n"
            "먼저 gcloud auth application-default login을 실행해 주세요."
        )
    try:
        with path.open(encoding="utf-8") as source_file:
            source = json.load(source_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"기존 ADC를 읽을 수 없습니다: {path}") from exc

    credential_type = source.get("type")
    if credential_type not in SUPPORTED_SOURCE_TYPES:
        raise SetupError(
            "지원하지 않는 기존 ADC 유형입니다: "
            f"{credential_type or 'type 없음'}"
        )
    return source


def build_impersonated_adc(
    source: dict[str, Any],
    service_account: str,
) -> dict[str, Any]:
    return {
        "type": "impersonated_service_account",
        "service_account_impersonation_url": (
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            f"{service_account}:generateAccessToken"
        ),
        "source_credentials": source,
    }


def run_gcloud(arguments: list[str], credential_path: Path | None = None) -> str:
    environment = os.environ.copy()
    if credential_path is not None:
        environment["GOOGLE_APPLICATION_CREDENTIALS"] = str(credential_path)
    completed = subprocess.run(
        ["gcloud", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise SetupError(message or "gcloud 명령을 실행하지 못했습니다")
    return completed.stdout.strip()


def verify_source_adc(path: Path) -> None:
    run_gcloud(["auth", "application-default", "print-access-token"], path)


def verify_impersonated_adc(path: Path) -> None:
    run_gcloud(["auth", "application-default", "print-access-token"], path)


def active_gcloud_account() -> str:
    return run_gcloud(
        ["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
    ) or "확인되지 않음"


def configured_project() -> str:
    return run_gcloud(["config", "get-value", "project"]) or "설정되지 않음"


def write_and_verify(
    payload: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_path.parent, 0o700)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".firebase-adc.",
        suffix=".json.tmp",
        dir=output_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, separators=(",", ":"))
            output_file.write("\n")

        verify_impersonated_adc(temporary_path)
        os.replace(temporary_path, output_path)
        os.chmod(output_path, 0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    if shutil.which("gcloud") is None:
        print("오류: gcloud CLI가 설치되어 있지 않습니다.", file=sys.stderr)
        return 1

    source_path = args.source_adc.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if source_path == output_path:
        print("오류: 기존 ADC와 Firebase ADC 경로는 달라야 합니다.", file=sys.stderr)
        return 1

    try:
        print("[1/4] 기존 Gemini ADC 확인")
        source = load_source_adc(source_path)
        verify_source_adc(source_path)
        print(f"      Google 계정: {active_gcloud_account()}")
        print(f"      현재 프로젝트: {configured_project()}")
        print("      결과: 정상")

        print("[2/4] Firebase 서비스 계정 위임 확인")
        print(f"      대상: {args.service_account}")
        payload = build_impersonated_adc(source, args.service_account)

        print("[3/4] Firebase ADC 생성 및 임시 토큰 발급 테스트")
        write_and_verify(payload, output_path)
        print("      결과: 정상")

        print("[4/4] 로컬 환경변수 안내")
        print(f"      FIREBASE_PROJECT_ID={args.project_id}")
        print(f"      FIREBASE_ADC_HOST_PATH={output_path}")
        print(f"      파일 권한: {oct(output_path.stat().st_mode & 0o777)[2:]}")
        print("\nFirebase 로컬 인증 설정이 완료되었습니다.")
        return 0
    except SetupError as exc:
        print(f"\n오류: {exc}", file=sys.stderr)
        print(
            "\n확인 사항:\n"
            "- 기존 Gemini ADC 로그인이 유효한지\n"
            "- 본인 계정에 Service Account Token Creator 권한이 있는지\n"
            "- IAM Service Account Credentials API가 활성화되어 있는지",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
