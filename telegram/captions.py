from __future__ import annotations

from html import escape

from utils.formatting import format_duration, format_size
from video.metadata import VideoMetadata

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096


def build_preview_caption(metadata: VideoMetadata) -> str:
    if metadata.content_type == "instagram_story":
        lines = ["<b>Нашёл Instagram Story:</b>", ""]
        if metadata.uploader:
            lines.append(f"<b>Автор:</b> {escape(metadata.uploader)}")
        lines.append("<b>Тип:</b> Story")
        duration = format_duration(metadata.duration)
        if duration:
            lines.append(f"<b>Длительность:</b> {escape(duration)}")
        lines.extend(["", "Это то видео, которое нужно скачать?"])
        return "\n".join(lines)

    lines = ["<b>Нашёл видео:</b>", ""]
    if metadata.title:
        lines.append(f"<b>Название:</b> {escape(metadata.title)}")
    if metadata.platform:
        lines.append(f"<b>Источник:</b> {escape(metadata.platform)}")
    if metadata.uploader:
        lines.append(f"<b>Автор:</b> {escape(metadata.uploader)}")
    duration = format_duration(metadata.duration)
    if duration:
        lines.append(f"<b>Длительность:</b> {escape(duration)}")
    estimated_size = format_size(metadata.estimated_filesize)
    if estimated_size:
        lines.append(f"<b>Примерный размер:</b> {escape(estimated_size)}")
    lines.extend(["", "Это то видео, которое нужно скачать?"])
    return "\n".join(lines)


def build_video_caption(metadata: VideoMetadata) -> tuple[str, str | None]:
    title = metadata.title or "Видео"
    description = metadata.description or ""
    escaped_title = escape(title)
    escaped_description = escape(description)

    if escaped_description:
        full_caption = f"<b>{escaped_title}</b>\n\n{escaped_description}"
    else:
        full_caption = f"<b>{escaped_title}</b>"

    if len(full_caption) <= TELEGRAM_CAPTION_LIMIT:
        return full_caption, None

    short_title = _fit_text(escaped_title, 900)
    short_caption = f"<b>{short_title}</b>\n\nПолное описание ниже."
    if len(short_caption) > TELEGRAM_CAPTION_LIMIT:
        short_caption = f"<b>{_fit_text(escaped_title, 980)}</b>"
    return short_caption, description or None


def split_plain_text_as_html(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    chunks: list[str] = []
    remaining = text

    while remaining:
        take = min(len(remaining), limit)
        while take > 1 and len(escape(remaining[:take])) > limit:
            take = max(1, int(take * 0.9))

        if take < len(remaining):
            split_at = remaining.rfind("\n", 0, take)
            if split_at < take // 2:
                split_at = remaining.rfind(" ", 0, take)
            if split_at >= take // 2:
                take = split_at

        chunk = remaining[:take].strip()
        if chunk:
            chunks.append(escape(chunk))
        remaining = remaining[take:].strip()

    return chunks


def split_long_html_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _fit_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
