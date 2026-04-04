import sqlite3

from app.core.config import settings


DB_PATH = settings.INDEX_DIR / "atlas.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    settings.ensure_dirs()

    with get_connection() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                title TEXT,
                webpage_url TEXT,
                duration INTEGER,
                channel TEXT,
                uploader TEXT,
                language TEXT,
                selected_subtitle_type TEXT,
                selected_subtitle_lang TEXT,
                subtitle_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS subtitle_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                start REAL NOT NULL,
                end REAL NOT NULL,
                duration REAL NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_subtitle_segments_video_id
            ON subtitle_segments(video_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS subtitle_segments_fts
            USING fts5(
                text,
                video_id UNINDEXED,
                segment_id UNINDEXED
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                title TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS source_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                position INTEGER,
                discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_available INTEGER NOT NULL DEFAULT 1,
                sync_status TEXT DEFAULT 'pending',
                last_error TEXT,
                UNIQUE(source_id, video_id),
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_source_videos_source_id
            ON source_videos(source_id);

            CREATE INDEX IF NOT EXISTS idx_source_videos_video_id
            ON source_videos(video_id);

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                total_discovered INTEGER NOT NULL DEFAULT 0,
                new_videos INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                succeeded INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT,
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sync_runs_source_id
            ON sync_runs(source_id);

            CREATE TABLE IF NOT EXISTS summary_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                start_seconds REAL NOT NULL,
                window_before INTEGER NOT NULL,
                window_after INTEGER NOT NULL,
                summary TEXT NOT NULL,
                model_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(video_id, start_seconds, window_before, window_after, model_name)
            );

            CREATE INDEX IF NOT EXISTS idx_summary_cache_lookup
            ON summary_cache(video_id, start_seconds, window_before, window_after, model_name);

            CREATE TABLE IF NOT EXISTS saved_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                channel TEXT,
                query TEXT,
                start_seconds INTEGER,
                end_seconds INTEGER,
                display_text TEXT,
                watch_url TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_saved_items_created_at
            ON saved_items(created_at);

            CREATE INDEX IF NOT EXISTS idx_saved_items_video_id
            ON saved_items(video_id);
            """
        )