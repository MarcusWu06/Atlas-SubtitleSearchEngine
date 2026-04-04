from app.db.database import get_connection


class ArchiveService:
    def save_moment(self, payload) -> dict:
        normalized_query = (payload.query or "").strip() or None

        with get_connection() as conn:
            existing = conn.execute(
                """
                SELECT
                    id,
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url,
                    created_at
                FROM saved_items
                WHERE item_type = ?
                  AND video_id = ?
                  AND start_seconds = ?
                  AND (
                        (query IS NULL AND ? IS NULL)
                     OR query = ?
                  )
                LIMIT 1
                """,
                (
                    "moment",
                    payload.video_id,
                    payload.start_seconds,
                    normalized_query,
                    normalized_query,
                ),
            ).fetchone()

            if existing:
                return dict(existing)

            cursor = conn.execute(
                """
                INSERT INTO saved_items (
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "moment",
                    payload.video_id,
                    payload.title,
                    payload.channel,
                    normalized_query,
                    payload.start_seconds,
                    payload.end_seconds,
                    payload.display_text,
                    payload.watch_url,
                ),
            )
            conn.commit()

            row = conn.execute(
                """
                SELECT
                    id,
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url,
                    created_at
                FROM saved_items
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()

        return dict(row)

    def save_video(self, payload) -> dict:
        normalized_query = (payload.query or "").strip() or None

        with get_connection() as conn:
            existing = conn.execute(
                """
                SELECT
                    id,
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url,
                    created_at
                FROM saved_items
                WHERE item_type = ?
                  AND video_id = ?
                LIMIT 1
                """,
                ("video", payload.video_id),
            ).fetchone()

            if existing:
                return dict(existing)

            cursor = conn.execute(
                """
                INSERT INTO saved_items (
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "video",
                    payload.video_id,
                    payload.title,
                    payload.channel,
                    normalized_query,
                    None,
                    None,
                    payload.display_text,
                    payload.watch_url,
                ),
            )
            conn.commit()

            row = conn.execute(
                """
                SELECT
                    id,
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url,
                    created_at
                FROM saved_items
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()

        return dict(row)

    def list_saved_items(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    item_type,
                    video_id,
                    title,
                    channel,
                    query,
                    start_seconds,
                    end_seconds,
                    display_text,
                    watch_url,
                    created_at
                FROM saved_items
                ORDER BY datetime(created_at) DESC, id DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def delete_saved_item(self, item_id: int) -> None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM saved_items
                WHERE id = ?
                """,
                (item_id,),
            ).fetchone()

            if not row:
                raise ValueError("Saved item not found")

            conn.execute(
                """
                DELETE FROM saved_items
                WHERE id = ?
                """,
                (item_id,),
            )
            conn.commit()


archive_service = ArchiveService()