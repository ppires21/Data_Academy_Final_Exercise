#!/usr/bin/env python3
"""
S3 Integration — Raw CSV Uploader
---------------------------------
- Uploads raw CSV files into S3 with partitioned paths:
  s3://<bucket>/raw/year=YYYY/month=MM/day=DD/{customers|products|transactions}/<file_with_version>.csv
- Implements simple file versioning by appending a UTC timestamp to the filename.
- Adds basic exponential backoff retry logic.

Run:
    python src/cloud/s3_handler.py

You should only need to change S3_BUCKET once below.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# -----------------------
# Configuration
# -----------------------
S3_BUCKET = "ctw04557-ppires-academy-finalexercise-bucket" 

# -----------------------
# Logging
# -----------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# -----------------------
# Constants
# -----------------------
LOCAL_DIR = Path("data/raw")
BASE_PREFIX = "raw"
RAW_FILE_MAP: Dict[str, str] = {
    "clientes.csv": "customers",
    "produtos.csv": "products",
    "transacoes.csv": "transactions",
}

MAX_RETRIES = 5
INITIAL_BACKOFF_SECS = 1.0


def _s3_client() -> boto3.client:
    """
    Create an S3 client using the default AWS credential/region chain:
    - ~/.aws/credentials or AWS SSO/profile you’ve already configured
    - EC2/ECS role, etc.
    No env vars needed at runtime.
    """
    return boto3.client("s3")


def _utc_version_tag() -> str:
    """UTC timestamp tag for filename versioning, e.g., 20251024T152530Z"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _partition_path(run_date: Optional[date] = None) -> str:
    """Partition path raw/year=YYYY/month=MM/day=DD"""
    d = run_date or date.today()
    return f"{BASE_PREFIX}/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}"


def _upload_with_retries(
    s3,
    file_path: Path,
    bucket: str,
    key: str,
    extra_args: Optional[dict] = None,
):
    """Upload with exponential backoff retries."""
    extra_args = extra_args or {}
    attempt = 0
    backoff = INITIAL_BACKOFF_SECS

    while True:
        try:
            s3.upload_file(
                Filename=str(file_path),
                Bucket=bucket,
                Key=key,
                ExtraArgs=extra_args,
            )
            return
        except (BotoCoreError, ClientError) as e:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            log.warning(
                f"Upload failed for s3://{bucket}/{key} (attempt {attempt}/{MAX_RETRIES}): {e}. "
                f"Retrying in {backoff:.1f}s..."
            )
            time.sleep(backoff)
            backoff *= 2


def upload_raw_csvs(bucket: str, run_date: Optional[date] = None) -> None:
    """
    Upload raw CSVs to:
      raw/year=YYYY/month=MM/day=DD/<entity>/<original_stem>_<UTCVER>.csv
    where <entity> in {customers, products, transactions}
    """
    if not bucket or bucket == "YOUR_S3_BUCKET_NAME_HERE":
        raise ValueError(
            "Please set S3_BUCKET at the top of src/cloud/s3_handler.py to your real bucket name."
        )

    partition = _partition_path(run_date)
    version = _utc_version_tag()
    s3 = _s3_client()

    for local_name, entity in RAW_FILE_MAP.items():
        src = LOCAL_DIR / local_name
        if not src.exists():
            raise FileNotFoundError(f"Missing local file: {src}")

        versioned_name = f"{src.stem}_{version}.csv"
        key = f"{partition}/{entity}/{versioned_name}"

        extra_args = {
            "ContentType": "text/csv",
            "Metadata": {
                "source": "shopflow-data-generator",
                "version_tag": version,
                "entity": entity,
            },
        }

        log.info(f"Uploading {src} → s3://{bucket}/{key}")
        _upload_with_retries(s3, src, bucket, key, extra_args=extra_args)

    log.info("✅ All raw CSVs uploaded to S3.")


def main():
    try:
        # Explanation: uses today’s date automatically; you don’t pass anything at runtime.
        upload_raw_csvs(bucket=S3_BUCKET, run_date=None)
    except Exception as e:
        log.exception(f"❌ S3 upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
