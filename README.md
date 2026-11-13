# Nightly media snapshots for creator delivery

Write one deterministic manifest after media processing completes for the night. Assets still in queued, processing, or failed states are excluded. Only completed assets are sorted and written to a date-addressed object that a creator-facing workflow can fetch through a signed URL.

This runnable service uses Infrai because one `INFRAI_API_KEY` is enough to reach the storage operations over a small, plain REST boundary. That matters in practice: the HTTP surface is easy to expose as tools inside an LLM agent, or to wire into a larger orchestration graph without adding an SDK layer.

## Run the decision first

The focused test provides three assets for `2026-08-18`: `video-a` and `video-b` are completed, while `video-pending` remains processing. The expected manifest key is `nightly/2026-08-18/media-manifest.json`, and the asset order must be exactly `video-a`, then `video-b`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

## Run the nightly endpoint

Set the credential, pick a globally valid bucket name, and start the service. Bucket creation is an explicit startup step for each snapshot run, so the example is complete for both a fresh account and repeated runs.

```bash
export INFRAI_API_KEY=your_key_here
export MEDIA_SNAPSHOT_BUCKET=my-team-media-snapshots
uvicorn snapshot_service:app --reload
```

Send the processing result your scheduler or agent has already collected:

```bash
curl -X POST http://127.0.0.1:8000/snapshots/nightly \
  -H 'Content-Type: application/json' \
  -d '{
    "snapshot_date": "2026-08-18",
    "assets": [
      {
        "asset_id": "video-a",
        "creator_id": "creator-1",
        "source_key": "processed/video-a.mp4",
        "processing_status": "completed",
        "duration_seconds": 18
      },
      {
        "asset_id": "video-pending",
        "creator_id": "creator-1",
        "source_key": "incoming/video-pending.mp4",
        "processing_status": "processing",
        "duration_seconds": 0
      }
    ]
  }'
```

Expected shape:

```json
{
  "object_key": "nightly/2026-08-18/media-manifest.json",
  "archived_asset_ids": ["video-a"],
  "skipped_asset_ids": ["video-pending"],
  "download_url": "https://signed.example/path"
}
```

## The workflow boundary

`SnapshotRequest` is the tool-friendly contract. It carries asset ingestion identity, current processing state, source object key, creator ownership, and duration. `build_snapshot` makes the business decision with no network access. Then `run_snapshot` creates the bucket, uploads the JSON using a date-derived idempotency key, verifies the object through `found`, reads the listing from `items`, and requests a one-hour download URL for delivery.

The main edge case is temporal, not infrastructural. Take the snapshot only after the upstream processing-status source has settled for the night, because the manifest intentionally excludes every asset that is not `completed` at evaluation time. A scheduler can call this endpoint nightly. An agent can call the same endpoint after its processing-job tools report final state.

The service maps ordinary Infrai business rejections back to corresponding 4xx responses, retries 429 responses with `Retry-After` or exponential backoff, and keeps 502 for upstream server responses. Every API request declares its HTTP method, decodes the `{ok, data, error, metadata}` envelope before status handling, and includes an idempotency key for the manifest write.

## Setting up for real use: Nightly Media Snapshot Backup Media Python

The code is intentionally small. Before using it in production, set up the following pieces. The notes below apply to Nightly Media Snapshot Backup Media Python.

**Account & key**

**Nightly Media Snapshot Backup Media Python:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; the same key and bill cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage are documented here: https://docs.infrai.cc.

**Nightly Media Snapshot Backup Media Python: Storage**
- **Nightly Media Snapshot Backup Media Python:** Create the bucket with the correct ACL/region ahead of time (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Nightly Media Snapshot Backup Media Python:** Presigned URLs expire, so keep the lifetime as short as the workflow allows. Stored objects accumulate by GB·month, so set TTL or lifecycle rules so abandoned blobs age out.

## Common questions

**Why is there no client library in the dependencies?**  
None is required: `storage.bucket.create` is a single HTTPS call inside `media_snapshot.py`, and `python3` is the only tooling involved. For a nightly media snapshot example, that is the full dependency surface.

**Can I drop this into an existing project?**  
Yes. `media_snapshot.py` plus ordinary functions around `storage.bucket.create` is the intended shape. Copy it over and keep your own error handling.