from datetime import UTC, datetime

from app.db.database import get_connection
from app.services.context_service import context_service
from app.services.summary_provider_service import summary_provider_service


class SummaryService:
    def summarize_context(
        self,
        video_id: str,
        start_seconds: float,
        query: str | None = None,
        window_before: int = 30,
        window_after: int = 30,
    ) -> dict:
        query_text = (query or "").strip()
        active_model_name = summary_provider_service.get_active_model_name(query_text)

        cached = self._get_cached_summary(
            video_id=video_id,
            start_seconds=start_seconds,
            query=query_text,
            window_before=window_before,
            window_after=window_after,
            model_name=active_model_name,
        )

        context = context_service.get_context_window(
            video_id=video_id,
            start_seconds=start_seconds,
            window_before=window_before,
            window_after=window_after,
        )

        if cached:
            return {
                "video_id": context["video_id"],
                "window_start": context["window_start"],
                "window_end": context["window_end"],
                "segment_count": context["segment_count"],
                "full_text": context["full_text"],
                "summary": cached["summary"],
            }

        summary = summary_provider_service.summarize(
            query=query_text,
            full_text=context["full_text"],
            window_start=context["window_start"],
            window_end=context["window_end"],
        )

        self._save_summary_cache(
            video_id=video_id,
            start_seconds=start_seconds,
            query=query_text,
            window_before=window_before,
            window_after=window_after,
            summary=summary,
            model_name=active_model_name,
        )

        return {
            "video_id": context["video_id"],
            "window_start": context["window_start"],
            "window_end": context["window_end"],
            "segment_count": context["segment_count"],
            "full_text": context["full_text"],
            "summary": summary,
        }

    def _get_cached_summary(
        self,
        video_id: str,
        start_seconds: float,
        query: str,
        window_before: int,
        window_after: int,
        model_name: str,
    ) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT summary, model_name, created_at
                FROM summary_cache
                WHERE video_id = ?
                  AND start_seconds = ?
                  AND window_before = ?
                  AND window_after = ?
                  AND model_name = ?
                LIMIT 1
                """,
                (
                    video_id,
                    start_seconds,
                    window_before,
                    window_after,
                    model_name,
                ),
            ).fetchone()

        if not row:
            return None

        return {
            "summary": row["summary"],
            "model_name": row["model_name"],
            "created_at": row["created_at"],
        }

    def _save_summary_cache(
        self,
        video_id: str,
        start_seconds: float,
        query: str,
        window_before: int,
        window_after: int,
        summary: str,
        model_name: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO summary_cache (
                    video_id, start_seconds, window_before, window_after,
                    summary, model_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, start_seconds, window_before, window_after, model_name)
                DO UPDATE SET
                    summary = excluded.summary,
                    created_at = excluded.created_at
                """,
                (
                    video_id,
                    start_seconds,
                    window_before,
                    window_after,
                    summary,
                    model_name,
                    now,
                ),
            )


summary_service = SummaryService()