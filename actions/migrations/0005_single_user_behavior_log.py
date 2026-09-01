from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone

import actions.models


class Migration(migrations.Migration):
    dependencies = [("actions", "0004_behavior_logging"), migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("files", "0018_embedmediacourse")]

    operations = [
        migrations.DeleteModel(name="BehaviorEvent"),
        migrations.DeleteModel(name="VideoInteractionLog"),
        migrations.DeleteModel(name="UserViewingSession"),
        migrations.CreateModel(
            name="UserBehaviorLog",
            fields=[
                ("interaction_id", models.CharField(default=actions.models.new_interaction_id, editable=False, max_length=33, primary_key=True, serialize=False)),
                ("user_id", models.CharField(db_index=True, help_text="User/participant identifier, for example P001", max_length=64)),
                ("session_id", models.CharField(db_index=True, max_length=33)),
                ("video_id", models.CharField(db_index=True, max_length=150)),
                ("recommendation_request_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("algorithm_id", models.CharField(choices=[("CF", "Collaborative filtering"), ("CONTENT", "Content based"), ("KG", "Knowledge graph"), ("LEGACY", "MediaCMS legacy fallback"), ("RELATED", "Related media"), ("PLAYLIST", "Playlist navigation"), ("DIRECT", "Direct page entry"), ("SEARCH", "Search result"), ("UNKNOWN", "Unknown")], db_index=True, default="UNKNOWN", max_length=20)),
                ("algorithm_version", models.CharField(blank=True, max_length=64)),
                ("recommendation_rank", models.PositiveIntegerField(blank=True, null=True)),
                ("exposure_time", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("play_start_time", models.DateTimeField(blank=True, null=True)),
                ("play_end_time", models.DateTimeField(blank=True, null=True)),
                ("end_reason", models.CharField(blank=True, choices=[("ended", "Played to end"), ("next", "Next video"), ("previous", "Previous video"), ("page_close", "Page closed"), ("navigate", "Page navigation"), ("background_timeout", "Background timeout"), ("error", "Playback error"), ("session_timeout", "Session timeout")], max_length=24)),
                ("video_duration", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("watch_duration", models.DecimalField(decimal_places=3, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("skip_time", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("completion_ratio", models.DecimalField(decimal_places=5, default=0, max_digits=6, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("session_start", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("session_end", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("liked", models.BooleanField(default=False)),
                ("commented", models.BooleanField(default=False)),
                ("shared", models.BooleanField(default=False)),
                ("collected", models.BooleanField(default=False)),
                ("followed", models.BooleanField(default=False)),
                ("last_activity_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("last_client_sequence", models.BigIntegerField(default=-1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("auth_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="behavior_logs", to=settings.AUTH_USER_MODEL)),
                ("media", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="behavior_interactions", to="files.media")),
            ],
            options={
                "indexes": [models.Index(fields=["auth_user", "-created_at"], name="beh_log_auth_created_idx"), models.Index(fields=["user_id", "-created_at"], name="beh_log_user_created_idx"), models.Index(fields=["session_id", "created_at"], name="beh_log_session_created_idx"), models.Index(fields=["video_id", "-created_at"], name="beh_log_video_created_idx"), models.Index(fields=["session_end", "last_activity_at"], name="beh_log_end_active_idx")],
                "constraints": [models.CheckConstraint(condition=models.Q(("completion_ratio__gte", 0), ("completion_ratio__lte", 1)), name="user_behavior_completion_0_1"), models.CheckConstraint(condition=models.Q(("play_end_time__isnull", True), ("play_start_time__isnull", True), ("play_end_time__gte", models.F("play_start_time")), _connector="OR"), name="user_behavior_play_end_after_start"), models.CheckConstraint(condition=models.Q(("session_end__isnull", True), ("session_end__gte", models.F("session_start")), _connector="OR"), name="user_behavior_session_end_after_start")],
            },
        ),
    ]
