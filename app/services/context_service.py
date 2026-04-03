from app.db.database import get_connection


class ContextService:
    def get_context_window(
        self,
        video_id: str,
        start_seconds: float,
        window_before: int = 30,
        window_after: int = 30,
    ) -> dict:
        window_start = max(0.0, start_seconds - window_before)
        window_end = start_seconds + window_after

        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT start, end, text
                FROM subtitle_segments
                WHERE video_id = ?
                  AND end >= ?
                  AND start <= ?
                ORDER BY start ASC
                """,
                (video_id, window_start, window_end),
            ).fetchall()

        segments = [
            {
                "start": row["start"],
                "end": row["end"],
                "text": row["text"],
            }
            for row in rows
        ]

        full_text = " ".join(segment["text"] for segment in segments)

        return {
            "video_id": video_id,
            "window_start": window_start,
            "window_end": window_end,
            "segment_count": len(segments),
            "segments": segments,
            "full_text": full_text,
        }


context_service = ContextService()