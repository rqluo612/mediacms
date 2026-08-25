import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from files.models import Media
from users.models import User

USER_MEDIA_ACTIONS = (
    ("like", "Like"),
    ("dislike", "Dislike"),
    ("watch", "Watch"),
    ("report", "Report"),
    ("rate", "Rate"),
)


class MediaAction(models.Model):
    """Stores different user actions"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True,
        blank=True,
        null=True,
        related_name="useractions",
    )
    session_key = models.CharField(
        max_length=33,
        db_index=True,
        blank=True,
        null=True,
        help_text="for not logged in users",
    )

    action = models.CharField(max_length=20, choices=USER_MEDIA_ACTIONS, default="watch")
    # keeps extra info, eg on report action, why it is reported
    extra_info = models.TextField(blank=True, null=True)

    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name="mediaactions")
    action_date = models.DateTimeField(auto_now_add=True)
    remote_ip = models.CharField(max_length=40, blank=True, null=True)

    def save(self, *args, **kwargs):
        super(MediaAction, self).save(*args, **kwargs)

    def __str__(self):
        return self.action

    class Meta:
        indexes = [
            models.Index(fields=["user", "action", "-action_date"]),
            models.Index(fields=["session_key", "action"]),
        ]


def new_session_id():
    return f"S{uuid.uuid4().hex.upper()}"


def new_interaction_id():
    return f"I{uuid.uuid4().hex.upper()}"


class UserViewingSession(models.Model):
    class EndReason(models.TextChoices):
        EXPLICIT = "explicit", "Explicit exit"
        IDLE_TIMEOUT = "idle_timeout", "Idle timeout"
        LOGOUT = "logout", "Logout"
        PAGE_CLOSE = "page_close", "Page close"
        SYSTEM = "system", "System cleanup"

    session_id = models.CharField(primary_key=True, max_length=33, default=new_session_id, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="viewing_sessions")
    participant_code = models.CharField(max_length=64, db_index=True)
    django_session_key = models.CharField(max_length=40, blank=True, db_index=True)
    client_session_id = models.UUIDField(unique=True)
    session_start = models.DateTimeField(default=timezone.now, db_index=True)
    session_end = models.DateTimeField(null=True, blank=True, db_index=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    end_reason = models.CharField(max_length=20, choices=EndReason.choices, blank=True)
    client_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-session_start"], name="beh_session_user_start_idx"), models.Index(fields=["participant_code", "-session_start"], name="beh_session_part_start_idx"), models.Index(fields=["session_end", "last_activity_at"], name="beh_session_end_active_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(session_end__isnull=True) | models.Q(session_end__gte=models.F("session_start")), name="behavior_session_end_after_start")]


class VideoInteractionLog(models.Model):
    class Algorithm(models.TextChoices):
        CF = "CF", "Collaborative filtering"
        CONTENT = "CONTENT", "Content based"
        KG = "KG", "Knowledge graph"
        LEGACY = "LEGACY", "MediaCMS legacy fallback"
        RELATED = "RELATED", "Related media"
        PLAYLIST = "PLAYLIST", "Playlist navigation"
        DIRECT = "DIRECT", "Direct page entry"
        SEARCH = "SEARCH", "Search result"
        UNKNOWN = "UNKNOWN", "Unknown"

    class EndReason(models.TextChoices):
        ENDED = "ended", "Played to end"
        SWIPE = "swipe", "User swiped away"
        NEXT = "next", "Next video"
        PREVIOUS = "previous", "Previous video"
        PAGE_CLOSE = "page_close", "Page closed"
        NAVIGATE = "navigate", "Page navigation"
        BACKGROUND_TIMEOUT = "background_timeout", "Background timeout"
        ERROR = "error", "Playback error"
        SESSION_TIMEOUT = "session_timeout", "Session timeout"

    interaction_id = models.CharField(primary_key=True, max_length=33, default=new_interaction_id, editable=False)
    session = models.ForeignKey(UserViewingSession, on_delete=models.CASCADE, related_name="interactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="video_interactions")
    participant_code = models.CharField(max_length=64, db_index=True)
    media = models.ForeignKey("files.Media", null=True, blank=True, on_delete=models.SET_NULL, related_name="behavior_interactions")
    video_id = models.CharField(max_length=150, db_index=True)
    video_uid = models.UUIDField(null=True, blank=True)
    recommendation_request_id = models.UUIDField(null=True, blank=True, db_index=True)
    algorithm_id = models.CharField(max_length=20, choices=Algorithm.choices, default=Algorithm.UNKNOWN, db_index=True)
    algorithm_version = models.CharField(max_length=64, blank=True)
    recommendation_rank = models.PositiveIntegerField(null=True, blank=True)
    served_at = models.DateTimeField(default=timezone.now, db_index=True)
    exposure_time = models.DateTimeField(null=True, blank=True, db_index=True)
    play_start_time = models.DateTimeField(null=True, blank=True)
    play_end_time = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=24, choices=EndReason.choices, blank=True)
    video_duration = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    watch_duration = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(Decimal("0"))])
    skip_time = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    play_latency = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    completion_ratio = models.DecimalField(max_digits=6, decimal_places=5, default=0, validators=[MinValueValidator(Decimal("0"))])
    watch_ratio_raw = models.DecimalField(max_digits=12, decimal_places=5, default=0, validators=[MinValueValidator(Decimal("0"))])
    max_play_position = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(Decimal("0"))])
    replay_count = models.PositiveIntegerField(default=0)
    last_client_sequence = models.BigIntegerField(default=-1)
    liked = models.BooleanField(default=False)
    commented = models.BooleanField(default=False)
    shared = models.BooleanField(default=False)
    collected = models.BooleanField(default=False)
    followed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["session", "served_at"], name="beh_inter_session_served_idx"), models.Index(fields=["user", "-served_at"], name="beh_inter_user_served_idx"), models.Index(fields=["participant_code", "-served_at"], name="beh_inter_part_served_idx"), models.Index(fields=["video_id", "-served_at"], name="beh_inter_video_served_idx"), models.Index(fields=["algorithm_id", "-served_at"], name="beh_inter_algo_served_idx"), models.Index(fields=["recommendation_request_id", "recommendation_rank"], name="beh_inter_request_rank_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(completion_ratio__gte=0) & models.Q(completion_ratio__lte=1), name="behavior_completion_ratio_0_1"), models.CheckConstraint(condition=models.Q(play_end_time__isnull=True) | models.Q(play_start_time__isnull=True) | models.Q(play_end_time__gte=models.F("play_start_time")), name="behavior_play_end_after_start")]


class BehaviorEvent(models.Model):
    class EventType(models.TextChoices):
        EXPOSURE = "exposure", "Exposure"
        PLAY = "play", "First play"
        RESUME = "resume", "Resume"
        PAUSE = "pause", "Pause"
        SEEK = "seek", "Seek"
        REPLAY = "replay", "Replay"
        END = "end", "Playback end"
        LIKE = "like", "Like"
        UNLIKE = "unlike", "Unlike"
        DISLIKE = "dislike", "Dislike"
        COMMENT = "comment", "Comment"
        COMMENT_DELETE = "comment_delete", "Comment deleted"
        SHARE = "share", "Share"
        COLLECT = "collect", "Added to playlist"
        UNCOLLECT = "uncollect", "Removed from playlist"
        FOLLOW = "follow", "Follow author"
        UNFOLLOW = "unfollow", "Unfollow author"

    class Source(models.TextChoices):
        CLIENT = "client", "Client"
        SERVER = "server", "Server"

    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    session = models.ForeignKey(UserViewingSession, on_delete=models.CASCADE, related_name="events")
    interaction = models.ForeignKey(VideoInteractionLog, null=True, blank=True, on_delete=models.CASCADE, related_name="events")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="behavior_events")
    event_type = models.CharField(max_length=24, choices=EventType.choices, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices)
    client_sequence = models.BigIntegerField(null=True, blank=True)
    client_time = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["session", "received_at"], name="beh_event_session_recv_idx"), models.Index(fields=["interaction", "received_at"], name="beh_event_inter_recv_idx"), models.Index(fields=["user", "event_type", "-received_at"], name="beh_event_user_type_recv_idx")]
        constraints = [models.UniqueConstraint(fields=["interaction", "client_sequence"], condition=models.Q(interaction__isnull=False, client_sequence__isnull=False), name="behavior_unique_interaction_client_sequence")]
