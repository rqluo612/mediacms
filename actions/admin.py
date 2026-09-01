from django.contrib import admin

from .models import UserBehaviorLog


@admin.register(UserBehaviorLog)
class UserBehaviorLogAdmin(admin.ModelAdmin):
    list_display = (
        "user_id", "session_id", "video_id", "algorithm_id", "play_start_time",
        "play_end_time", "video_duration", "watch_duration", "skip_time",
        "completion_ratio", "session_start", "session_end", "liked", "commented",
        "shared", "collected", "followed",
    )
    search_fields = ("interaction_id", "user_id", "session_id", "video_id", "auth_user__username")
    list_filter = ("algorithm_id", "end_reason", "liked", "commented", "shared", "collected", "followed")
    readonly_fields = ("interaction_id", "created_at", "updated_at")
