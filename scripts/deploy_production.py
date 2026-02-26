#!/usr/bin/env python3
"""
Production Deployment  [Step 2/2: 운영 배포]
=============================================
import_suimi_routes.py 실행 후 생성된 파일들을 운영 환경에 배포.

  Step 1 (GCS): backend/storage/routes/*.json → GCS 업로드
  Step 2 (DB) : scripts/output/import_suimi_*.sql → 운영 VM psql 실행

== 전제 조건 ==
  - gcloud CLI 설치 및 인증 완료  (gcloud auth login)
  - 운영 VM에 psql 설치됨
  - 운영 VM에서 로컬 PostgreSQL 접근 가능 (private VM 내 psql)

== Usage ==
  # GCS 업로드만
  python scripts/deploy_production.py --step gcs \\
    --gcs-bucket riduck-course-data \\
    --vm-name riduck-backend --vm-zone asia-northeast3-a

  # DB 실행만 (GCS 업로드 완료 후)
  python scripts/deploy_production.py --step db \\
    --vm-name riduck-backend --vm-zone asia-northeast3-a \\
    --db-name riduck --db-user postgres

  # 둘 다 순서대로
  python scripts/deploy_production.py --step all \\
    --gcs-bucket riduck-course-data \\
    --vm-name riduck-backend --vm-zone asia-northeast3-a \\
    --db-name riduck --db-user postgres
"""

from __future__ import annotations

import sys
import os
import subprocess
import glob
import argparse
from pathlib import Path

PROJECT_ROOT   = Path(__file__).parent.parent
LOCAL_JSON_DIR = PROJECT_ROOT / "backend" / "storage" / "routes"
SQL_OUTPUT_DIR = Path(__file__).parent / "output"


# ============================================================
# Step 1: JSON → GCS 업로드
# ============================================================

def upload_to_gcs(gcs_bucket: str, gcs_prefix: str = "routes") -> None:
    """
    backend/storage/routes/*.json 을 GCS에 병렬 업로드.
    gsutil -m cp (병렬) 사용.
    """
    json_files = list(LOCAL_JSON_DIR.glob("*.json"))
    if not json_files:
        print(f"ERROR: JSON 파일 없음 → {LOCAL_JSON_DIR}")
        print("먼저 import_suimi_routes.py 를 실행하세요.")
        sys.exit(1)

    gcs_dest = f"gs://{gcs_bucket}/{gcs_prefix}/"
    print(f"GCS 업로드: {len(json_files)}개 파일 → {gcs_dest}")

    cmd = [
        "gsutil", "-m", "cp",
        str(LOCAL_JSON_DIR / "*.json"),
        gcs_dest,
    ]
    print(f"실행: {' '.join(cmd)}")

    # shell=True 로 glob 패턴 처리
    result = subprocess.run(
        f"gsutil -m cp '{LOCAL_JSON_DIR}/*.json' {gcs_dest}",
        shell=True,
        text=True,
    )
    if result.returncode != 0:
        print("ERROR: GCS 업로드 실패")
        sys.exit(1)

    print(f"GCS 업로드 완료: {gcs_dest}")
    print()
    print("다음 단계: backend 환경변수 설정")
    print(f"  STORAGE_TYPE=GCS")
    print(f"  GCS_BUCKET_NAME={gcs_bucket}")


# ============================================================
# Step 2: SQL → 운영 VM psql 실행
# ============================================================

