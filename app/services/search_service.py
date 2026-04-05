from collections import defaultdict
from urllib.parse import urlencode

from app.db.database import get_connection
from app.utils.text_utils import is_high_frequency_query, normalize_query

import re


def extract_exact_phrase(query: str) -> str | None:
    q = query.strip()
    if len(q) >= 2 and q.startswith('"') and q.endswith('"'):
        inner = q[1:-1].strip()
        inner = " ".join(inner.split())
        return inner or None
    return None


def build_normalized_phrase(query: str) -> str | None:
    q = " ".join(query.lower().strip().split())
    if not q:
        return None

    parts = q.split()
    if len(parts) < 2 or len(parts) > 6:
        return None

    return q


def normalize_text_for_phrase(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())
    return text


def compute_phrase_boost(text: str, normalized_phrase: str | None) -> tuple[bool, float]:
    if not normalized_phrase:
        return False, 0.0

    normalized_text = normalize_text_for_phrase(text)
    if normalized_phrase in normalized_text:
        return True, 2.5

    return False, 0.0


def build_query_tokens(query: str) -> list[str]:
    tokens = normalize_text_for_phrase(query).split()
    tokens = [token for token in tokens if token]
    unique_tokens: list[str] = []
    for token in tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)
    return unique_tokens[:6]


def compute_proximity_boost(text: str, query_tokens: list[str]) -> tuple[int, float]:
    if len(query_tokens) < 2:
        return 0, 0.0

    words = normalize_text_for_phrase(text).split()
    if not words:
        return 0, 0.0

    positions: dict[str, list[int]] = defaultdict(list)
    for idx, word in enumerate(words):
        if word in query_tokens:
            positions[word].append(idx)

    matched_tokens = [token for token in query_tokens if positions.get(token)]
    matched_count = len(matched_tokens)

    if matched_count < 2:
        return matched_count, 0.0

    best_span: int | None = None
    for left_token in matched_tokens:
        for right_token in matched_tokens:
            if left_token == right_token:
                continue
            for left_pos in positions[left_token]:
                for right_pos in positions[right_token]:
                    span = abs(left_pos - right_pos)
                    if best_span is None or span < best_span:
                        best_span = span

    if best_span is None:
        return matched_count, 0.0

    if matched_count >= 3 and best_span <= 6:
        return matched_count, 1.6
    if best_span <= 4:
        return matched_count, 1.2
    if best_span <= 8:
        return matched_count, 0.7

    return matched_count, 0.0


def _tokenize_preview_text(text: str) -> list[str]:
    return text.split()


