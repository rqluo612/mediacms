from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import UserBehaviorLog


IDLE_TIMEOUT_SECONDS = 300
CLIENT_EVENT_TYPES = {"exposure", "play", "resume", "pause", "seek", "replay", "end", "share"}
EARLY_EXIT_REASONS = {
    UserBehaviorLog.EndReason.NEXT,
    UserBehaviorLog.EndReason.PREVIOUS,
    UserBehaviorLog.EndReason.PAGE_CLOSE,
    UserBehaviorLog.EndReason.NAVIGATE,
    UserBehaviorLog.EndReason.BACKGROUND_TIMEOUT,
    UserBehaviorLog.EndReason.ERROR,
    UserBehaviorLog.EndReason.SESSION_TIMEOUT,
}


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


def session_queryset(user, session_id, lock=False):
    queryset = UserBehaviorLog.objects.filter(auth_user=user, session_id=session_id)
    return queryset.select_for_update() if lock else queryset


def expire_session(user, session_id, now=None):
    now = now or timezone.now()
    logs = session_queryset(user, session_id)
    latest = logs.order_by("-last_activity_at").first()
    if not latest:
        return None
    if latest.session_end:
        raise BehaviorError("SESSION_EXPIRED", "Create a new client_session_id.", 409)
    if now - latest.last_activity_at < timedelta(seconds=IDLE_TIMEOUT_SECONDS):
        return latest
    close_session_logs(logs, latest.last_activity_at, UserBehaviorLog.EndReason.SESSION_TIMEOUT)
    raise BehaviorError("SESSION_EXPIRED", "Create a new client_session_id.", 409)


def owned_interaction(user, interaction_id, lock=False, check_session=True):
    queryset = UserBehaviorLog.objects
    if lock:
        queryset = queryset.select_for_update()
    try:
        log = queryset.get(interaction_id=interaction_id, auth_user=user)
    except UserBehaviorLog.DoesNotExist:
        raise BehaviorError("NOT_FOUND", "User behavior log was not found.", 404)
    if check_session:
        expire_session(user, log.session_id)
    return log


def recalculate(log):
    if log.video_duration and log.video_duration > 0:
        ratio = log.watch_duration / log.video_duration
        log.completion_ratio = min(ratio, Decimal("1")).quantize(Decimal("0.00001"))
    else:
        log.completion_ratio = Decimal("0")
    if log.end_reason in EARLY_EXIT_REASONS and log.exposure_time and log.play_end_time:
        elapsed = max(0, (log.play_end_time - log.exposure_time).total_seconds())
        log.skip_time = Decimal(str(elapsed)).quantize(Decimal("0.001"))
    else:
        log.skip_time = None


def merge_totals(log, data, now=None):
    try:
        sequence = int(data.get("client_sequence"))
    except (TypeError, ValueError):
        raise BehaviorError("INVALID_FIELD", "client_sequence must be an integer.")
    if sequence <= log.last_client_sequence:
        return False
    requested = decimal_value(data.get("watch_duration"), "watch_duration", log.watch_duration)
    reference = log.last_heartbeat_at or log.play_start_time
    if reference:
        elapsed = Decimal(str(max(0, ((now or timezone.now()) - reference).total_seconds())))
        requested = min(requested, log.watch_duration + elapsed + Decimal("2"))
    log.watch_duration = max(log.watch_duration, requested)
    log.video_duration = decimal_value(data.get("video_duration"), "video_duration", log.video_duration)
    log.last_client_sequence = sequence
    recalculate(log)
    return True


def touch_session(user, session_id, at=None):
    at = at or timezone.now()
    session_queryset(user, session_id).filter(last_activity_at__lt=at).update(last_activity_at=at)


def close_session_logs(logs, end_at, open_end_reason):
    for log in logs.iterator():
        log.session_end = end_at
        if not log.play_end_time:
            log.play_end_time = end_at
            log.end_reason = open_end_reason
        recalculate(log)
        log.save(update_fields=["session_end", "play_end_time", "end_reason", "skip_time", "completion_ratio", "updated_at"])


def record_business_event(user, interaction_id, media, event_type, payload=None, state_field=None, state=None):
    del event_type, payload
    if not interaction_id or not user.is_authenticated or not state_field:
        return False
    with transaction.atomic():
        try:
            log = owned_interaction(user, interaction_id, lock=True)
        except BehaviorError:
            return False
        if log.media_id != media.pk:
            return False
        setattr(log, state_field, state)
        now = timezone.now()
        log.last_activity_at = now
        log.save(update_fields=[state_field, "last_activity_at", "updated_at"])
        touch_session(user, log.session_id, now)
    return True
