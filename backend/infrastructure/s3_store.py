from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)


class S3Store:
    def __init__(
        self,
        *,
        bucket: str,
        key: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        import boto3

        self._bucket = bucket
        self._key = key
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def download_to(self, path: Path) -> bool:
        try:
            self._client.download_file(self._bucket, self._key, str(path))
            print(f"s3 download ok: s3://{self._bucket}/{self._key}")
            return True
        except Exception as e:
            print(f"s3 download failed ({e}), using local file")
            return False

    def upload_from(self, path: Path) -> None:
        try:
            self._client.upload_file(str(path), self._bucket, self._key)
            print(f"s3 upload ok: s3://{self._bucket}/{self._key}")
        except Exception as e:
            print(f"s3 upload failed: {e}")

    def get_etag(self) -> str | None:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=self._key)
            etag = resp.get("ETag")
            return etag if isinstance(etag, str) else None
        except Exception:
            return None

    def generate_download_url(self, expires_in: int = 3600) -> str:
        """Generate presigned URL for download (default 1 hour)"""
        return cast(
            str,
            self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": self._key,
                    "ResponseContentDisposition": "attachment; filename=ontology_grnti.json",
                },
                ExpiresIn=expires_in,
            ),
        )
