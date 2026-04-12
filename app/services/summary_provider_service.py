import os
from typing import Optional

import requests
from openai import OpenAI


class SummaryProviderService:
    OLLAMA_URL = "http://localhost:11434/api/chat"
    OLLAMA_TIMEOUT = 120
    DEFAULT_LOCAL_MODEL = "gemma3:4b"

    def __init__(self) -> None:
        self.provider = os.getenv("SUMMARY_PROVIDER", "local").strip().lower()
        self.openai_model = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5-mini").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.local_model = os.getenv("LOCAL_SUMMARY_MODEL", self.DEFAULT_LOCAL_MODEL).strip()

        self.client: Optional[OpenAI] = None
        if self.provider == "openai":
            if not self.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is missing")
            self.client = OpenAI(api_key=self.openai_api_key)

    def get_active_model_name(self, query: str) -> str:
        base = self.openai_model if self.provider == "openai" else self.local_model
        return f"{base}|query-aware" if (query or "").strip() else base

    def summarize(
        self,
        query: str,
        full_text: str,
        window_start: float,
        window_end: float,
    ) -> str:
        if self.provider == "openai":
            return self._summarize_with_openai(
                query=query,
                full_text=full_text,
                window_start=window_start,
                window_end=window_end,
            )

        return self._summarize_with_local(
            query=query,
            full_text=full_text,
            window_start=window_start,
            window_end=window_end,
        )

    def _summarize_with_openai(
        self,
        query: str,
        full_text: str,
        window_start: float,
        window_end: float,
    ) -> str:
        assert self.client is not None

        text = " ".join((full_text or "").split())
        if not text:
            return "No subtitle context is available for this time window."

        instructions = (
            "You summarize subtitle context from a YouTube video. "
            "Write a concise 1-2 sentence summary of what is being discussed in the subtitle context. "
            "Use the search query only as a light hint for the topic, but do not explain relevance to the query. "
            "Focus on the actual content of the subtitles. "
            "Be factual, clear, and brief. "
            "Do not invent details that are not supported by the subtitle context. "
            "Do not write phrases like 'this segment is relevant to the query' or "
            "'this subtitle segment mentions'."
        )

        if query.strip():
            user_input = (
                f"Search query (topic hint only):\n{query.strip()}\n\n"
                f"Context window: {window_start:.1f}s to {window_end:.1f}s\n\n"
                f"Subtitle context:\n{text}"
            )
        else:
            user_input = (
                f"Context window: {window_start:.1f}s to {window_end:.1f}s\n\n"
                f"Subtitle context:\n{text}"
            )

        response = self.client.responses.create(
            model=self.openai_model,
            instructions=instructions,
            input=user_input,
            max_output_tokens=100,
        )

        content = (response.output_text or "").strip()
        if not content:
            raise RuntimeError("OpenAI returned empty content")
        return content

    def _summarize_with_local(
        self,
        query: str,
        full_text: str,
        window_start: float,
        window_end: float,
    ) -> str:
        text = " ".join((full_text or "").split())
        if not text:
            return "No subtitle context is available for this time window."

        try:
            return self._call_ollama(text, query)
        except Exception as exc:
            print(f"[summary_provider_service] Ollama failed, fallback enabled: {exc}")
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
                "model": self.local_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=self.OLLAMA_TIMEOUT,
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


summary_provider_service = SummaryProviderService()