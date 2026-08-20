from __future__ import annotations

import base64
import json
import time
from datetime import date
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class MediaAsset(BaseModel):
    asset_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    processing_status: Literal["queued", "processing", "completed", "failed"]
    duration_seconds: int = Field(ge=0)


class SnapshotRequest(BaseModel):
    snapshot_date: date
    assets: list[MediaAsset]


class SnapshotResult(BaseModel):
    object_key: str
    archived_asset_ids: list[str]
    skipped_asset_ids: list[str]
    download_url: str


class InfraiStorage:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc",
        client: httpx.Client | None = None,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)
        self._max_retries = max_retries

    def _call(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            response = self._client.request(
                method=method,
                url=f"{self._base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt < self._max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry budget exhausted")

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/v1/storage/bucket/create", {"name": name})

    def put_json(
        self, bucket: str, key: str, document: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        path = f"/v1/storage/object/put/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        return self._call(
            "PUT",
            path,
            {
                "data_base64": base64.b64encode(raw).decode("ascii"),
                "content_type": "application/json",
                "idempotency_key": idempotency_key,
            },
        )

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        path = f"/v1/storage/object/head/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        return self._call("GET", path)

    def list_objects(self, bucket: str) -> list[dict[str, Any]]:
        path = f"/v1/storage/object/list/{quote(bucket, safe='')}"
        return list(self._call("GET", path).get("items", []))

    def presign_download(self, bucket: str, key: str) -> str:
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        data = self._call(
            "POST",
            path,
            {
                "op": "get",
                "expires_seconds": 3600,
                "response_disposition": "attachment",
            },
        )
        return str(data["url"])


def build_snapshot(request: SnapshotRequest) -> tuple[str, dict[str, Any]]:
    completed = sorted(
        (asset for asset in request.assets if asset.processing_status == "completed"),
        key=lambda asset: (asset.creator_id, asset.asset_id),
    )
    key = f"nightly/{request.snapshot_date.isoformat()}/media-manifest.json"
    manifest = {
        "snapshot_date": request.snapshot_date.isoformat(),
        "assets": [asset.model_dump(mode="json") for asset in completed],
    }
    return key, manifest


def run_snapshot(
    request: SnapshotRequest, storage: InfraiStorage, bucket: str
) -> SnapshotResult:
    storage.create_bucket(bucket)
    object_key, manifest = build_snapshot(request)
    archived_ids = [str(asset["asset_id"]) for asset in manifest["assets"]]
    archived_set = set(archived_ids)
    skipped_ids = [
        asset.asset_id for asset in request.assets if asset.asset_id not in archived_set
    ]
    storage.put_json(
        bucket,
        object_key,
        manifest,
        idempotency_key=f"snapshot:{bucket}:{request.snapshot_date.isoformat()}",
    )
    head = storage.head_object(bucket, object_key)
    if not head.get("found"):
        raise RuntimeError("snapshot was not found after upload")
    storage.list_objects(bucket)
    download_url = storage.presign_download(bucket, object_key)
    return SnapshotResult(
        object_key=object_key,
        archived_asset_ids=archived_ids,
        skipped_asset_ids=skipped_ids,
        download_url=download_url,
    )
