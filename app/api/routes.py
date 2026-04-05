import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    ContextSegmentResponse,
    ContextWindowRequest,
    ContextWindowResponse,
    JobResponse,
    JobStatusResponse,
    PlaylistSyncRequest,
    SaveMomentRequest,
    SavedItemResponse,
    SourceCreateRequest,
    SourceDetailResponse,
    SourceResponse,
    SourceUpdateRequest,
    SourceSyncResponse,
    SourceVideoResponse,
    SummarizeContextRequest,
    SummarizeContextResponse,
    SyncRunListItemResponse,
    SyncRunResponse,
    SaveVideoRequest,
)
from app.services.archive_service import archive_service
from app.services.context_service import context_service
from app.services.job_store import job_store
from app.services.search_service import search_service
from app.services.source_service import source_service
from app.services.subtitle_service import subtitle_service
from app.services.summary_service import summary_service
from app.services.sync_service import sync_service
from app.services.youtube_service import youtube_service

router = APIRouter()


@router.post("/sync/playlist", response_model=JobResponse)
async def sync_playlist(payload: PlaylistSyncRequest) -> JobResponse:
    job = await job_store.create_job()

    asyncio.create_task(
        youtube_service.sync_playlist(
            job_id=job.job_id,
            playlist_url=str(payload.playlist_url),
            languages=payload.languages,
            include_auto_subtitles=payload.include_auto_subtitles,
            max_concurrent_downloads=payload.max_concurrent_downloads,
        )
    )

    return JobResponse(job_id=job.job_id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        total=job.total,
        processed=job.processed,
        succeeded=job.succeeded,
        failed=job.failed,
        errors=job.errors,
        results=job.results,
    )


@router.post("/ingest")
async def ingest_subtitles() -> dict:
    return subtitle_service.ingest_downloaded_subtitles()


@router.get("/search")
async def search(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    exact: bool = Query(False),
    source_mode: str = Query("all"),
    source_ids: str | None = Query(None),
):
    return search_service.search(
        query=q,
        page=page,
        per_page=per_page,
        exact=exact,
        source_mode=source_mode,
        source_ids=source_ids,
    )


@router.post("/sources", response_model=SourceResponse)
async def create_source(payload: SourceCreateRequest) -> SourceResponse:
    source = source_service.create_source(payload)
    return SourceResponse(**source)


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources() -> list[SourceResponse]:
    sources = source_service.list_sources()
    return [SourceResponse(**source) for source in sources]


@router.get("/sources/{source_id}", response_model=SourceDetailResponse)
async def get_source(source_id: int) -> SourceDetailResponse:
    source = source_service.get_source_by_id(source_id)
    return SourceDetailResponse(**source)


@router.post("/sources/{source_id}/sync", response_model=SourceSyncResponse)
async def sync_source(source_id: int) -> SourceSyncResponse:
    result = await sync_service.sync_source(source_id)
    return SourceSyncResponse(
        source_id=result["source_id"],
        sync_run=SyncRunResponse(**result["sync_run"]),
    )


@router.patch("/sources/{source_id}", response_model=SourceDetailResponse)
async def update_source(source_id: int, payload: SourceUpdateRequest) -> SourceDetailResponse:
    source = source_service.update_source(source_id, payload)
    return SourceDetailResponse(**source)


@router.get("/sources/{source_id}/videos", response_model=list[SourceVideoResponse])
async def list_source_videos(source_id: int) -> list[SourceVideoResponse]:
    videos = source_service.list_source_videos(source_id)
    return [SourceVideoResponse(**video) for video in videos]


@router.get("/sources/{source_id}/sync-runs", response_model=list[SyncRunListItemResponse])
async def list_source_sync_runs(source_id: int) -> list[SyncRunListItemResponse]:
    runs = source_service.list_sync_runs(source_id)
    return [SyncRunListItemResponse(**run) for run in runs]


@router.delete("/sources/{source_id}")
async def delete_source(source_id: int) -> dict[str, str]:
    source_service.delete_source(source_id)
    return {"status": "ok"}


@router.post("/context-window", response_model=ContextWindowResponse)
async def get_context_window(payload: ContextWindowRequest) -> ContextWindowResponse:
    data = context_service.get_context_window(
        video_id=payload.video_id,
        start_seconds=payload.start_seconds,
        window_before=payload.window_before,
        window_after=payload.window_after,
    )
    return ContextWindowResponse(
        video_id=data["video_id"],
        window_start=data["window_start"],
        window_end=data["window_end"],
        segment_count=data["segment_count"],
        segments=[ContextSegmentResponse(**segment) for segment in data["segments"]],
        full_text=data["full_text"],
    )


@router.post("/summarize-context", response_model=SummarizeContextResponse)
async def summarize_context(payload: SummarizeContextRequest) -> SummarizeContextResponse:
    data = summary_service.summarize_context(
        video_id=payload.video_id,
        start_seconds=payload.start_seconds,
        query=payload.query,
        window_before=payload.window_before,
        window_after=payload.window_after,
    )
    return SummarizeContextResponse(**data)


@router.get("/videos/{video_id}")
async def get_video_detail(
    video_id: str,
    q: str = Query(..., min_length=1),
    sort: str = Query("timeline"),
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if sort not in {"timeline", "best"}:
        raise HTTPException(status_code=400, detail="Invalid sort mode")

    data = search_service.get_video_detail(
        video_id=video_id,
        query=query,
        sort_mode=sort,
    )

    if not data:
        raise HTTPException(status_code=404, detail="Video detail not found")

    return data


@router.post("/archive/moments", response_model=SavedItemResponse)
async def save_moment(payload: SaveMomentRequest) -> SavedItemResponse:
    item = archive_service.save_moment(payload)
    return SavedItemResponse(**item)

@router.post("/archive/videos", response_model=SavedItemResponse)
async def save_video(payload: SaveVideoRequest) -> SavedItemResponse:
    item = archive_service.save_video(payload)
    return SavedItemResponse(**item)

@router.get("/archive", response_model=list[SavedItemResponse])
async def list_archive_items() -> list[SavedItemResponse]:
    items = archive_service.list_saved_items()
    return [SavedItemResponse(**item) for item in items]


@router.delete("/archive/{item_id}")
async def delete_archive_item(item_id: int) -> dict[str, str]:
    archive_service.delete_saved_item(item_id)
    return {"status": "ok"}
