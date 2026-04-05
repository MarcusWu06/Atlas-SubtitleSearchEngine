from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class PlaylistSyncRequest(BaseModel):
    playlist_url: HttpUrl
    languages: list[str] = Field(
        default_factory=lambda: ["en", "en-US", "zh-Hans", "zh-Hant", "zh", "auto"]
    )
    max_concurrent_downloads: int = 3
    include_auto_subtitles: bool = True


class JobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)


class SourceCreateRequest(BaseModel):
    source_type: Literal["playlist", "channel", "video"]
    source_url: HttpUrl
    title: str | None = None


class SourceResponse(BaseModel):
    id: int
    source_type: Literal["playlist", "channel", "video"]
    source_url: str
    source_key: str
    title: str | None = None
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None
    last_synced_at: str | None = None


class SourceDetailResponse(SourceResponse):
    video_count: int = 0
    available_video_count: int = 0
    sync_run_count: int = 0


class SyncRunResponse(BaseModel):
    id: int
    source_id: int
    status: Literal["pending", "running", "completed", "failed"]
    started_at: str | None = None
    finished_at: str | None = None
    total_discovered: int = 0
    new_videos: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    error_summary: str | None = None


class SourceSyncResponse(BaseModel):
    source_id: int
    sync_run: SyncRunResponse


class SourceVideoResponse(BaseModel):
    id: int
    source_id: int
    video_id: str
    position: int | None = None
    discovered_at: str | None = None
    last_seen_at: str | None = None
    is_available: bool
    sync_status: str | None = None
    last_error: str | None = None


class SyncRunListItemResponse(BaseModel):
    id: int
    source_id: int
    status: Literal["pending", "running", "completed", "failed"]
    started_at: str | None = None
    finished_at: str | None = None
    total_discovered: int = 0
    new_videos: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    error_summary: str | None = None


class ContextWindowRequest(BaseModel):
    video_id: str
    start_seconds: float
    window_before: int = 30
    window_after: int = 30


class ContextSegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class ContextWindowResponse(BaseModel):
    video_id: str
    window_start: float
    window_end: float
    segment_count: int
    segments: list[ContextSegmentResponse]
    full_text: str


class SummarizeContextRequest(BaseModel):
    video_id: str
    start_seconds: float
    query: str | None = None
    window_before: int = 30
    window_after: int = 30


class SummarizeContextResponse(BaseModel):
    video_id: str
    window_start: float
    window_end: float
    segment_count: int
    full_text: str
    summary: str


class SourceUpdateRequest(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None


class SaveMomentRequest(BaseModel):
    video_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    query: Optional[str] = None
    start_seconds: int
    end_seconds: int
    display_text: Optional[str] = None
    watch_url: Optional[str] = None


class SaveVideoRequest(BaseModel):
    video_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    query: Optional[str] = None
    display_text: Optional[str] = None
    watch_url: Optional[str] = None


class SavedItemResponse(BaseModel):
    id: int
    item_type: str
    video_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    query: Optional[str] = None
    start_seconds: Optional[int] = None
    end_seconds: Optional[int] = None
    display_text: Optional[str] = None
    watch_url: Optional[str] = None
    created_at: str