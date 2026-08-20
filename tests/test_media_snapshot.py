from datetime import date

from media_snapshot import MediaAsset, SnapshotRequest, build_snapshot


def test_snapshot_archives_only_completed_assets_in_stable_order() -> None:
    request = SnapshotRequest(
        snapshot_date=date(2026, 8, 18),
        assets=[
            MediaAsset(
                asset_id="video-b",
                creator_id="creator-2",
                source_key="processed/video-b.mp4",
                processing_status="completed",
                duration_seconds=42,
            ),
            MediaAsset(
                asset_id="video-pending",
                creator_id="creator-1",
                source_key="incoming/video-pending.mp4",
                processing_status="processing",
                duration_seconds=0,
            ),
            MediaAsset(
                asset_id="video-a",
                creator_id="creator-1",
                source_key="processed/video-a.mp4",
                processing_status="completed",
                duration_seconds=18,
            ),
        ],
    )

    key, manifest = build_snapshot(request)

    assert key == "nightly/2026-08-18/media-manifest.json"
    assert [asset["asset_id"] for asset in manifest["assets"]] == [
        "video-a",
        "video-b",
    ]