def run_sql_on_vm(
    vm_name:  str,
    vm_zone:  str,
    db_name:  str,
    db_user:  str,
    sql_file: Path,
) -> None:
    """
    gcloud compute scp 로 SQL 파일 VM에 복사 후,
    gcloud compute ssh 로 psql 실행.
    운영 VM 내부에서 로컬 psql 접근 (private VM 구조 기반).
    """
    remote_sql = f"/tmp/{sql_file.name}"

    # 1. SQL 파일 VM으로 복사
    print(f"SQL 파일 VM 복사: {sql_file.name} → {vm_name}:{remote_sql}")
    scp_cmd = [
        "gcloud", "compute", "scp",
        str(sql_file),
        f"{vm_name}:{remote_sql}",
        "--zone", vm_zone,
    ]
    print(f"실행: {' '.join(scp_cmd)}")
    result = subprocess.run(scp_cmd, text=True)
    if result.returncode != 0:
        print("ERROR: SCP 실패")
        sys.exit(1)

    # 2. VM 내에서 psql 실행
    psql_cmd = f"psql -U {db_user} -d {db_name} -f {remote_sql}"
    print(f"\nVM에서 psql 실행: {psql_cmd}")
    ssh_cmd = [
        "gcloud", "compute", "ssh", vm_name,
        "--zone", vm_zone,
        "--command", psql_cmd,
    ]
    print(f"실행: {' '.join(ssh_cmd)}")
    result = subprocess.run(ssh_cmd, text=True)
    if result.returncode != 0:
        print("ERROR: psql 실행 실패")
        sys.exit(1)

    print(f"\nDB 반영 완료!")

    # 3. VM에서 임시 SQL 파일 삭제
    cleanup_cmd = [
        "gcloud", "compute", "ssh", vm_name,
        "--zone", vm_zone,
        "--command", f"rm -f {remote_sql}",
    ]
    subprocess.run(cleanup_cmd, text=True)


# ============================================================
# SQL 파일 자동 탐색
# ============================================================

def _find_latest_sql() -> Path:
    """scripts/output/import_suimi_*.sql 중 가장 최근 파일."""
    candidates = sorted(SQL_OUTPUT_DIR.glob("import_suimi_*.sql"), reverse=True)
    if not candidates:
        print(f"ERROR: SQL 파일 없음 → {SQL_OUTPUT_DIR}")
        print("먼저 import_suimi_routes.py 를 실행하세요.")
        sys.exit(1)
    return candidates[0]


# ============================================================
# 메인
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="운영 배포: JSON→GCS 업로드 + SQL→VM psql 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--step", choices=["gcs", "db", "all"], default="all",
        help="gcs: GCS 업로드만 | db: DB 실행만 | all: 둘 다 (기본)"
    )
    # GCS
    parser.add_argument("--gcs-bucket", default="riduck-course-data",
                        help="GCS 버킷 이름")
    parser.add_argument("--gcs-prefix", default="routes",
                        help="GCS 경로 prefix (기본: routes)")
    # VM
    parser.add_argument("--vm-name",  required=False, help="GCE VM 인스턴스 이름")
    parser.add_argument("--vm-zone",  default="asia-northeast3-a", help="GCE VM zone")
    # DB
    parser.add_argument("--db-name",  default="riduck",   help="DB 이름")
    parser.add_argument("--db-user",  default="postgres",  help="DB 유저")
    parser.add_argument("--sql-file", default=None,
                        help="실행할 SQL 파일 경로 (미지정 시 최신 import_suimi_*.sql 자동 탐색)")
    args = parser.parse_args()

    # DB 스텝에는 vm-name 필수
    if args.step in ("db", "all") and not args.vm_name:
        print("ERROR: --vm-name 이 필요합니다.")
        sys.exit(1)

    sql_file = Path(args.sql_file) if args.sql_file else _find_latest_sql()

    print("=" * 60)
    print("운영 배포 시작")
    if args.step in ("gcs", "all"):
        print(f"  GCS 버킷  : gs://{args.gcs_bucket}/{args.gcs_prefix}/")
    if args.step in ("db", "all"):
        print(f"  VM        : {args.vm_name} ({args.vm_zone})")
        print(f"  DB        : {args.db_name} / {args.db_user}")
        print(f"  SQL 파일  : {sql_file}")
    print("=" * 60)
    print()

    if args.step in ("gcs", "all"):
        upload_to_gcs(args.gcs_bucket, args.gcs_prefix)
        print()

    if args.step in ("db", "all"):
        run_sql_on_vm(
            vm_name  = args.vm_name,
            vm_zone  = args.vm_zone,
            db_name  = args.db_name,
            db_user  = args.db_user,
            sql_file = sql_file,
        )

    print()
    print("=" * 60)
    print("배포 완료!")
    if args.step in ("gcs", "all"):
        print(f"  JSON: gs://{args.gcs_bucket}/{args.gcs_prefix}/")
    if args.step in ("db", "all"):
        print(f"  DB  : {args.vm_name} → {args.db_name}")
    print()
    print("backend 환경변수 확인:")
    print(f"  STORAGE_TYPE=GCS")
    print(f"  GCS_BUCKET_NAME={args.gcs_bucket}")
    print("=" * 60)


if __name__ == "__main__":
    main()
