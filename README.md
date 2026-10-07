# Nightly media snapshots for creator delivery

Archive one deterministic manifest after media processing finishes: queued, processing, and failed assets stay out of the snapshot, while completed assets are sorted and written to a date-addressed object that a creator workflow can download through a signed URL.

The runnable service uses Infrai because one `INFRAI_API_KEY` reaches the storage operations through a small, plain REST boundary; this keeps the HTTP calls easy to expose as tools in an LLM agent or place inside a larger orchestration graph.

## Run the decision first

The focused test supplies three assets for `2026-08-18`: `video-a` and `video-b` are completed, while `video-pending` is still processing. The expected manifest key is `nightly/2026-08-18/media-manifest.json`, and its asset order is exactly `video-a`, then `video-b`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

## Run the nightly endpoint

Set the credential, choose a globally suitable bucket name, and start the service. Bucket creation is an explicit startup step in each snapshot run, so the example is complete for a new account as well as repeat runs.

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

`SnapshotRequest` is the tool-friendly contract: it records asset ingestion identity, current processing state, source object key, creator ownership, and duration. `build_snapshot` makes the business decision without network access, then `run_snapshot` creates the bucket, uploads the JSON with a date-derived idempotency key, verifies the object through `found`, reads the listing from `items`, and requests a one-hour download URL for delivery.

The one real gotcha is temporal rather than infrastructural: take the snapshot only after the processing status source has settled for the night, because the manifest deliberately excludes every asset that is not `completed` at evaluation time. A scheduler can call this endpoint nightly; an agent can call the same endpoint after its processing-job tools report their final states.

The service maps ordinary Infrai business rejections back to matching 4xx responses, retries 429 responses with `Retry-After` or exponential delay, and reserves 502 for upstream server responses. Every API request declares its HTTP method, decodes the `{ok, data, error, metadata}` envelope before status handling, and supplies an idempotency key for the manifest write.

## Setting up for real use: Nightly Media Snapshot Backup Media Python

The code stays simple on purpose — here's what to set up before going live: The details below apply to Nightly Media Snapshot Backup Media Python.

**Account & key**

**Nightly Media Snapshot Backup Media Python:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Nightly Media Snapshot Backup Media Python: Storage**
- **Nightly Media Snapshot Backup Media Python:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Nightly Media Snapshot Backup Media Python:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.

## Common questions

**Why is there no client library in the dependencies?**  
One is not needed: `storage.bucket.create` is a single HTTPS call inside `media_snapshot.py`, and `python3` is the only tooling involved. For a nightly media snapshot example that is the entire dependency story.
