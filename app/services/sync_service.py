import asyncio
from datetime import UTC, datetime

from fastapi import HTTPException

from app.db.database import get_connection
from app.services.source_service import source_service
from app.services.subtitle_service import subtitle_service
from app.services.youtube_service import youtube_service


class SyncService:
    async def sync_source(self, source_id: int) -> dict:
        with get_connection() as conn:
            source_row = conn.execute(
                """
                SELECT id, is_active
                FROM sources
                WHERE id = ?
                """,
                (source_id,),
            ).fetchone()

        if not source_row:
            raise HTTPException(status_code=404, detail="Source not found")

        if not bool(source_row["is_active"]):
            raise HTTPException(status_code=400, detail="Source is inactive. Enable it before syncing.")

        return await self._sync_source_async(source_id)


    async def _sync_source_async(self, source_id: int) -> dict:
        source = source_service.get_source_by_id(source_id)

        if source["source_type"] != "playlist":
            raise HTTPException(status_code=400, detail="Only playlist sync is supported for now")

        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (source_id, status)
                VALUES (?, 'running')
                """,
                (source_id,),
            )
            sync_run_id = cursor.lastrowid

        try:
            entries = await asyncio.to_thread(
                youtube_service.get_playlist_entries,
                source["source_url"],
            )
            now = datetime.now(UTC).isoformat()

            total_discovered = len(entries)
            new_videos = 0

            with get_connection() as conn:
                existing_rows = conn.execute(
                    """
                    SELECT video_id
                    FROM source_videos
                    WHERE source_id = ?
                    """,
                    (source_id,),
                ).fetchall()
                existing_video_ids = {row["video_id"] for row in existing_rows}

                seen_video_ids = set()
                discovered_new_video_ids: list[str] = []

                for position, entry in enumerate(entries, start=1):
                    video_id = entry["id"]
                    seen_video_ids.add(video_id)

                    if video_id in existing_video_ids:
                        conn.execute(
                            """
                            UPDATE source_videos
                            SET
                                position = ?,
                                last_seen_at = ?,
                                is_available = 1
                            WHERE source_id = ? AND video_id = ?
                            """,
                            (position, now, source_id, video_id),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO source_videos (
                                source_id, video_id, position, discovered_at, last_seen_at,
                                is_available, sync_status, last_error
                            )
                            VALUES (?, ?, ?, ?, ?, 1, 'pending', NULL)
                            """,
                            (source_id, video_id, position, now, now),
                        )
                        discovered_new_video_ids.append(video_id)
                        new_videos += 1

                if seen_video_ids:
                    placeholders = ",".join("?" for _ in seen_video_ids)
                    conn.execute(
                        f"""
                        UPDATE source_videos
                        SET is_available = 0
                        WHERE source_id = ?
                          AND video_id NOT IN ({placeholders})
                        """,
                        (source_id, *seen_video_ids),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE source_videos
                        SET is_available = 0
                        WHERE source_id = ?
                        """,
                        (source_id,),
                    )

            results = await self._process_new_videos_concurrently(
                source_id=source_id,
                video_ids=discovered_new_video_ids,
                now=now,
            )

            processed = len(results)
            succeeded = sum(1 for item in results if item["sync_status"] == "success")
            failed = processed - succeeded
            errors = [item["error_summary"] for item in results if item["error_summary"]]

            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE sources
                    SET last_synced_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, source_id),
                )

                conn.execute(
                    """
                    UPDATE sync_runs
                    SET
                        status = 'completed',
                        finished_at = ?,
                        total_discovered = ?,
                        new_videos = ?,
                        processed = ?,
                        succeeded = ?,
                        failed = ?,
                        error_summary = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        total_discovered,
                        new_videos,
                        processed,
                        succeeded,
                        failed,
                        "\n".join(errors) if errors else None,
                        sync_run_id,
                    ),
                )

                row = conn.execute(
                    """
                    SELECT *
                    FROM sync_runs
                    WHERE id = ?
                    """,
                    (sync_run_id,),
                ).fetchone()

            return {
                "source_id": source_id,
                "sync_run": self._sync_run_to_dict(row),
            }

        except Exception as exc:
            now = datetime.now(UTC).isoformat()
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE sync_runs
                    SET
                        status = 'failed',
                        finished_at = ?,
                        error_summary = ?
                    WHERE id = ?
                    """,
                    (now, str(exc), sync_run_id),
                )
                row = conn.execute(
                    "SELECT * FROM sync_runs WHERE id = ?",
                    (sync_run_id,),
                ).fetchone()

            return {
                "source_id": source_id,
                "sync_run": self._sync_run_to_dict(row),
            }

    async def _process_new_videos_concurrently(
        self,
        source_id: int,
        video_ids: list[str],
        now: str,
    ) -> list[dict]:
        if not video_ids:
            return []

        max_workers = max(1, youtube_service._semaphore._value)
        semaphore = asyncio.Semaphore(max_workers)

        tasks = [
            self._process_single_new_video(
                semaphore=semaphore,
                source_id=source_id,
                video_id=video_id,
                now=now,
            )
            for video_id in video_ids
        ]

        return await asyncio.gather(*tasks)

    async def _process_single_new_video(
        self,
        semaphore: asyncio.Semaphore,
        source_id: int,
        video_id: str,
        now: str,
    ) -> dict:
        async with semaphore:
            sync_status = "failed"
            last_error = None
            error_summary = None

            try:
                download_result = await asyncio.to_thread(
                    youtube_service.sync_single_video_by_id,
                    video_id,
                )
                download_status = download_result.get("status", "failed")

                if download_status == "success":
                    ingest_result = await asyncio.to_thread(
                        subtitle_service.ingest_video,
                        video_id,
                    )
                    ingest_status = ingest_result.get("status")

                    if ingest_status == "ok":
                        sync_status = "success"
                    else:
                        sync_status = "failed"
                        last_error = f"Ingest failed: {ingest_status}"
                        error_summary = f"{video_id}: {last_error}"

                elif download_status == "no_subtitles":
                    sync_status = "no_subtitles"
                    last_error = "No subtitles available"
                    error_summary = f"{video_id}: {last_error}"

                else:
                    sync_status = "failed"
                    last_error = f"Download failed: {download_status}"
                    error_summary = f"{video_id}: {last_error}"

            except Exception as exc:
                sync_status = "failed"
                last_error = str(exc)
                error_summary = f"{video_id}: {exc}"

            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE source_videos
                    SET sync_status = ?, last_error = ?, last_seen_at = ?
                    WHERE source_id = ? AND video_id = ?
                    """,
                    (sync_status, last_error, now, source_id, video_id),
                )

            return {
                "video_id": video_id,
                "sync_status": sync_status,
                "last_error": last_error,
                "error_summary": error_summary,
            }

    def _sync_run_to_dict(self, row) -> dict:
        return {
            "id": row["id"],
            "source_id": row["source_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "total_discovered": row["total_discovered"],
            "new_videos": row["new_videos"],
            "processed": row["processed"],
            "succeeded": row["succeeded"],
            "failed": row["failed"],
            "error_summary": row["error_summary"],
        }


sync_service = SyncService()