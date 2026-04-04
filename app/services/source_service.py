from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

from app.db.database import get_connection
from app.models.schemas import SourceCreateRequest
from pathlib import Path
from app.core.config import settings


class SourceService:
    def create_source(self, payload: SourceCreateRequest) -> dict:
        source_url = str(payload.source_url)
        source_key = self._build_source_key(payload.source_type, source_url)

        with get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM sources WHERE source_key = ?",
                (source_key,),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Source already exists")

            cursor = conn.execute(
                """
                INSERT INTO sources (source_type, source_url, source_key, title)
                VALUES (?, ?, ?, ?)
                """,
                (payload.source_type, source_url, source_key, payload.title),
            )
            source_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()

        return self._row_to_dict(row)

    def list_sources(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sources
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        return [self._row_to_dict(row) for row in rows]

    def get_source_by_id(self, source_id: int) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Source not found")

            video_count = conn.execute(
                "SELECT COUNT(*) AS count FROM source_videos WHERE source_id = ?",
                (source_id,),
            ).fetchone()["count"]

            available_video_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM source_videos
                WHERE source_id = ? AND is_available = 1
                """,
                (source_id,),
            ).fetchone()["count"]

            sync_run_count = conn.execute(
                "SELECT COUNT(*) AS count FROM sync_runs WHERE source_id = ?",
                (source_id,),
            ).fetchone()["count"]

        data = self._row_to_dict(row)
        data["video_count"] = video_count
        data["available_video_count"] = available_video_count
        data["sync_run_count"] = sync_run_count
        return data

    def list_source_videos(self, source_id: int) -> list[dict]:
        self.get_source_by_id(source_id)

        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM source_videos
                WHERE source_id = ?
                ORDER BY position ASC, id ASC
                """,
                (source_id,),
            ).fetchall()

        return [self._source_video_row_to_dict(row) for row in rows]

    def list_sync_runs(self, source_id: int) -> list[dict]:
        self.get_source_by_id(source_id)

        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sync_runs
                WHERE source_id = ?
                ORDER BY id DESC
                """,
                (source_id,),
            ).fetchall()

        return [self._sync_run_row_to_dict(row) for row in rows]

    def delete_source(self, source_id: int) -> None:
        self.get_source_by_id(source_id)

        with get_connection() as conn:
            source_video_rows = conn.execute(
                """
                SELECT video_id
                FROM source_videos
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchall()
            source_video_ids = [row["video_id"] for row in source_video_rows]

            orphan_video_ids: list[str] = []
            for video_id in source_video_ids:
                ref_count = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM source_videos
                    WHERE video_id = ?
                    """,
                    (video_id,),
                ).fetchone()["count"]

                if ref_count == 1:
                    orphan_video_ids.append(video_id)

            conn.execute(
                "DELETE FROM source_videos WHERE source_id = ?",
                (source_id,),
            )
            conn.execute(
                "DELETE FROM sync_runs WHERE source_id = ?",
                (source_id,),
            )
            conn.execute(
                "DELETE FROM sources WHERE id = ?",
                (source_id,),
            )

            for video_id in orphan_video_ids:
                conn.execute(
                    "DELETE FROM subtitle_segments_fts WHERE video_id = ?",
                    (video_id,),
                )
                conn.execute(
                    "DELETE FROM subtitle_segments WHERE video_id = ?",
                    (video_id,),
                )
                conn.execute(
                    "DELETE FROM videos WHERE id = ?",
                    (video_id,),
                )

        # delete local subtitle folders after DB cleanup
        subtitles_root = settings.SUBTITLES_DIR
        for video_id in orphan_video_ids:
            video_dir = subtitles_root / video_id
            if video_dir.exists() and video_dir.is_dir():
                for path in sorted(video_dir.rglob("*"), reverse=True):
                    if path.is_file() or path.is_symlink():
                        path.unlink(missing_ok=True)
                    elif path.is_dir():
                        path.rmdir()
                video_dir.rmdir()

    def _build_source_key(self, source_type: str, source_url: str) -> str:
        parsed = urlparse(source_url)

        if source_type == "playlist":
            playlist_id = parse_qs(parsed.query).get("list", [None])[0]
            if not playlist_id:
                raise HTTPException(status_code=400, detail="Invalid playlist URL")
            return f"playlist:{playlist_id}"

        if source_type == "channel":
            path = parsed.path.rstrip("/")
            if not path:
                raise HTTPException(status_code=400, detail="Invalid channel URL")
            return f"channel:{path}"

        raise HTTPException(status_code=400, detail="Unsupported source type")

    def _row_to_dict(self, row) -> dict:
        return {
            "id": row["id"],
            "source_type": row["source_type"],
            "source_url": row["source_url"],
            "source_key": row["source_key"],
            "title": row["title"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_synced_at": row["last_synced_at"],
        }

    def _source_video_row_to_dict(self, row) -> dict:
        return {
            "id": row["id"],
            "source_id": row["source_id"],
            "video_id": row["video_id"],
            "position": row["position"],
            "discovered_at": row["discovered_at"],
            "last_seen_at": row["last_seen_at"],
            "is_available": bool(row["is_available"]),
            "sync_status": row["sync_status"],
            "last_error": row["last_error"],
        }

    def _sync_run_row_to_dict(self, row) -> dict:
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

    def update_source(self, source_id: int, payload) -> dict:
        updates = []
        values = []

        if payload.title is not None:
            title = payload.title.strip()
            updates.append("title = ?")
            values.append(title if title else None)

        if payload.is_active is not None:
            updates.append("is_active = ?")
            values.append(1 if payload.is_active else 0)

        if not updates:
            return self.get_source_by_id(source_id)

        values.append(source_id)

        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()

            if not row:
                raise ValueError("Source not found")

            conn.execute(
                f"""
                UPDATE sources
                SET {", ".join(updates)}
                WHERE id = ?
                """,
                values,
            )
            conn.commit()

        return self.get_source_by_id(source_id)


source_service = SourceService()