def _collapse_repeated_phrases(text: str, max_ngram: int = 6) -> str:
    tokens = text.split()
    if len(tokens) < 2:
        return text

    result: list[str] = []
    i = 0
    n = len(tokens)

    while i < n:
        collapsed = False

        for size in range(min(max_ngram, (n - i) // 2), 0, -1):
            left = tokens[i:i + size]
            right = tokens[i + size:i + 2 * size]

            if left == right:
                result.extend(left)
                i += 2 * size

                while i + size <= n and tokens[i - size:i] == tokens[i:i + size]:
                    i += size

                collapsed = True
                break

        if not collapsed:
            result.append(tokens[i])
            i += 1

    return " ".join(result)


def _merge_preview_texts(texts: list[str], max_items: int = 3) -> str:
    cleaned: list[str] = []

    for raw in texts[:max_items]:
        text = " ".join(raw.split())
        text = _collapse_repeated_phrases(text)
        if not text:
            continue

        if not cleaned:
            cleaned.append(text)
            continue

        prev_tokens = _tokenize_preview_text(cleaned[-1])
        curr_tokens = _tokenize_preview_text(text)

        max_overlap = min(len(prev_tokens), len(curr_tokens), 8)
        overlap = 0

        for size in range(max_overlap, 0, -1):
            if prev_tokens[-size:] == curr_tokens[:size]:
                overlap = size
                break

        if overlap == len(curr_tokens):
            continue

        if overlap > 0:
            curr_tokens = curr_tokens[overlap:]

        merged_text = " ".join(curr_tokens).strip()
        if merged_text:
            cleaned.append(merged_text)

    final_text = " | ".join(cleaned)
    return _collapse_repeated_phrases(final_text)


def _normalize_long_preview_text(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+\|+\s*", " ", text)
    return text.strip()


def _merge_long_preview_texts(texts: list[str], max_items: int = 8) -> str:
    cleaned: list[str] = []

    for raw in texts[:max_items]:
        text = _normalize_long_preview_text(raw)
        text = _collapse_repeated_phrases(text)
        if not text:
            continue

        if not cleaned:
            cleaned.append(text)
            continue

        prev_tokens = _tokenize_preview_text(cleaned[-1])
        curr_tokens = _tokenize_preview_text(text)

        max_overlap = min(len(prev_tokens), len(curr_tokens), 12)
        overlap = 0

        for size in range(max_overlap, 0, -1):
            if prev_tokens[-size:] == curr_tokens[:size]:
                overlap = size
                break

        if overlap == len(curr_tokens):
            continue

        if overlap > 0:
            curr_tokens = curr_tokens[overlap:]

        merged_text = " ".join(curr_tokens).strip()
        if merged_text:
            cleaned.append(merged_text)

    final_text = " ".join(cleaned)
    return _collapse_repeated_phrases(final_text)


def _extract_sentence_like_preview(text: str, max_chars: int = 320) -> str:
    text = _normalize_long_preview_text(text)
    if not text:
        return ""

    text = text[: max_chars * 2].strip()

    sentence_end_pattern = re.compile(r"[.!?](?:\s|$)")
    match = sentence_end_pattern.search(text)

    if match and match.end() >= 80:
        return text[:match.end()].strip()

    comma_match = re.search(r",(?:\s|$)", text)
    if comma_match and comma_match.end() >= 120:
        return text[:comma_match.end()].strip()

    if len(text) <= max_chars:
        return text

    cutoff = text.rfind(" ", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars

    return text[:cutoff].strip() + "..."


def _build_long_preview_text(hits: list[dict]) -> str:
    merged = _merge_long_preview_texts(
        [hit["text"] for hit in hits],
        max_items=8,
    )
    return _extract_sentence_like_preview(merged, max_chars=320)


def _extract_sentence_like_preview_from_context(text: str, max_chars: int = 360) -> str:
    text = _normalize_long_preview_text(text)
    if not text:
        return ""

    text = _collapse_repeated_phrases(text)
    if len(text) <= max_chars:
        return text

    sentence_end_pattern = re.compile(r"[.!?](?:\s|$)")
    match = sentence_end_pattern.search(text)

    if match and match.end() >= 100:
        return text[:match.end()].strip()

    cutoff = text.rfind(" ", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars

    return text[:cutoff].strip() + "..."


class SearchService:
    MERGE_GAP_SECONDS = 3.0
    CLUSTER_WINDOW_SECONDS = 30.0
    DETAIL_CONTEXT_BEFORE_SECONDS = 2.0
    DETAIL_CONTEXT_AFTER_SECONDS = 5.0
    DETAIL_DISPLAY_MAX_CHARS = 260

    def _build_cluster_context_preview(
        self,
        video_id: str,
        start: float,
        end: float,
        before_seconds: float = 8.0,
        after_seconds: float = 8.0,
    ) -> str:
        sql = """
        SELECT text
        FROM subtitle_segments
        WHERE video_id = ?
          AND start <= ?
          AND end >= ?
        ORDER BY start
        """

        window_start = max(0.0, start - before_seconds)
        window_end = end + after_seconds

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (video_id, window_end, window_start),
            ).fetchall()

        texts = [dict(row)["text"] for row in rows]
        merged = _merge_long_preview_texts(texts, max_items=12)
        return _extract_sentence_like_preview_from_context(merged, max_chars=360)

    def _clean_display_text(self, text: str) -> str:
        text = " ".join(text.split())
        text = re.sub(r"\s+\|+\s*", " ", text)
        text = _collapse_repeated_phrases(text)
        return text.strip()

    def _trim_display_text(self, text: str, max_chars: int | None = None) -> str:
        if max_chars is None:
            max_chars = self.DETAIL_DISPLAY_MAX_CHARS

        text = self._clean_display_text(text)
        if len(text) <= max_chars:
            return text

        cutoff = text.rfind(" ", 0, max_chars)
        if cutoff == -1:
            cutoff = max_chars

        trimmed = text[:cutoff].strip()

        sentence_cut = max(
            trimmed.rfind("."),
            trimmed.rfind("?"),
            trimmed.rfind("!"),
            trimmed.rfind("。"),
            trimmed.rfind("？"),
            trimmed.rfind("！"),
        )
        if sentence_cut >= 80:
            return trimmed[: sentence_cut + 1].strip()

        return trimmed + "..."

    def _build_detail_display_text(
        self,
        video_id: str,
        start: float,
        end: float,
        before_seconds: float | None = None,
        after_seconds: float | None = None,
    ) -> str:
        if before_seconds is None:
            before_seconds = self.DETAIL_CONTEXT_BEFORE_SECONDS
        if after_seconds is None:
            after_seconds = self.DETAIL_CONTEXT_AFTER_SECONDS

        window_start = max(0.0, start - before_seconds)
        window_end = end + after_seconds

        sql = """
        SELECT text
        FROM subtitle_segments
        WHERE video_id = ?
          AND start <= ?
          AND end >= ?
        ORDER BY start
        """

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (video_id, window_end, window_start),
            ).fetchall()

        texts = [dict(row)["text"] for row in rows if dict(row).get("text")]
        if not texts:
            return ""

        merged = _merge_long_preview_texts(texts, max_items=20)
        merged = self._clean_display_text(merged)
        return self._trim_display_text(merged)

    def _parse_source_ids(self, source_ids: str | None) -> list[int]:
        if not source_ids:
            return []

        result: list[int] = []
        for part in source_ids.split(","):
            item = part.strip()
            if not item or not item.isdigit():
                continue

            value = int(item)
            if value not in result:
                result.append(value)

        return result

    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 12,
        raw_limit: int = 300,
        exact: bool = False,
        source_mode: str = "all",
        source_ids: str | None = None,
    ) -> dict:
        raw_query = query
        manual_exact_phrase = extract_exact_phrase(raw_query)

        effective_exact_phrase = manual_exact_phrase
        if exact and not effective_exact_phrase:
            candidate = " ".join(raw_query.strip().split())
            if candidate:
                effective_exact_phrase = candidate

        query = normalize_query(effective_exact_phrase if effective_exact_phrase else raw_query)
        normalized_phrase = build_normalized_phrase(query)
        query_tokens = build_query_tokens(query)
        selected_source_ids = self._parse_source_ids(source_ids)

        if source_mode not in {"all", "selected"}:
            return {
                "query": raw_query,
                "exact": bool(effective_exact_phrase),
                "source_mode": source_mode,
                "source_ids": selected_source_ids,
                "total_hits": 0,
                "total_videos": 0,
                "total_pages": 0,
                "page": 1,
                "per_page": per_page,
                "groups": [],
                "message": "Invalid source mode.",
            }

        if source_mode == "selected" and not selected_source_ids:
            return {
                "query": raw_query,
                "exact": bool(effective_exact_phrase),
                "source_mode": source_mode,
                "source_ids": selected_source_ids,
                "total_hits": 0,
                "total_videos": 0,
                "total_pages": 0,
                "page": 1,
                "per_page": per_page,
                "groups": [],
                "message": "No sources selected.",
            }

        if not query:
            return {
                "query": raw_query,
                "exact": bool(effective_exact_phrase),
                "source_mode": source_mode,
                "source_ids": selected_source_ids,
                "total_hits": 0,
                "total_videos": 0,
                "total_pages": 0,
                "page": page,
                "per_page": per_page,
                "groups": [],
                "message": "Empty query.",
            }

        if not effective_exact_phrase and is_high_frequency_query(query):
            return {
                "query": raw_query,
                "exact": bool(effective_exact_phrase),
                "source_mode": source_mode,
                "source_ids": selected_source_ids,
                "total_hits": 0,
                "total_videos": 0,
                "total_pages": 0,
                "page": page,
                "per_page": per_page,
                "groups": [],
                "message": "Query too broad. Please use a more specific phrase.",
            }

        rows = self._search_segments(
            query=query,
            limit=raw_limit,
            exact_phrase=effective_exact_phrase,
            source_mode=source_mode,
            selected_source_ids=selected_source_ids,
        )
        groups = self._group_rows(
            rows,
            normalized_phrase=normalized_phrase,
            query_tokens=query_tokens,
        )

        total_videos = len(groups)
        total_pages = (total_videos + per_page - 1) // per_page if total_videos else 0

        if total_pages == 0:
            paged_groups = []
            page = 1
        else:
            page = max(1, min(page, total_pages))
            start = (page - 1) * per_page
            end = start + per_page
            paged_groups = groups[start:end]

        return {
            "query": raw_query,
            "exact": bool(effective_exact_phrase),
            "source_mode": source_mode,
            "source_ids": selected_source_ids,
            "total_hits": len(rows),
            "total_videos": total_videos,
            "total_pages": total_pages,
            "page": page,
            "per_page": per_page,
            "groups": paged_groups,
            "message": "ok",
        }

    def _search_segments(
        self,
        query: str,
        limit: int,
        exact_phrase: str | None = None,
        source_mode: str = "all",
        selected_source_ids: list[int] | None = None,
    ) -> list[dict]:
        search_query = f'"{exact_phrase}"' if exact_phrase else query

        exists_sql = """
        EXISTS (
            SELECT 1
            FROM source_videos sv
            JOIN sources src ON src.id = sv.source_id
            WHERE sv.video_id = s.video_id
              AND sv.is_available = 1
              AND src.is_active = 1
        """
        params: list = [search_query]

        if source_mode == "selected" and selected_source_ids:
            placeholders = ",".join("?" for _ in selected_source_ids)
            exists_sql += f" AND sv.source_id IN ({placeholders})"
            params.extend(selected_source_ids)

        exists_sql += ")"

        sql = f"""
        SELECT
            s.id AS segment_id,
            s.video_id,
            s.start,
            s.end,
            s.duration,
            s.text,
            v.title,
            v.webpage_url,
            v.channel
        FROM subtitle_segments_fts f
        JOIN subtitle_segments s ON s.id = f.rowid
        JOIN videos v ON v.id = s.video_id
        WHERE subtitle_segments_fts MATCH ?
          AND {exists_sql}
        ORDER BY bm25(subtitle_segments_fts), s.start
        LIMIT ?
        """

        params.append(limit)

        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def _video_has_active_source(self, video_id: str) -> bool:
        sql = """
        SELECT 1
        FROM source_videos sv
        JOIN sources src ON src.id = sv.source_id
        WHERE sv.video_id = ?
          AND sv.is_available = 1
          AND src.is_active = 1
        LIMIT 1
        """

        with get_connection() as conn:
            row = conn.execute(sql, (video_id,)).fetchone()

        return row is not None

    def _group_rows(
        self,
        rows: list[dict],
        normalized_phrase: str | None = None,
        query_tokens: list[str] | None = None,
    ) -> list[dict]:
        by_video: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_video[row["video_id"]].append(row)

        groups = []
        for video_id, items in by_video.items():
            items.sort(key=lambda x: x["start"])

            merged_hits = self._merge_hits(items)
            clusters = self._cluster_hits(merged_hits)

            for cluster in clusters:
                preview_text = cluster.get("preview_text", "")

                cluster["long_preview_text"] = self._build_cluster_context_preview(
                    video_id=video_id,
                    start=float(cluster.get("start", 0.0)),
                    end=float(cluster.get("end", 0.0)),
                    before_seconds=12.0,
                    after_seconds=12.0,
                )

                phrase_match, phrase_boost = compute_phrase_boost(
                    preview_text,
                    normalized_phrase,
                )
                matched_token_count, proximity_boost = compute_proximity_boost(
                    preview_text,
                    query_tokens,
                )

                cluster["phrase_match"] = phrase_match
                cluster["phrase_boost"] = phrase_boost
                cluster["matched_token_count"] = matched_token_count
                cluster["proximity_boost"] = proximity_boost
                cluster["cluster_hit_count"] = len(cluster.get("hits", []))
                cluster["final_score"] = phrase_boost + proximity_boost

            clusters.sort(
                key=lambda c: (
                    c.get("final_score", 0.0),
                    c.get("matched_token_count", 0),
                    c.get("cluster_hit_count", 0),
                    -c.get("start_seconds", 0),
                ),
                reverse=True,
            )

            top_cluster_score = max(
                (float(cluster.get("final_score", 0.0)) for cluster in clusters),
                default=0.0,
            )
            phrase_match_count = sum(1 for cluster in clusters if cluster.get("phrase_match"))
            proximity_match_count = sum(1 for cluster in clusters if cluster.get("proximity_boost", 0.0) > 0)

            groups.append(
                {
                    "video_id": video_id,
                    "title": items[0]["title"],
                    "webpage_url": items[0]["webpage_url"],
                    "channel": items[0]["channel"],
                    "hit_count": len(items),
                    "cluster_count": len(clusters),
                    "top_cluster_score": top_cluster_score,
                    "phrase_match_count": phrase_match_count,
                    "proximity_match_count": proximity_match_count,
                    "default_watch_url": self._build_watch_url(
                        items[0]["webpage_url"],
                        clusters[0]["start"],
                    ) if clusters else items[0]["webpage_url"],
                    "default_embed_url": self._build_embed_url(
                        video_id,
                        clusters[0]["start"],
                    ) if clusters else self._build_embed_url(video_id, 0),
                    "clusters": clusters,
                }
            )

        groups.sort(
            key=lambda g: (
                g.get("top_cluster_score", 0.0),
                g.get("phrase_match_count", 0),
                g.get("proximity_match_count", 0),
                g.get("cluster_count", 0),
                g.get("hit_count", 0),
            ),
            reverse=True,
        )

        return groups

    def _merge_hits(self, hits: list[dict]) -> list[dict]:
        if not hits:
            return []

        merged = [self._to_merge_item(hits[0])]

        for hit in hits[1:]:
            current = self._to_merge_item(hit)
            last = merged[-1]

            if current["start"] - last["end"] <= self.MERGE_GAP_SECONDS:
                last["end"] = max(last["end"], current["end"])
                last["texts"].extend(current["texts"])
                last["segment_ids"].extend(current["segment_ids"])
            else:
                merged.append(current)

        for item in merged:
            item["text"] = " ".join(dict.fromkeys(item["texts"]))
            item["start_seconds"] = int(item["start"])
            item["watch_url"] = self._build_watch_url(item["webpage_url"], item["start"])
            item["embed_url"] = self._build_embed_url(item["video_id"], item["start"])
            del item["texts"]

        return merged

    def _cluster_hits(self, merged_hits: list[dict]) -> list[dict]:
        if not merged_hits:
            return []

        clusters = [self._new_cluster(merged_hits[0])]

        for hit in merged_hits[1:]:
            last = clusters[-1]
            if hit["start"] - last["_cluster_end"] <= self.CLUSTER_WINDOW_SECONDS:
                last["_cluster_end"] = max(last["_cluster_end"], hit["end"])
                last["hits"].append(hit)
            else:
                clusters.append(self._new_cluster(hit))

        for cluster in clusters:
            first_hit = cluster["hits"][0]
            last_hit = cluster["hits"][-1]

            cluster["start"] = first_hit["start"]
            cluster["end"] = last_hit["end"]
            cluster["start_seconds"] = int(first_hit["start"])
            cluster["video_id"] = first_hit["video_id"]
            cluster["watch_url"] = self._build_watch_url(first_hit["webpage_url"], first_hit["start"])
            cluster["embed_url"] = self._build_embed_url(first_hit["video_id"], first_hit["start"])
            cluster["preview_text"] = _merge_preview_texts(
                [hit["text"] for hit in cluster["hits"]],
                max_items=3,
            )
            cluster["long_preview_text"] = _build_long_preview_text(cluster["hits"])

            for hit in cluster["hits"]:
                hit.pop("webpage_url", None)

            cluster["cluster_end"] = cluster.pop("_cluster_end")

        return clusters

    def _to_merge_item(self, hit: dict) -> dict:
        return {
            "segment_ids": [hit["segment_id"]],
            "video_id": hit["video_id"],
            "start": hit["start"],
            "end": hit["end"],
            "text": hit["text"],
            "texts": [hit["text"]],
            "webpage_url": hit["webpage_url"],
        }

    def _new_cluster(self, hit: dict) -> dict:
        return {
            "_cluster_end": hit["end"],
            "hits": [hit],
        }

    def _build_watch_url(self, webpage_url: str, start: float) -> str:
        separator = "&" if "?" in webpage_url else "?"
        return f"{webpage_url}{separator}{urlencode({'t': int(start)})}"

    def _build_embed_url(self, video_id: str, start: float) -> str:
        params = urlencode(
            {
                "start": int(start),
                "autoplay": 1,
                "enablejsapi": 1,
                "playsinline": 1,
            }
        )
        return f"https://www.youtube.com/embed/{video_id}?{params}"

    def get_video_detail(
        self,
        video_id: str,
        query: str,
        sort_mode: str = "timeline",
        raw_limit: int = 500,
    ) -> dict | None:
        if not self._video_has_active_source(video_id):
            return None

        raw_query = query
        exact_phrase = extract_exact_phrase(raw_query)

        effective_exact_phrase = exact_phrase
        query = normalize_query(effective_exact_phrase if effective_exact_phrase else raw_query)
        normalized_phrase = build_normalized_phrase(query)
        query_tokens = build_query_tokens(query)

        if not query:
            return None

        rows = self._search_segments(query, raw_limit, exact_phrase=effective_exact_phrase)
        rows = [row for row in rows if row["video_id"] == video_id]

        if not rows:
            with get_connection() as conn:
                video_row = conn.execute(
                    """
                    SELECT id, title, webpage_url, duration, channel, uploader,
                           selected_subtitle_type, selected_subtitle_lang
                    FROM videos
                    WHERE id = ?
                    """,
                    (video_id,),
                ).fetchone()

            if not video_row:
                return None

            return {
                "video_id": video_row["id"],
                "title": video_row["title"],
                "webpage_url": video_row["webpage_url"],
                "duration": video_row["duration"],
                "channel": video_row["channel"],
                "uploader": video_row["uploader"],
                "selected_subtitle_type": video_row["selected_subtitle_type"],
                "selected_subtitle_lang": video_row["selected_subtitle_lang"],
                "query": raw_query,
                "sort_mode": sort_mode,
                "hit_count": 0,
                "clusters": [],
            }

        items = sorted(rows, key=lambda x: x["start"])
        merged_hits = self._merge_hits(items)
        clusters = self._cluster_hits(merged_hits)

        for cluster in clusters:
            preview_text = cluster.get("preview_text", "")

            phrase_match, phrase_boost = compute_phrase_boost(
                preview_text,
                normalized_phrase,
            )
            matched_token_count, proximity_boost = compute_proximity_boost(
                preview_text,
                query_tokens,
            )

            cluster["phrase_match"] = phrase_match
            cluster["phrase_boost"] = phrase_boost
            cluster["matched_token_count"] = matched_token_count
            cluster["proximity_boost"] = proximity_boost
            cluster["cluster_hit_count"] = len(cluster.get("hits", []))
            cluster["final_score"] = phrase_boost + proximity_boost

            cluster["display_text"] = self._build_detail_display_text(
                video_id=video_id,
                start=float(cluster.get("start", 0.0)),
                end=float(cluster.get("end", 0.0)),
            ) or cluster.get("long_preview_text") or cluster.get("preview_text", "")

        if sort_mode == "best":
            clusters.sort(
                key=lambda c: (
                    c.get("final_score", 0.0),
                    c.get("matched_token_count", 0),
                    c.get("cluster_hit_count", 0),
                    -c.get("start_seconds", 0),
                ),
                reverse=True,
            )
        else:
            clusters.sort(key=lambda c: c.get("start_seconds", 0))

        first = rows[0]

        with get_connection() as conn:
            video_row = conn.execute(
                """
                SELECT id, title, webpage_url, duration, channel, uploader,
                       selected_subtitle_type, selected_subtitle_lang
                FROM videos
                WHERE id = ?
                """,
                (video_id,),
            ).fetchone()

        if not video_row:
            return None

        return {
            "video_id": video_row["id"],
            "title": video_row["title"],
            "webpage_url": video_row["webpage_url"],
            "duration": video_row["duration"],
            "channel": video_row["channel"],
            "uploader": video_row["uploader"],
            "selected_subtitle_type": video_row["selected_subtitle_type"],
            "selected_subtitle_lang": video_row["selected_subtitle_lang"],
            "query": raw_query,
            "sort_mode": sort_mode,
            "hit_count": len(rows),
            "clusters": clusters,
            "default_embed_url": self._build_embed_url(video_id, clusters[0]["start"]) if clusters else self._build_embed_url(video_id, 0),
            "default_watch_url": self._build_watch_url(first["webpage_url"], clusters[0]["start"]) if clusters else first["webpage_url"],
        }


search_service = SearchService()