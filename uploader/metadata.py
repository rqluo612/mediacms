"""Validation shared by the upload form and direct media API."""
import json
import os
import uuid

from django.core.exceptions import ValidationError
from django.utils.html import strip_tags

from files.helpers import get_alphanumeric_and_spaces


def upload_token(user_id, upload_id):
    return 'upload-' + uuid.uuid5(uuid.NAMESPACE_URL, f'mediacms:{user_id}:{upload_id}').hex


def normalize_tags(values):
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except (ValueError, TypeError):
            raise ValidationError('标签必须是 JSON 字符串数组。')
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValidationError('标签必须是字符串数组。')
    tags = []
    for value in values:
        value = get_alphanumeric_and_spaces(value).lower()
        if not value:
            continue
        if len(value) > 20:
            raise ValidationError('每个标签最多20字。')
        if value not in tags:
            tags.append(value)
    return tags


def is_video(filename):
    return os.path.splitext(filename)[1].lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff", ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".pdf"}


def validate_metadata(data, filename):
    if not is_video(filename):
        return {"title": data.get("title", filename), "description": data.get("description", ""), "tags": []}
    title = strip_tags(data.get('title', os.path.splitext(os.path.basename(filename))[0])).strip()
    description = strip_tags(data.get('description', '')).strip()
    errors = {}
    if not title or len(title) > 100:
        errors['title'] = '标题必填，最多100字。'
    if len(description) > 300:
        errors['description'] = '简介最多300字。'
    try:
        tags = normalize_tags(data.get('tags', []))
        if not 1 <= len(tags) <= 5:
            errors['tags'] = '至少1个、最多5个，建议填写2～3个'
    except ValidationError as exc:
        errors['tags'] = exc.messages
        tags = []
    if errors:
        raise ValidationError(errors)
    return {'title': title, 'description': description, 'tags': tags}


def resolve_tags(titles):
    # Serialize creation across uploaders, including differently cased legacy tags.
    from django.db import connection
    from files.models import Tag

    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [71430912])
    existing = {}
    for tag in Tag.objects.order_by('pk'):
        existing.setdefault(get_alphanumeric_and_spaces(tag.title).lower(), tag)
    return [existing[title] if title in existing else Tag.objects.get_or_create(title=title)[0] for title in titles]
