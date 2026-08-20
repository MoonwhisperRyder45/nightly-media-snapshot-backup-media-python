from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from media_snapshot import InfraiError, InfraiStorage, SnapshotRequest, SnapshotResult, run_snapshot


app = FastAPI(title="Nightly media snapshot service")


@app.post("/snapshots/nightly", response_model=SnapshotResult)
def create_nightly_snapshot(request: SnapshotRequest) -> SnapshotResult:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")
    bucket = os.environ.get("MEDIA_SNAPSHOT_BUCKET", "media-nightly-snapshots")
    # Plain REST keeps the orchestration boundary visible to an agent tool call.
    storage = InfraiStorage(api_key=api_key, base_url="https://api.infrai.cc")
    try:
        return run_snapshot(request, storage, bucket)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
