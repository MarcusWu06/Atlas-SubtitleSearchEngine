from pathlib import Path


class Settings:
    BASE_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = BASE_DIR / "data"
    SUBTITLES_DIR = DATA_DIR / "subtitles"
    INDEX_DIR = DATA_DIR / "index"
    META_DIR = DATA_DIR / "meta"
    CACHE_DIR = DATA_DIR / "cache"

    YTDLP_COOKIE_FILE = None
    YTDLP_PREFERRED_SUB_LANGS = ["en", "en-US", "zh-Hans", "zh-Hant", "zh"]
    MAX_CONCURRENT_DOWNLOADS = 3

    @classmethod
    def ensure_dirs(cls) -> None:
        for path in (
            cls.DATA_DIR,
            cls.SUBTITLES_DIR,
            cls.INDEX_DIR,
            cls.META_DIR,
            cls.CACHE_DIR,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()