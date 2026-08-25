import json
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from files.models import Media

from .models import BehaviorEvent, UserViewingSession, VideoInteractionLog


IDLE_TIMEOUT_SECONDS = 300
CLIENT_EVENT_TYPES = {"exposure", "play", "resume", "pause", "seek", "replay", "end", "share"}
CLIENT_INFO_KEYS = {"timezone", "viewport", "app_version"}
PAYLOAD_KEYS = {"position", "visible", "from_position", "to_position", "channel", "end_reason"}


class BehaviorError(Exception):
    def __init__(self, code, detail, status_code=400):
        self.code, self.detail, self.status_code = code, detail, status_code
        super().__init__(detail)


def decimal_value(value, field, default=None):
    if value is None:
        return default
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BehaviorError("INVALID_FIELD", f"{field} must be a number.")
    if result < 0:
        raise BehaviorError("INVALID_FIELD", f"{field} must be non-negative.")
    return result


def client_info(value):
    if not isinstance(value, dict):
        return {}
    return {key: str(value[key])[:128] for key in CLIENT_INFO_KEYS if key in value}


def event_payload(value):
    if not isinstance(value, dict):
        raise BehaviorError("INVALID_PAYLOAD", "payload must be an object.")
    cleaned = {key: value[key] for key in PAYLOAD_KEYS if key in value}
    if len(json.dumps(cleaned, default=str).encode("utf-8")) > 4096:
        raise BehaviorError("PAYLOAD_TOO_LARGE", "payload must not exceed 4 KiB.")
    return cleaned


def client_datetime(value):
    if not value:
        return None
    if not isinstance(value, str):
        raise BehaviorError("INVALID_FIELD", "client_time must be an ISO-8601 datetime.")
    result = parse_datetime(value)
    if result is None:
        raise BehaviorError("INVALID_FIELD", "client_time must be an ISO-8601 datetime.")
    if timezone.is_naive(result):
        result = timezone.make_aware(result)
    return result


def expire_session(session, now=None):
    now = now or timezone.now()
    if session.session_end:
        raise BehaviorError("SESSION_EXPIRED", "Create a new client_session_id.", 409)
    if now - session.last_activity_at < timedelta(seconds=IDLE_TIMEOUT_SECONDS):
        return
    session.session_end = session.last_activity_at
    session.end_reason = UserViewingSession.EndReason.IDLE_TIMEOUT
    session.save(update_fields=["session_end", "end_reason", "updated_at"])
    session.interactions.filter(play_end_time__isnull=True).update(
        play_end_time=session.last_activity_at,
        end_reason=VideoInteractionLog.EndReason.SESSION_TIMEOUT,
    )
    raise BehaviorError("SESSION_EXPIRED", "Create a new client_session_id.", 409)


def owned_session(user, session_id, lock=False):
    queryset = UserViewingSession.objects
    if lock:
        queryset = queryset.select_for_update()
    try:
        session = queryset.get(session_id=session_id, user=user)
    except UserViewingSession.DoesNotExist:
        raise BehaviorError("NOT_FOUND", "Viewing session was not found.", 404)
    expire_session(session)
    return session


def owned_interaction(user, interaction_id, lock=False):
    queryset = VideoInteractionLog.objects.select_related("session")
    if lock:
        queryset = queryset.select_for_update()
    try:
        interaction = queryset.get(interaction_id=interaction_id, user=user, session__user=user)
    except VideoInteractionLog.DoesNotExist:
        raise BehaviorError("NOT_FOUND", "Video interaction was not found.", 404)
    expire_session(interaction.session)
    return interaction


def touch(session, at=None):
    at = at or timezone.now()
    if at > session.last_activity_at:
        session.last_activity_at = at
        session.save(update_fields=["last_activity_at", "updated_at"])


def recalculate(interaction):
    if interaction.video_duration and interaction.video_duration > 0:
        raw = interaction.watch_duration / interaction.video_duration
        interaction.watch_ratio_raw = raw.quantize(Decimal("0.00001"))
        interaction.completion_ratio = min(raw, Decimal("1")).quantize(Decimal("0.00001"))
    else:
        interaction.watch_ratio_raw = Decimal("0")
        interaction.completion_ratio = Decimal("0")
    if interaction.exposure_time and interaction.play_start_time:
        interaction.play_latency = Decimal(str(max(0, (interaction.play_start_time - interaction.exposure_time).total_seconds()))).quantize(Decimal("0.001"))
    if interaction.end_reason == VideoInteractionLog.EndReason.SWIPE and interaction.play_start_time and interaction.play_end_time:
        interaction.skip_time = Decimal(str(max(0, (interaction.play_end_time - interaction.play_start_time).total_seconds()))).quantize(Decimal("0.001"))
    else:
        interaction.skip_time = None


def merge_totals(interaction, data):
    sequence = data.get("client_sequence")
    try:
        sequence = int(sequence)
    except (TypeError, ValueError):
        raise BehaviorError("INVALID_FIELD", "client_sequence must be an integer.")
    if sequence <= interaction.last_client_sequence:
        return False
    interaction.watch_duration = max(interaction.watch_duration, decimal_value(data.get("watch_duration"), "watch_duration", interaction.watch_duration))
    interaction.video_duration = decimal_value(data.get("video_duration"), "video_duration", interaction.video_duration)
    interaction.max_play_position = max(interaction.max_play_position, decimal_value(data.get("max_play_position"), "max_play_position", interaction.max_play_position))
    try:
        interaction.replay_count = max(interaction.replay_count, int(data.get("replay_count", interaction.replay_count)))
    except (TypeError, ValueError):
        raise BehaviorError("INVALID_FIELD", "replay_count must be an integer.")
    interaction.last_client_sequence = sequence
    recalculate(interaction)
    return True


def bounded_totals(interaction, data, now=None):
    """Bound cumulative watch time by server elapsed time while preserving monotonic totals."""
    cleaned = data.copy()
    requested = decimal_value(cleaned.get("watch_duration"), "watch_duration", interaction.watch_duration)
    reference = interaction.last_heartbeat_at or interaction.play_start_time
    if reference:
        elapsed = Decimal(str(max(0, ((now or timezone.now()) - reference).total_seconds())))
        cleaned["watch_duration"] = min(requested, interaction.watch_duration + elapsed + Decimal("2"))
    return cleaned


def record_business_event(user, interaction_id, media, event_type, payload=None, state_field=None, state=None):
    if not interaction_id or not user.is_authenticated:
        return False
    try:
        owned_interaction(user, interaction_id)
    except BehaviorError:
        return False
    with transaction.atomic():
        try:
            interaction = owned_interaction(user, interaction_id, lock=True)
        except BehaviorError:
            return False
        if interaction.media_id != media.pk:
            return False
        if state_field:
            setattr(interaction, state_field, state)
            interaction.save(update_fields=[state_field, "updated_at"])
        BehaviorEvent.objects.create(session=interaction.session, interaction=interaction, user=user, event_type=event_type, source=BehaviorEvent.Source.SERVER, payload=payload or {})
        touch(interaction.session)
    return True
