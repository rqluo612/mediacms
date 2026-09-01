import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from files.models import Media

from .behavior import CLIENT_EVENT_TYPES, IDLE_TIMEOUT_SECONDS, BehaviorError, close_session_logs, expire_session, merge_totals, owned_interaction, recalculate, session_queryset, touch_session
from .models import UserBehaviorLog


def error_response(exc):
    return Response({"code": exc.code, "detail": exc.detail}, status=exc.status_code)


def log_data(obj):
    def number(value):
        return float(value) if value is not None else None
    return {
        "interaction_id": obj.interaction_id,
        "session_id": obj.session_id,
        "user_id": obj.user_id,
        "video_id": obj.video_id,
        "algorithm_id": obj.algorithm_id,
        "play_start_time": obj.play_start_time,
        "play_end_time": obj.play_end_time,
        "video_duration": number(obj.video_duration),
        "watch_duration": number(obj.watch_duration),
        "skip_time": number(obj.skip_time),
        "completion_ratio": number(obj.completion_ratio),
        "session_start": obj.session_start,
        "session_end": obj.session_end,
        "liked": obj.liked,
        "commented": obj.commented,
        "shared": obj.shared,
        "collected": obj.collected,
        "followed": obj.followed,
        "end_reason": obj.end_reason,
    }


class BehaviorAPIView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser,)


class ViewingSessionList(BehaviorAPIView):
    def post(self, request):
        try:
            client_id = uuid.UUID(str(request.data.get("client_session_id")))
        except (TypeError, ValueError, AttributeError):
            return error_response(BehaviorError("INVALID_FIELD", "client_session_id must be a UUID."))
        session_id = f"S{client_id.hex.upper()}"
        try:
            latest = expire_session(request.user, session_id)
        except BehaviorError as exc:
            return error_response(exc)
        now = timezone.now()
        return Response(
            {
                "session_id": session_id,
                "user_id": request.user.username,
                "session_start": latest.session_start if latest else now,
                "last_activity_at": latest.last_activity_at if latest else now,
                "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
            },
            status=status.HTTP_200_OK if latest else status.HTTP_201_CREATED,
        )


class ViewingSessionEnd(BehaviorAPIView):
    def post(self, request, session_id):
        logs = session_queryset(request.user, session_id)
        if not logs.exists():
            return error_response(BehaviorError("NOT_FOUND", "Viewing session was not found.", 404))
        now = timezone.now()
        close_session_logs(logs, now, UserBehaviorLog.EndReason.NAVIGATE)
        return Response({"session_id": session_id, "session_end": now})


class InteractionList(BehaviorAPIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        if not isinstance(session_id, str) or len(session_id) != 33 or not session_id.startswith("S"):
            return error_response(BehaviorError("INVALID_FIELD", "Invalid session_id."))
        try:
            latest = expire_session(request.user, session_id)
            media = Media.objects.filter(friendly_token=request.data.get("video_id")).first()
            if not media:
                raise BehaviorError("NOT_FOUND", "Media was not found.", 404)
            context = str(request.data.get("entry_context", "DIRECT")).upper()
            if context not in UserBehaviorLog.Algorithm.values:
                raise BehaviorError("INVALID_FIELD", "Invalid entry_context.")
            now = timezone.now()
            log = UserBehaviorLog.objects.create(
                auth_user=request.user,
                user_id=request.user.username,
                session_id=session_id,
                session_start=latest.session_start if latest else now,
                media=media,
                video_id=media.friendly_token,
                video_duration=media.duration or None,
                algorithm_id=context,
                exposure_time=now,
                last_activity_at=now,
            )
            touch_session(request.user, session_id, now)
            return Response(log_data(log), status=status.HTTP_201_CREATED)
        except BehaviorError as exc:
            return error_response(exc)


class InteractionEvents(BehaviorAPIView):
    def post(self, request, interaction_id):
        event_type = request.data.get("event_type")
        if event_type not in CLIENT_EVENT_TYPES:
            return error_response(BehaviorError("INVALID_FIELD", "Invalid client event_type."))
        try:
            sequence = int(request.data.get("client_sequence"))
            with transaction.atomic():
                log = owned_interaction(request.user, interaction_id, lock=True)
                now = timezone.now()
                if event_type == "play" and not log.play_start_time:
                    log.play_start_time = now
                elif event_type == "share":
                    channel = (request.data.get("payload") or {}).get("channel")
                    if channel not in {"copy_link", "email", "system_share", "internal"}:
                        raise BehaviorError("INVALID_FIELD", "A successful share channel is required.")
                    log.shared = True
                log.last_client_sequence = max(log.last_client_sequence, sequence)
                log.last_activity_at = now
                recalculate(log)
                log.save()
                touch_session(request.user, log.session_id, now)
            return Response({"accepted": True, "interaction_id": interaction_id}, status=status.HTTP_201_CREATED)
        except (TypeError, ValueError):
            return error_response(BehaviorError("INVALID_FIELD", "client_sequence is required."))
        except BehaviorError as exc:
            return error_response(exc)


class InteractionHeartbeat(BehaviorAPIView):
    def patch(self, request, interaction_id):
        try:
            with transaction.atomic():
                log = owned_interaction(request.user, interaction_id, lock=True)
                if log.play_end_time:
                    return Response(log_data(log))
                changed = merge_totals(log, request.data)
                now = timezone.now()
                if changed:
                    log.last_activity_at = now
                    if request.data.get("playing") is True and request.data.get("visible") is True:
                        log.last_heartbeat_at = now
                    log.save()
                    touch_session(request.user, log.session_id, now)
            return Response(log_data(log))
        except BehaviorError as exc:
            return error_response(exc)


class InteractionEnd(BehaviorAPIView):
    def post(self, request, interaction_id):
        try:
            with transaction.atomic():
                log = owned_interaction(request.user, interaction_id, lock=True)
                if log.play_end_time:
                    return Response(log_data(log))
                reason = request.data.get("end_reason")
                if reason not in UserBehaviorLog.EndReason.values:
                    raise BehaviorError("INVALID_FIELD", "Invalid end_reason.")
                now = timezone.now()
                merge_totals(log, request.data, now)
                if reason == UserBehaviorLog.EndReason.ENDED and not log.play_start_time and log.watch_duration > 0:
                    log.play_start_time = now - timedelta(seconds=float(log.watch_duration))
                log.play_end_time = now
                log.end_reason = reason
                log.last_activity_at = now
                recalculate(log)
                log.save()
                touch_session(request.user, log.session_id, now)
            return Response(log_data(log))
        except BehaviorError as exc:
            return error_response(exc)
