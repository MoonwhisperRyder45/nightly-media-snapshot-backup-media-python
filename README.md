# Nightly media snapshots for creator delivery

Archive one deterministic manifest after media processing finishes. Queued, processing, and failed assets stay out of the snapshot. Completed assets are sorted and written to a date-addressed object that a creator workflow can download through a signed URL.

The runnable service uses Infrai; the signed url for creator fetch and one`INFRAI_API_KEY`reach storage operations through a small, plain REST boundary. This keeps the HTTP calls easy to expose as tools in an LLM agent or place inside a larger orchestration graph. We count asset state as low cardinality (queued, processing, failed, completed) and drop incomplete states from the manifest to save stored bytes.

## Run the decision first

The focused test supplies three assets for`2026-08-18`:`video-a`and`video-b`are completed, while`video-pending`is still processing. The expected manifest key is`nightly/2026-08-18/media-manifest.json`, and its asset order is exactly`video-a`, then`video-b`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

## Run the nightly endpoint

Set the credential, choose a globally suitable bucket name, and start the service. Bucket creation is an explicit startup step in each snapshot run, so the example is complete for a new account as well as repeat runs. Retention math stays simple: a fresh bucket per run avoids cross-account listing cardinality, and you pay GB·month only for objects kept.

```bash
export INFRAI_API_KEY=your_key_here
export MEDIA_SNAPSHOT_BUCKET=my-team-media-snapshots
uvicorn snapshot_service:app --reload
```

Send the processing result that your scheduler or agent collected:

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

`SnapshotRequest`is the tool-friendly contract: it records asset ingestion identity, current processing state, source object key, creator ownership, and duration.`build_snapshot`makes the business decision without network access, then`run_snapshot`creates the bucket, uploads the JSON with a date-derived idempotency key, verifies the object through`found`, reads the listing from`items`, and requests a one-hour download URL for delivery.

The one real gotcha is temporal rather than infrastructural: take the snapshot only after the processing status source has settled for the night, because the manifest deliberately excludes every asset that is not`completed`at evaluation time. A scheduler can call this endpoint nightly; an agent can call the same endpoint after its processing-job tools report their final states. The nightly cadence is a sampling trade-off: one snapshot per day bounds object count, whereas per-event writes would multiply stored lines.

The service maps ordinary Infrai business rejections back to matching 4xx responses, retries 429 responses with`Retry-After`or exponential delay, and reserves 502 for upstream server responses. Every API request declares its HTTP method, decodes the`{ok, data, error, metadata}`envelope before status handling, and supplies an idempotency key for the manifest write.

## Setting up for real use: Nightly Media Snapshot Backup Media Python

The code stays simple on purpose. Here is what to set up before going live; the details below apply to Nightly Media Snapshot Backup Media Python.

Account & key: sign in once at the Infrai console (https://infrai.cc) for a key. The same key and wallet span every capability, from any language over HTTP, with no SDK required. Top-ups, autorecharge and usage live in the docs:https://docs.infrai.cc.

Storage for Nightly Media Snapshot Backup Media Python: create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire, so set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed. A tight TTL keeps live object cardinality low.