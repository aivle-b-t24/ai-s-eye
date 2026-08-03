"""Firebase 로그인 계정과 AI's Eye 역할 claim을 생성하거나 갱신한다."""

from __future__ import annotations

import argparse
import os

import firebase_admin
from firebase_admin import auth, credentials


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", required=True, choices=("store_manager", "admin"))
    parser.add_argument("--store-id")
    parser.add_argument(
        "--password-env",
        default="FIREBASE_TEMP_PASSWORD",
        help="신규 계정 비밀번호가 들어 있는 환경변수 이름",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    credential_path = os.environ.get("FIREBASE_CREDENTIALS")
    if not project_id:
        raise SystemExit("FIREBASE_PROJECT_ID가 필요합니다")
    if args.role == "store_manager" and not args.store_id:
        raise SystemExit("점주 계정에는 --store-id가 필요합니다")

    credential = credentials.Certificate(credential_path) if credential_path else None
    firebase_admin.initialize_app(credential, {"projectId": project_id})

    password = os.environ.get(args.password_env)

    try:
        user = auth.get_user_by_email(args.email)
        update_fields = {"display_name": args.name}
        if password:
            update_fields["password"] = password
        user = auth.update_user(user.uid, **update_fields)
        created = False
    except auth.UserNotFoundError:
        if not password:
            raise SystemExit(
                f"신규 계정 비밀번호 환경변수 {args.password_env}가 필요합니다"
            )
        user = auth.create_user(
            email=args.email,
            password=password,
            display_name=args.name,
            email_verified=True,
        )
        created = True

    claims = {"role": args.role}
    if args.role == "store_manager":
        claims["store_id"] = args.store_id
    auth.set_custom_user_claims(user.uid, claims)
    auth.revoke_refresh_tokens(user.uid)
    action = "created" if created else "updated"
    print(f"{action}: {args.email} role={args.role} store_id={args.store_id or '-'}")


if __name__ == "__main__":
    main()
