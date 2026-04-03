import re


TIMECODE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)

TAG_RE = re.compile(r"<[^>]+>")


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _clean_text(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").strip()
    return " ".join(text.split())


def parse_vtt(content: str) -> list[dict]:
    lines = content.splitlines()
    segments: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line or line == "WEBVTT" or line.startswith("NOTE"):
            i += 1
            continue

        if "-->" not in line:
            i += 1
            continue

        match = TIMECODE_RE.match(line)
        if not match:
            i += 1
            continue

        start = _to_seconds(*match.groups()[:4])
        end = _to_seconds(*match.groups()[4:])
        i += 1

        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1

        text = _clean_text(" ".join(text_lines))
        if text:
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "duration": max(0.0, end - start),
                    "text": text,
                }
            )

    return segments