import json

from app.core.config import settings
from app.db.database import get_connection
from app.utils.vtt_parser import parse_vtt


class SubtitleService:
    def ingest_downloaded_subtitles(self) -> dict:
        subtitles_root = settings.SUBTITLES_DIR
        if not subtitles_root.exists():
            return {"videos": 0, "segments": 0}

        total_videos = 0
        total_segments = 0

        for video_dir in subtitles_root.iterdir():
            if not video_dir.is_dir():
                continue

            chosen_path = video_dir / "chosen.json"
            meta_path = video_dir / "meta.json"
            raw_dir = video_dir / "raw"

            if not chosen_path.exists() or not meta_path.exists() or not raw_dir.exists():
                continue

            chosen = json.loads(chosen_path.read_text(encoding="utf-8"))
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

            if chosen.get("status") != "success":
                continue

            saved_files = chosen.get("saved_files", [])
            if not saved_files:
                continue

            subtitle_file = raw_dir / saved_files[0]
            if not subtitle_file.exists():
                continue

            content = subtitle_file.read_text(encoding="utf-8", errors="ignore")
            segments = parse_vtt(content)
            if not segments:
                continue

            self._upsert_video(meta, chosen, subtitle_file)
            inserted = self._replace_segments(meta["id"], segments)

            total_videos += 1
            total_segments += inserted

        return {"videos": total_videos, "segments": total_segments}

    def _upsert_video(self, meta: dict, chosen: dict, subtitle_file) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO videos (
                    id, title, webpage_url, duration, channel, uploader, language,
                    selected_subtitle_type, selected_subtitle_lang, subtitle_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    webpage_url = excluded.webpage_url,
                    duration = excluded.duration,
                    channel = excluded.channel,
                    uploader = excluded.uploader,
                    language = excluded.language,
                    selected_subtitle_type = excluded.selected_subtitle_type,
                    selected_subtitle_lang = excluded.selected_subtitle_lang,
                    subtitle_path = excluded.subtitle_path
                """,
                (
                    meta.get("id"),
                    meta.get("title"),
                    meta.get("webpage_url"),
                    meta.get("duration"),
                    meta.get("channel"),
                    meta.get("uploader"),
                    meta.get("language"),
                    chosen.get("selected_type"),
                    chosen.get("selected_lang"),
                    str(subtitle_file),
                ),
            )

    def _replace_segments(self, video_id: str, segments: list[dict]) -> int:
        with get_connection() as conn:
            old_ids = conn.execute(
                "SELECT id FROM subtitle_segments WHERE video_id = ?",
                (video_id,),
            ).fetchall()

            if old_ids:
                segment_ids = [str(row["id"]) for row in old_ids]
                conn.execute(
                    f"DELETE FROM subtitle_segments_fts WHERE segment_id IN ({','.join('?' * len(segment_ids))})",
                    segment_ids,
                )

            conn.execute("DELETE FROM subtitle_segments WHERE video_id = ?", (video_id,))

            rows = [
                (video_id, seg["start"], seg["end"], seg["duration"], seg["text"])
                for seg in segments
            ]
            conn.executemany(
                """
                INSERT INTO subtitle_segments (video_id, start, end, duration, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

            inserted_rows = conn.execute(
                """
                SELECT id, video_id, text
                FROM subtitle_segments
                WHERE video_id = ?
                ORDER BY id
                """,
                (video_id,),
            ).fetchall()

            conn.executemany(
                """
                INSERT INTO subtitle_segments_fts (rowid, text, video_id, segment_id)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (row["id"], row["text"], row["video_id"], row["id"])
                    for row in inserted_rows
                ],
            )

            return len(inserted_rows)

    def ingest_video(self, video_id: str) -> dict:
        video_dir = settings.SUBTITLES_DIR / video_id
        if not video_dir.exists():
            return {"video_id": video_id, "inserted": 0, "status": "missing"}

        chosen_path = video_dir / "chosen.json"
        meta_path = video_dir / "meta.json"
        raw_dir = video_dir / "raw"

        if not chosen_path.exists() or not meta_path.exists() or not raw_dir.exists():
            return {"video_id": video_id, "inserted": 0, "status": "incomplete"}

        chosen = json.loads(chosen_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        if chosen.get("status") != "success":
            return {"video_id": video_id, "inserted": 0, "status": "no_subtitles"}

        saved_files = chosen.get("saved_files", [])
        if not saved_files:
            return {"video_id": video_id, "inserted": 0, "status": "no_files"}

        subtitle_file = raw_dir / saved_files[0]
        if not subtitle_file.exists():
            return {"video_id": video_id, "inserted": 0, "status": "missing_file"}

        content = subtitle_file.read_text(encoding="utf-8", errors="ignore")
        segments = parse_vtt(content)
        if not segments:
            return {"video_id": video_id, "inserted": 0, "status": "empty"}

        self._upsert_video(meta, chosen, subtitle_file)
        inserted = self._replace_segments(meta["id"], segments)

        return {"video_id": video_id, "inserted": inserted, "status": "ok"}


subtitle_service = SubtitleService()