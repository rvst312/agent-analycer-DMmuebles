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


class UnsafeFilenameError(ValueError):
    """El nombre de archivo intenta salir del directorio de uploads."""


def safe_key(filename: str) -> str:
    """
    Normaliza un nombre de archivo y garantiza que no escapa de UPLOAD_DIR.
    Colapsa '..', rechaza rutas absolutas y separadores hacia atrás.
    Se usa tanto para el disco local como para la Key de R2.
    """
    if not filename or "\x00" in filename:
        raise UnsafeFilenameError("nombre de archivo vacío o inválido")
    # Colapsa componentes '..' y '.'; quita cualquier '/' inicial (absoluto).
    normalized = os.path.normpath("/" + filename.replace("\\", "/")).lstrip("/")
    if not normalized or normalized.startswith(".."):
        raise UnsafeFilenameError(f"ruta no permitida: {filename!r}")
    return normalized


def local_path(filename: str) -> str:
    """Ruta absoluta en disco para un archivo, validada contra path traversal."""
    key = safe_key(filename)
    base = os.path.realpath(UPLOAD_DIR)
    full = os.path.realpath(os.path.join(base, key))
    if full != base and not full.startswith(base + os.sep):
        raise UnsafeFilenameError(f"ruta fuera de UPLOAD_DIR: {filename!r}")
    return full


def get_url(filename: str) -> str:
    """
    URL to serve a stored file.
    - In cloud mode: route through the backend /files/<filename> proxy so images
      are served even when the R2 bucket has no public access configured.
    - In local dev: serve from the static /uploads mount.
    """
    if is_cloud():
        return f"/files/{filename}"
    return f"/uploads/{filename}"


async def save(file_bytes: bytes, filename: str, content_type: str) -> None:
    """
    Persist a file.
    - Always writes to local disk so the vision agent can read it during this session.
    - If R2/S3 is configured, also uploads to the bucket for durable storage.
    """
    lp = local_path(filename)  # valida path traversal antes de escribir
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    with open(lp, "wb") as fh:
        fh.write(file_bytes)

    if is_cloud():
        try:
            await _s3_upload(file_bytes, safe_key(filename), content_type)
            logger.info(f"storage: uploaded {filename} → R2 bucket '{_BUCKET}'")
        except Exception as e:
            # R2 failure is non-fatal: the file is already on local disk so the
            # vision agent can process it. Log clearly so credentials can be fixed.
            logger.error(f"storage: R2 upload failed for {filename}: {e}")
            logger.warning("storage: continuing with local-only storage — fix R2 credentials to enable durable uploads")


async def fetch(filename: str) -> tuple[bytes, str] | None:
    """
    Retrieve a file's raw bytes + content-type.
    Returns (bytes, content_type) or None if not found anywhere.
    """
    import mimetypes
    # Local disk first
    lp = local_path(filename)
    if os.path.exists(lp):
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(lp, "rb") as f:
            return f.read(), mime
    # R2 fallback
    if is_cloud():
        try:
            import aioboto3  # type: ignore
            session = aioboto3.Session()
            async with session.client("s3", **_s3_client_kwargs()) as s3:
                obj = await s3.get_object(Bucket=_BUCKET, Key=safe_key(filename))
                body = await obj["Body"].read()
            mime = obj.get("ContentType") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return body, mime
        except Exception as e:
            logger.error(f"storage: R2 fetch failed for {filename}: {e}")
    return None


async def delete_prefix(prefix: str) -> int:
    """
    Borra TODOS los archivos cuyo nombre empieza por `prefix` (disco local y,
    si está configurado, R2). Se usa al eliminar un presupuesto para no dejar
    huérfanos (PDF original, páginas del visor, recortes de partidas).
    Devuelve el nº de archivos borrados.
    """
    import glob

    borrados = 0
    safe = safe_key(prefix)
    # Disco local
    base = os.path.realpath(UPLOAD_DIR)
    for path in glob.glob(os.path.join(base, safe + "*")):
        try:
            os.remove(path)
            borrados += 1
        except OSError as e:
            logger.warning(f"storage: no se pudo borrar {path}: {e}")
    # R2: listado por prefijo
    if is_cloud():
        try:
            import aioboto3  # type: ignore
            session = aioboto3.Session()
            async with session.client("s3", **_s3_client_kwargs()) as s3:
                token = None
                while True:
                    kwargs = {"Bucket": _BUCKET, "Prefix": safe}
                    if token:
                        kwargs["ContinuationToken"] = token
                    resp = await s3.list_objects_v2(**kwargs)
                    keys = [o["Key"] for o in resp.get("Contents", [])]
                    if keys:
                        await s3.delete_objects(
                            Bucket=_BUCKET,
                            Delete={"Objects": [{"Key": k} for k in keys]},
                        )
                        borrados += len(keys)
                    if not resp.get("IsTruncated"):
                        break
                    token = resp.get("NextContinuationToken")
            logger.info(f"storage: borrados {borrados} archivos con prefijo '{safe}'")
        except Exception as e:
            logger.warning(f"storage: fallo borrando prefijo '{safe}' en R2: {e}")
    return borrados


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
            await _s3_delete(safe_key(filename))
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
