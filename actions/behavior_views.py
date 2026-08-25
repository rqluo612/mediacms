import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from files.models import Media

from .behavior import CLIENT_EVENT_TYPES, IDLE_TIMEOUT_SECONDS, BehaviorError, bounded_totals, client_datetime, client_info, event_payload, merge_totals, owned_interaction, owned_session, recalculate, touch
from .models import BehaviorEvent, UserViewingSession, VideoInteractionLog


def error_response(exc):
    return Response({"code": exc.code, "detail": exc.detail}, status=exc.status_code)


def interaction_data(obj):
    def number(value):
        return float(value) if value is not None else None
    return {"interaction_id": obj.interaction_id, "session_id": obj.session_id, "video_id": obj.video_id, "algorithm_id": obj.algorithm_id, "served_at": obj.served_at, "play_start_time": obj.play_start_time, "play_end_time": obj.play_end_time, "video_duration": number(obj.video_duration), "watch_duration": number(obj.watch_duration), "skip_time": number(obj.skip_time), "play_latency": number(obj.play_latency), "completion_ratio": number(obj.completion_ratio), "watch_ratio_raw": number(obj.watch_ratio_raw), "last_heartbeat_at": obj.last_heartbeat_at, "end_reason": obj.end_reason}


class BehaviorAPIView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser,)


