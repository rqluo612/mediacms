# Generated for MediaCMS behavior logging.
import uuid
from decimal import Decimal

import actions.models
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("actions", "0003_auto_20201201_0712"),
        ("files", "0018_embedmediacourse"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserViewingSession",
            fields=[
                ("session_id", models.CharField(default=actions.models.new_session_id, editable=False, max_length=33, primary_key=True, serialize=False)),
                ("participant_code", models.CharField(db_index=True, max_length=64)),
                ("django_session_key", models.CharField(blank=True, db_index=True, max_length=40)),
                ("client_session_id", models.UUIDField(unique=True)),
                ("session_start", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("session_end", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_activity_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("end_reason", models.CharField(blank=True, choices=[("explicit", "Explicit exit"), ("idle_timeout", "Idle timeout"), ("logout", "Logout"), ("page_close", "Page close"), ("system", "System cleanup")], max_length=20)),
                ("client_info", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="viewing_sessions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="VideoInteractionLog",
            fields=[
                ("interaction_id", models.CharField(default=actions.models.new_interaction_id, editable=False, max_length=33, primary_key=True, serialize=False)),
                ("participant_code", models.CharField(db_index=True, max_length=64)),
                ("video_id", models.CharField(db_index=True, max_length=150)),
                ("video_uid", models.UUIDField(blank=True, null=True)),
                ("recommendation_request_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("algorithm_id", models.CharField(choices=[("CF", "Collaborative filtering"), ("CONTENT", "Content based"), ("KG", "Knowledge graph"), ("LEGACY", "MediaCMS legacy fallback"), ("RELATED", "Related media"), ("PLAYLIST", "Playlist navigation"), ("DIRECT", "Direct page entry"), ("SEARCH", "Search result"), ("UNKNOWN", "Unknown")], db_index=True, default="UNKNOWN", max_length=20)),
                ("algorithm_version", models.CharField(blank=True, max_length=64)),
                ("recommendation_rank", models.PositiveIntegerField(blank=True, null=True)),
                ("served_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("exposure_time", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("play_start_time", models.DateTimeField(blank=True, null=True)),
                ("play_end_time", models.DateTimeField(blank=True, null=True)),
                ("last_heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("end_reason", models.CharField(blank=True, choices=[("ended", "Played to end"), ("swipe", "User swiped away"), ("next", "Next video"), ("previous", "Previous video"), ("page_close", "Page closed"), ("navigate", "Page navigation"), ("background_timeout", "Background timeout"), ("error", "Playback error"), ("session_timeout", "Session timeout")], max_length=24)),
                ("video_duration", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("watch_duration", models.DecimalField(decimal_places=3, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("skip_time", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("play_latency", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("completion_ratio", models.DecimalField(decimal_places=5, default=0, max_digits=6, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("watch_ratio_raw", models.DecimalField(decimal_places=5, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("max_play_position", models.DecimalField(decimal_places=3, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("replay_count", models.PositiveIntegerField(default=0)),
                ("last_client_sequence", models.BigIntegerField(default=-1)),
                ("liked", models.BooleanField(default=False)),
                ("commented", models.BooleanField(default=False)),
                ("shared", models.BooleanField(default=False)),
                ("collected", models.BooleanField(default=False)),
                ("followed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("media", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="behavior_interactions", to="files.media")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="interactions", to="actions.userviewingsession")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="video_interactions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="BehaviorEvent",
            fields=[
                ("event_id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("event_type", models.CharField(choices=[("exposure", "Exposure"), ("play", "First play"), ("resume", "Resume"), ("pause", "Pause"), ("seek", "Seek"), ("replay", "Replay"), ("end", "Playback end"), ("like", "Like"), ("unlike", "Unlike"), ("dislike", "Dislike"), ("comment", "Comment"), ("comment_delete", "Comment deleted"), ("share", "Share"), ("collect", "Added to playlist"), ("uncollect", "Removed from playlist"), ("follow", "Follow author"), ("unfollow", "Unfollow author")], db_index=True, max_length=24)),
                ("source", models.CharField(choices=[("client", "Client"), ("server", "Server")], max_length=10)),
                ("client_sequence", models.BigIntegerField(blank=True, null=True)),
                ("client_time", models.DateTimeField(blank=True, null=True)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("interaction", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="events", to="actions.videointeractionlog")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="actions.userviewingsession")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="behavior_events", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex("userviewingsession", models.Index(fields=["user", "-session_start"], name="beh_session_user_start_idx")),
        migrations.AddIndex("userviewingsession", models.Index(fields=["participant_code", "-session_start"], name="beh_session_part_start_idx")),
        migrations.AddIndex("userviewingsession", models.Index(fields=["session_end", "last_activity_at"], name="beh_session_end_active_idx")),
        migrations.AddConstraint("userviewingsession", models.CheckConstraint(condition=Q(session_end__isnull=True) | Q(session_end__gte=models.F("session_start")), name="behavior_session_end_after_start")),
        migrations.AddIndex("videointeractionlog", models.Index(fields=["session", "served_at"], name="beh_inter_session_served_idx")),
        migrations.AddIndex("videointeractionlog", models.Index(fields=["user", "-served_at"], name="beh_inter_user_served_idx")),
        migrations.AddIndex("videointeractionlog", models.Index(fields=["participant_code", "-served_at"], name="beh_inter_part_served_idx")),
        migrations.AddIndex("videointeractionlog", models.Index(fields=["video_id", "-served_at"], name="beh_inter_video_served_idx")),
        migrations.AddIndex("videointeractionlog", models.Index(fields=["algorithm_id", "-served_at"], name="beh_inter_algo_served_idx")),
        migrations.AddIndex("videointeractionlog", models.Index(fields=["recommendation_request_id", "recommendation_rank"], name="beh_inter_request_rank_idx")),
        migrations.AddConstraint("videointeractionlog", models.CheckConstraint(condition=Q(completion_ratio__gte=0) & Q(completion_ratio__lte=1), name="behavior_completion_ratio_0_1")),
        migrations.AddConstraint("videointeractionlog", models.CheckConstraint(condition=Q(play_end_time__isnull=True) | Q(play_start_time__isnull=True) | Q(play_end_time__gte=models.F("play_start_time")), name="behavior_play_end_after_start")),
        migrations.AddIndex("behaviorevent", models.Index(fields=["session", "received_at"], name="beh_event_session_recv_idx")),
        migrations.AddIndex("behaviorevent", models.Index(fields=["interaction", "received_at"], name="beh_event_inter_recv_idx")),
        migrations.AddIndex("behaviorevent", models.Index(fields=["user", "event_type", "-received_at"], name="beh_event_user_type_recv_idx")),
        migrations.AddConstraint("behaviorevent", models.UniqueConstraint(condition=Q(interaction__isnull=False, client_sequence__isnull=False), fields=("interaction", "client_sequence"), name="behavior_unique_interaction_client_sequence")),
    ]
