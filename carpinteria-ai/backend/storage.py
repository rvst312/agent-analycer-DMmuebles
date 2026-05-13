"""
Storage abstraction: local filesystem (dev) or Cloudflare R2 / S3 (production).

Set these env vars to enable cloud storage:
  S3_BUCKET_NAME        bucket name in R2/S3
  S3_ENDPOINT_URL       https://<account>.r2.cloudflarestorage.com  (or AWS endpoint)
  S3_ACCESS_KEY_ID      R2 API token key ID
  S3_SECRET_ACCESS_KEY  R2 API token secret
  S3_PUBLIC_URL         https://pub-xxx.r2.dev  (public bucket URL or custom domain)
  S3_REGION             "auto" for R2, or AWS region e.g. "eu-west-1"

If none of these are set the module falls back to the local filesystem.
"""

import logging
import os

logger = logging.getLogger(__name__)

_BUCKET     = os.environ.get("S3_BUCKET_NAME", "")
_ENDPOINT   = os.environ.get("S3_ENDPOINT_URL", "")
_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY_ID", "")
_SECRET_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "")
_REGION     = os.environ.get("S3_REGION", "auto")
_PUBLIC_URL = os.environ.get("S3_PUBLIC_URL", "").rstrip("/")

UPLOAD_DIR  = os.environ.get("UPLOAD_DIR", "/app/uploads")


def is_cloud() -> bool:
    """True when R2/S3 credentials are configured."""
    return bool(_BUCKET and _ENDPOINT and _ACCESS_KEY and _SECRET_KEY)


def local_path(filename: str) -> str:
    """Full filesystem path for a given filename."""
    return os.path.join(UPLOAD_DIR, filename)


def get_url(filename: str) -> str:
    """Public URL to serve a stored file."""
    if is_cloud() and _PUBLIC_URL:
        return f"{_PUBLIC_URL}/{filename}"
    return f"/uploads/{filename}"


async def save(file_bytes: bytes, filename: str, content_type: str) -> None:
    """
    Persist a file.
    - Always writes to local disk so the vision agent can read it during this session.
    - If R2/S3 is configured, also uploads to the bucket for durable storage.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(local_path(filename), "wb") as fh:
        fh.write(file_bytes)

    if is_cloud():
        try:
            await _s3_upload(file_bytes, filename, content_type)
            logger.info(f"storage: uploaded {filename} → R2 bucket '{_BUCKET}'")
        except Exception as e:
            # R2 failure is non-fatal: the file is already on local disk so the
            # vision agent can process it. Log clearly so credentials can be fixed.
            logger.error(f"storage: R2 upload failed for {filename}: {e}")
            logger.warning("storage: continuing with local-only storage — fix R2 credentials to enable durable uploads")


async def delete(filename: str) -> None:
    """Remove a file from local disk and, if configured, from the bucket."""
    lp = local_path(filename)
    if os.path.exists(lp):
        try:
            os.remove(lp)
        except Exception as e:
            logger.warning(f"storage: could not delete local file {lp}: {e}")

    if is_cloud():
        try:
            await _s3_delete(filename)
            logger.info(f"storage: deleted {filename} from R2 bucket '{_BUCKET}'")
        except Exception as e:
            logger.warning(f"storage: R2 delete failed for {filename}: {e}")


# ── S3/R2 helpers ─────────────────────────────────────────────────────────────

def _s3_client_kwargs() -> dict:
    return {
        "endpoint_url": _ENDPOINT,
        "aws_access_key_id": _ACCESS_KEY,
        "aws_secret_access_key": _SECRET_KEY,
        "region_name": _REGION,
    }


async def _s3_upload(data: bytes, key: str, content_type: str) -> None:
    import aioboto3  # type: ignore
    session = aioboto3.Session()
    async with session.client("s3", **_s3_client_kwargs()) as s3:
        await s3.put_object(
            Bucket=_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )


async def _s3_delete(key: str) -> None:
    import aioboto3  # type: ignore
    session = aioboto3.Session()
    async with session.client("s3", **_s3_client_kwargs()) as s3:
        await s3.delete_object(Bucket=_BUCKET, Key=key)
