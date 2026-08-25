from django.contrib import admin

from .models import BehaviorEvent, UserViewingSession, VideoInteractionLog


@admin.register(UserViewingSession)
class UserViewingSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "participant_code", "session_start", "session_end", "end_reason")
    search_fields = ("session_id", "participant_code", "user__username")
    list_filter = ("end_reason",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(VideoInteractionLog)
class VideoInteractionLogAdmin(admin.ModelAdmin):
    list_display = ("interaction_id", "participant_code", "video_id", "algorithm_id", "watch_duration", "end_reason")
    search_fields = ("interaction_id", "participant_code", "video_id")
    list_filter = ("algorithm_id", "end_reason", "liked", "commented", "shared", "collected")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BehaviorEvent)
class BehaviorEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "source", "participant", "received_at")
    search_fields = ("event_id", "interaction__interaction_id", "user__username")
    list_filter = ("event_type", "source")
    readonly_fields = ("event_id", "session", "interaction", "user", "event_type", "source", "client_sequence", "client_time", "received_at", "payload")

    @admin.display(description="Participant")
    def participant(self, obj):
        return obj.session.participant_code

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
