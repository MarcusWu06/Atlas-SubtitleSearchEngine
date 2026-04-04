import requests
from datetime import UTC, datetime

from app.db.database import get_connection
from app.services.context_service import context_service


class SummaryService:
    MODEL_NAME = "gemma3:4b"
    OLLAMA_URL = "http://localhost:11434/api/chat"
    TIMEOUT = 120

    def summarize_context(
        self,
        video_id: str,
        start_seconds: float,
        query: str | None = None,
        window_before: int = 30,
        window_after: int = 30,
    ) -> dict:
        query_text = (query or "").strip()

        cached = self._get_cached_summary(
            video_id=video_id,
            start_seconds=start_seconds,
            query=query_text,
            window_before=window_before,
            window_after=window_after,
            model_name=self.MODEL_NAME,
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

        summary = self._generate_summary_with_fallback(
            full_text=context["full_text"],
            query=query_text,
        )

        self._save_summary_cache(
            video_id=video_id,
            start_seconds=start_seconds,
            query=query_text,
            window_before=window_before,
            window_after=window_after,
            summary=summary,
            model_name=self.MODEL_NAME,
        )

        return {
            "video_id": context["video_id"],
            "window_start": context["window_start"],
            "window_end": context["window_end"],
            "segment_count": context["segment_count"],
            "full_text": context["full_text"],
            "summary": summary,
        }

    def _generate_summary_with_fallback(self, full_text: str, query: str) -> str:
        text = " ".join(full_text.split())
        if not text:
            return "No subtitle context is available for this time window."

        try:
            return self._call_ollama(text, query)
        except Exception as exc:
            print(f"[summary_service] Ollama failed, fallback enabled: {exc}")
            return self._build_placeholder_summary(text)

    def _call_ollama(self, full_text: str, query: str) -> str:
        if query:
            prompt = (
                "You summarize subtitle context from a YouTube video.\n"
                "Write a concise 1-2 sentence summary of what is being discussed in the subtitle context.\n"
                "Use the search query only as a light hint for the topic, but do not explain relevance to the query.\n"
                "Focus on the actual content of the subtitles.\n"
                "Be factual, clear, and brief.\n"
                "Do not invent details that are not supported by the subtitle context.\n"
                "Do not write phrases like 'this segment is relevant to the query' or 'this subtitle segment mentions'.\n\n"
                f"Search query (topic hint only):\n{query}\n\n"
                f"Subtitle context:\n{full_text}"
            )
        else:
            prompt = (
                "You summarize subtitle context from a YouTube video.\n"
                "Write a concise 1-2 sentence summary of what is being discussed.\n"
                "Focus on the actual content of the subtitles.\n"
                "Be factual, clear, and brief.\n"
                "Do not invent details that are not supported by the subtitle context.\n"
                "Do not repeat transcript fragments word-for-word unless necessary.\n\n"
                f"Subtitle context:\n{full_text}"
            )

        response = requests.post(
            self.OLLAMA_URL,
            json={
                "model": self.MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=self.TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "").strip()

        if not content:
            raise ValueError("Ollama returned empty content")

        return content

    def _build_placeholder_summary(self, full_text: str) -> str:
        compact = " ".join(full_text.split())
        if len(compact) <= 240:
            return compact
        return compact[:240].rstrip() + "..."

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
                    model_name_with_query(model_name, query),
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
        cache_model_name = model_name_with_query(model_name, query)

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
                    cache_model_name,
                    now,
                ),
            )


def model_name_with_query(model_name: str, query: str) -> str:
    return f"{model_name}|query-aware" if query else model_name


summary_service = SummaryService()