#!/usr/bin/env python3
"""대화형 입력으로 Firebase 본사 관리자 계정을 생성하거나 갱신한다."""

from __future__ import annotations

from getpass import getpass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MIN_PASSWORD_LENGTH = 8


def read_required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("값을 입력해 주세요.")


def read_email() -> str:
    while True:
        email = read_required("이메일: ").lower()
        if EMAIL_PATTERN.fullmatch(email):
            return email
        print("올바른 이메일 형식으로 입력해 주세요.")


def read_password() -> str:
    while True:
        password = getpass("임시 비밀번호: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")
            continue

        confirmation = getpass("임시 비밀번호 확인: ")
        if password == confirmation:
            return password
        print("비밀번호가 일치하지 않습니다. 다시 입력해 주세요.")


def docker_is_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "compose", "version"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def main() -> int:
    print("AI's Eye 본사 관리자 계정 생성")
    print("기존 이메일이면 이름·비밀번호·관리자 권한이 갱신됩니다.\n")

    try:
        name = read_required("이름: ")
        email = read_email()
        password = read_password()
        print(f"\n이름: {name}")
        print(f"이메일: {email}")
        confirmed = input("이 계정을 본사 관리자로 등록할까요? [y/N]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n취소했습니다.")
        return 130

    if confirmed.lower() not in {"y", "yes", "예"}:
        print("취소했습니다.")
        return 0

    if not docker_is_available():
        print(
            "오류: Docker와 Docker Compose를 사용할 수 있는지 확인해 주세요.",
            file=sys.stderr,
        )
        return 1

    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["FIREBASE_TEMP_PASSWORD"] = password
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--build",
        "-e",
        "FIREBASE_TEMP_PASSWORD",
        "api",
        "python",
        "-m",
        "app.provision_firebase_user",
        "--email",
        email,
        "--name",
        name,
        "--role",
        "admin",
    ]

    print("\nFirebase 관리자 계정을 등록하는 중입니다...")
    try:
        result = subprocess.run(
            command,
            cwd=repository_root,
            env=environment,
            check=False,
        )
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130
    finally:
        environment.pop("FIREBASE_TEMP_PASSWORD", None)

    if result.returncode != 0:
        print("\n계정 등록에 실패했습니다. 위 오류를 확인해 주세요.", file=sys.stderr)
        return result.returncode

    print("\n본사 관리자 계정 등록이 완료되었습니다.")
    print("대시보드 로그인 화면에서 방금 등록한 이메일과 비밀번호를 사용하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