class ViewingSessionList(BehaviorAPIView):
    def post(self, request):
        try:
            client_id = uuid.UUID(str(request.data.get("client_session_id")))
        except (TypeError, ValueError, AttributeError):
            return error_response(BehaviorError("INVALID_FIELD", "client_session_id must be a UUID."))
        defaults = {"user": request.user, "participant_code": request.user.username, "django_session_key": request.session.session_key or "", "client_info": client_info(request.data.get("client_info", {}))}
        try:
            session, created = UserViewingSession.objects.get_or_create(client_session_id=client_id, defaults=defaults)
        except IntegrityError:
            session, created = UserViewingSession.objects.get(client_session_id=client_id), False
        if session.user_id != request.user.pk:
            return error_response(BehaviorError("FORBIDDEN", "client_session_id belongs to another user.", 403))
        if session.session_end:
            return error_response(BehaviorError("SESSION_EXPIRED", "Create a new client_session_id.", 409))
        return Response({"session_id": session.session_id, "user_id": session.participant_code, "session_start": session.session_start, "last_activity_at": session.last_activity_at, "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ViewingSessionEnd(BehaviorAPIView):
    def post(self, request, session_id):
        try:
            owned_session(request.user, session_id)
            with transaction.atomic():
                session = owned_session(request.user, session_id, lock=True)
                reason = request.data.get("reason", UserViewingSession.EndReason.EXPLICIT)
                if reason not in UserViewingSession.EndReason.values:
                    raise BehaviorError("INVALID_FIELD", "Invalid session end reason.")
                now = timezone.now()
                session.session_end, session.last_activity_at, session.end_reason = now, now, reason
                session.save(update_fields=["session_end", "last_activity_at", "end_reason", "updated_at"])
                session.interactions.filter(play_end_time__isnull=True).update(play_end_time=now, end_reason=VideoInteractionLog.EndReason.NAVIGATE)
            return Response({"session_id": session.session_id, "session_end": session.session_end, "end_reason": session.end_reason})
        except BehaviorError as exc:
            return error_response(exc)


class InteractionList(BehaviorAPIView):
    def post(self, request):
        try:
            owned_session(request.user, request.data.get("session_id"))
            with transaction.atomic():
                session = owned_session(request.user, request.data.get("session_id"), lock=True)
                media = Media.objects.filter(friendly_token=request.data.get("video_id")).first()
                if not media:
                    raise BehaviorError("NOT_FOUND", "Media was not found.", 404)
                context = str(request.data.get("entry_context", "DIRECT")).upper()
                allowed = {"DIRECT", "RELATED", "PLAYLIST", "SEARCH"}
                if context not in allowed:
                    raise BehaviorError("INVALID_FIELD", "Invalid entry_context.")
                interaction = VideoInteractionLog.objects.create(session=session, user=request.user, participant_code=session.participant_code, media=media, video_id=media.friendly_token, video_uid=media.uid, video_duration=media.duration or None, algorithm_id=context)
                touch(session)
            return Response(interaction_data(interaction), status=status.HTTP_201_CREATED)
        except BehaviorError as exc:
            return error_response(exc)


class InteractionEvents(BehaviorAPIView):
    def post(self, request, interaction_id):
        try:
            event_id = uuid.UUID(str(request.data.get("event_id")))
            event_type = request.data.get("event_type")
            if event_type not in CLIENT_EVENT_TYPES:
                raise BehaviorError("INVALID_FIELD", "Invalid client event_type.")
            payload = event_payload(request.data.get("payload", {}))
            owned_interaction(request.user, interaction_id)
            with transaction.atomic():
                interaction = owned_interaction(request.user, interaction_id, lock=True)
                existing = BehaviorEvent.objects.filter(event_id=event_id).first()
                if existing:
                    requested_sequence = int(request.data.get("client_sequence"))
                    if (
                        existing.interaction_id != interaction_id
                        or existing.event_type != event_type
                        or existing.client_sequence != requested_sequence
                        or existing.payload != payload
                    ):
                        raise BehaviorError("EVENT_CONFLICT", "event_id already exists with different content.", 409)
                    return Response({"event_id": existing.event_id, "accepted": True, "interaction_id": interaction_id})
                sequence = int(request.data.get("client_sequence"))
                now = timezone.now()
                if event_type == "exposure" and not interaction.exposure_time:
                    interaction.exposure_time = now
                if event_type == "play" and not interaction.play_start_time:
                    interaction.play_start_time = now
                if event_type == "replay":
                    interaction.replay_count += 1
                if event_type == "share":
                    if payload.get("channel") not in {"copy_link", "email", "system_share", "internal"}:
                        raise BehaviorError("INVALID_FIELD", "A successful share channel is required.")
                    interaction.shared = True
                interaction.last_client_sequence = max(interaction.last_client_sequence, sequence)
                recalculate(interaction)
                interaction.save()
                BehaviorEvent.objects.create(event_id=event_id, session=interaction.session, interaction=interaction, user=request.user, event_type=event_type, source=BehaviorEvent.Source.CLIENT, client_sequence=sequence, client_time=client_datetime(request.data.get("client_time")), payload=payload)
                touch(interaction.session)
            return Response({"event_id": event_id, "accepted": True, "interaction_id": interaction_id}, status=status.HTTP_201_CREATED)
        except (TypeError, ValueError, AttributeError):
            return error_response(BehaviorError("INVALID_FIELD", "event_id and client_sequence are required."))
        except IntegrityError:
            return error_response(BehaviorError("EVENT_CONFLICT", "client_sequence already exists.", 409))
        except BehaviorError as exc:
            return error_response(exc)


class InteractionHeartbeat(BehaviorAPIView):
    def patch(self, request, interaction_id):
        try:
            owned_interaction(request.user, interaction_id)
            with transaction.atomic():
                interaction = owned_interaction(request.user, interaction_id, lock=True)
                if interaction.play_end_time:
                    return Response(interaction_data(interaction))
                changed = merge_totals(interaction, bounded_totals(interaction, request.data))
                if changed and request.data.get("playing") is True and request.data.get("visible") is True:
                    now = timezone.now()
                    interaction.last_heartbeat_at = now
                    interaction.save()
                    touch(interaction.session, now)
            return Response(interaction_data(interaction))
        except BehaviorError as exc:
            return error_response(exc)


class InteractionEnd(BehaviorAPIView):
    def post(self, request, interaction_id):
        try:
            owned_interaction(request.user, interaction_id)
            with transaction.atomic():
                interaction = owned_interaction(request.user, interaction_id, lock=True)
                if interaction.play_end_time:
                    return Response(interaction_data(interaction))
                reason = request.data.get("end_reason")
                if reason not in VideoInteractionLog.EndReason.values:
                    raise BehaviorError("INVALID_FIELD", "Invalid end_reason.")
                now = timezone.now()
                merge_totals(interaction, bounded_totals(interaction, request.data, now))
                interaction.play_end_time, interaction.end_reason = now, reason
                recalculate(interaction)
                interaction.save()
                BehaviorEvent.objects.create(event_id=request.data.get("event_id") or uuid.uuid4(), session=interaction.session, interaction=interaction, user=request.user, event_type=BehaviorEvent.EventType.END, source=BehaviorEvent.Source.CLIENT, client_sequence=request.data.get("client_sequence"), client_time=client_datetime(request.data.get("client_time")), payload={"end_reason": reason})
                touch(interaction.session, now)
            return Response(interaction_data(interaction))
        except IntegrityError:
            return error_response(BehaviorError("EVENT_CONFLICT", "End event already exists.", 409))
        except BehaviorError as exc:
            return error_response(exc)
