import asyncio
import json
from pathlib import Path
from typing import Any

import yt_dlp

from app.core.config import settings
from app.services.job_store import job_store


class YouTubeService:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)

    def get_playlist_entries(self, playlist_url: str) -> list[dict[str, str]]:
        return self._extract_playlist_entries(playlist_url)

    def sync_single_video(
            self,
            video_url: str,
            languages: list[str] | None = None,
            include_auto_subtitles: bool = True,
    ) -> dict[str, Any]:
        langs = languages or settings.YTDLP_PREFERRED_SUB_LANGS
        info = self._extract_video_info(video_url)
        video_id = info.get("id")
        if not video_id:
            raise ValueError("Failed to extract video id")

        return self._download_best_subtitles_for_video(
            video_id=video_id,
            video_url=video_url,
            languages=langs,
            include_auto_subtitles=include_auto_subtitles,
        )

    def sync_single_video_by_id(
            self,
            video_id: str,
            languages: list[str] | None = None,
            include_auto_subtitles: bool = True,
    ) -> dict[str, Any]:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        return self.sync_single_video(
            video_url=video_url,
            languages=languages,
            include_auto_subtitles=include_auto_subtitles,
        )




    async def sync_playlist(
        self,
        job_id: str,
        playlist_url: str,
        languages: list[str],
        include_auto_subtitles: bool,
        max_concurrent_downloads: int,
    ) -> None:
        await job_store.update_job(job_id, status="running")

        entries = await asyncio.to_thread(self._extract_playlist_entries, playlist_url)
        if not entries:
            await job_store.update_job(
                job_id,
                status="failed",
                errors=["No videos found in playlist."],
            )
            return

        await job_store.update_job(job_id, total=len(entries))

        semaphore = asyncio.Semaphore(max_concurrent_downloads)
        tasks = [
            self._process_video_with_limit(
                semaphore=semaphore,
                job_id=job_id,
                video_id=entry["id"],
                video_url=entry["url"],
                languages=languages,
                include_auto_subtitles=include_auto_subtitles,
            )
            for entry in entries
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors: list[str] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))

        job = await job_store.get_job(job_id)
        if job is None:
            return

        final_status = "completed" if job.failed == 0 and not errors else "completed"
        all_errors = job.errors + errors
        await job_store.update_job(job_id, status=final_status, errors=all_errors)

    async def _process_video_with_limit(
        self,
        semaphore: asyncio.Semaphore,
        job_id: str,
        video_id: str,
        video_url: str,
        languages: list[str],
        include_auto_subtitles: bool,
    ) -> None:
        async with semaphore:
            try:
                result = await asyncio.to_thread(
                    self._download_best_subtitles_for_video,
                    video_id,
                    video_url,
                    languages,
                    include_auto_subtitles,
                )
                job = await job_store.get_job(job_id)
                if job is None:
                    return
                job.results.append(result)
                job.processed += 1
                if result["status"] == "success":
                    job.succeeded += 1
                else:
                    job.failed += 1
                    if result.get("error"):
                        job.errors.append(f"{video_id}: {result['error']}")
            except Exception as exc:
                job = await job_store.get_job(job_id)
                if job is None:
                    return
                job.processed += 1
                job.failed += 1
                job.errors.append(f"{video_id}: {exc}")

    def _extract_playlist_entries(self, playlist_url: str) -> list[dict[str, str]]:
        opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
            "ignoreerrors": True,
        }
        if settings.YTDLP_COOKIE_FILE:
            opts["cookiefile"] = settings.YTDLP_COOKIE_FILE

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)

        entries = []
        for entry in info.get("entries", []) or []:
            if not entry or not entry.get("id"):
                continue
            entries.append(
                {
                    "id": entry["id"],
                    "url": f"https://www.youtube.com/watch?v={entry['id']}",
                }
            )
        return entries

    def _download_best_subtitles_for_video(
        self,
        video_id: str,
        video_url: str,
        languages: list[str],
        include_auto_subtitles: bool,
    ) -> dict[str, Any]:
        video_dir = settings.SUBTITLES_DIR / video_id
        raw_dir = video_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        info = self._extract_video_info(video_url)

        self._save_json(video_dir / "meta.json", self._build_meta(info, video_url))

        selected = self._choose_subtitle_track(
            subtitles=info.get("subtitles", {}) or {},
            automatic_captions=info.get("automatic_captions", {}) or {},
            languages=languages,
            include_auto_subtitles=include_auto_subtitles,
        )

        if not selected:
            chosen = {
                "video_id": video_id,
                "status": "no_subtitles",
                "selected_type": None,
                "selected_lang": None,
                "saved_files": [],
            }
            self._save_json(video_dir / "chosen.json", chosen)
            return {"video_id": video_id, "status": "no_subtitles"}

        self._download_subtitles(video_url, raw_dir, selected["lang"])

        saved_files = sorted([p.name for p in raw_dir.glob("*") if p.is_file()])

        chosen = {
            "video_id": video_id,
            "status": "success",
            "selected_type": selected["type"],
            "selected_lang": selected["lang"],
            "saved_files": saved_files,
        }
        self._save_json(video_dir / "chosen.json", chosen)

        return {
            "video_id": video_id,
            "title": info.get("title"),
            "status": "success",
            "selected_type": selected["type"],
            "selected_lang": selected["lang"],
            "saved_files": saved_files,
        }

    def _extract_video_info(self, video_url: str) -> dict[str, Any]:
        opts = {
            "quiet": True,
            "skip_download": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "ignoreerrors": False,
        }
        if settings.YTDLP_COOKIE_FILE:
            opts["cookiefile"] = settings.YTDLP_COOKIE_FILE

        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(video_url, download=False)

    def _download_subtitles(self, video_url: str, output_dir: Path, lang: str) -> None:
        outtmpl = str(output_dir / "%(id)s.%(ext)s")
        opts = {
            "quiet": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "outtmpl": outtmpl,
            "ignoreerrors": False,
        }
        if settings.YTDLP_COOKIE_FILE:
            opts["cookiefile"] = settings.YTDLP_COOKIE_FILE

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video_url])

    def _choose_subtitle_track(
        self,
        subtitles: dict[str, list[dict[str, Any]]],
        automatic_captions: dict[str, list[dict[str, Any]]],
        languages: list[str],
        include_auto_subtitles: bool,
    ) -> dict[str, str] | None:
        preferred_langs = [lang for lang in languages if lang != "auto"]

        for lang in preferred_langs:
            if subtitles.get(lang):
                return {"type": "manual", "lang": lang}

        if include_auto_subtitles:
            for lang in preferred_langs:
                if automatic_captions.get(lang):
                    return {"type": "auto", "lang": lang}

        if subtitles:
            lang = next(iter(subtitles.keys()))
            return {"type": "manual", "lang": lang}

        if include_auto_subtitles and automatic_captions:
            lang = next(iter(automatic_captions.keys()))
            return {"type": "auto", "lang": lang}

        return None

    def _build_meta(self, info: dict[str, Any], video_url: str) -> dict[str, Any]:
        return {
            "id": info.get("id"),
            "title": info.get("title"),
            "webpage_url": info.get("webpage_url", video_url),
            "duration": info.get("duration"),
            "channel": info.get("channel"),
            "uploader": info.get("uploader"),
            "language": info.get("language"),
            "subtitles": list((info.get("subtitles") or {}).keys()),
            "automatic_captions": list((info.get("automatic_captions") or {}).keys()),
        }

    def _save_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        def get_playlist_entries(self, playlist_url: str) -> list[dict[str, str]]:
            return self._extract_playlist_entries(playlist_url)



youtube_service = YouTubeService()