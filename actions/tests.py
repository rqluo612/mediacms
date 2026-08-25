import uuid
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from files.models import Media
from files.serializers import MediaSerializer
from users.models import User

from .models import BehaviorEvent, UserViewingSession, VideoInteractionLog


class BehaviorLoggingApiTest(TestCase):
    fixtures = ["fixtures/categories.json", "fixtures/encoding_profiles.json"]

    def setUp(self):
        self.password = "behavior-test-password"
        self.user = User.objects.create_user(username="P001", password=self.password, email="p001@example.test")
        self.media = Media(
            title="Behavior test",
            user=self.user,
            media_file="original/behavior-test.mp4",
            friendly_token="BEHAVIORTEST",
            duration=30,
        )
        Media.objects.bulk_create([self.media])
        self.client = Client()
        self.assertTrue(self.client.login(username=self.user.username, password=self.password))

    def create_session(self):
        response = self.client.post(
            "/api/v1/behavior/sessions",
            {"client_session_id": str(uuid.uuid4()), "client_info": {"timezone": "Asia/Shanghai", "ignored": "not stored"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["session_id"]

    def test_session_interaction_event_heartbeat_and_end(self):
        session_id = self.create_session()
        interaction_response = self.client.post(
            "/api/v1/behavior/interactions",
            {"session_id": session_id, "video_id": self.media.friendly_token, "entry_context": "DIRECT"},
            content_type="application/json",
        )
        self.assertEqual(interaction_response.status_code, 201)
        interaction_id = interaction_response.json()["interaction_id"]

        for sequence, event_type in ((1, "exposure"), (2, "play")):
            response = self.client.post(
                f"/api/v1/behavior/interactions/{interaction_id}/events",
                {"event_id": str(uuid.uuid4()), "client_sequence": sequence, "event_type": event_type, "payload": {"position": 0, "visible": True}},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 201)

        VideoInteractionLog.objects.filter(interaction_id=interaction_id).update(
            play_start_time=timezone.now() - timedelta(seconds=24)
        )

        heartbeat = self.client.patch(
            f"/api/v1/behavior/interactions/{interaction_id}/heartbeat",
            {"client_sequence": 3, "playing": True, "visible": True, "watch_duration": 23.4, "video_duration": 30, "max_play_position": 23.4, "replay_count": 0},
            content_type="application/json",
        )
        self.assertEqual(heartbeat.status_code, 200)
        self.assertEqual(heartbeat.json()["completion_ratio"], 0.78)

        ended = self.client.post(
            f"/api/v1/behavior/interactions/{interaction_id}/end",
            {"event_id": str(uuid.uuid4()), "client_sequence": 4, "end_reason": "next", "watch_duration": 23.4, "video_duration": 30, "max_play_position": 23.4, "replay_count": 0},
            content_type="application/json",
        )
        self.assertEqual(ended.status_code, 200)
        self.assertIsNone(ended.json()["skip_time"])
        self.assertEqual(BehaviorEvent.objects.filter(interaction_id=interaction_id).count(), 3)

    def test_idle_session_ends_at_last_activity(self):
        session_id = self.create_session()
        last_activity = timezone.now() - timedelta(minutes=6)
        UserViewingSession.objects.filter(session_id=session_id).update(
            session_start=timezone.now() - timedelta(minutes=10),
            last_activity_at=last_activity,
        )
        response = self.client.post(
            "/api/v1/behavior/interactions",
            {"session_id": session_id, "video_id": self.media.friendly_token, "entry_context": "DIRECT"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        session = UserViewingSession.objects.get(session_id=session_id)
        self.assertEqual(session.session_end, last_activity)
        self.assertEqual(session.end_reason, "idle_timeout")

    def test_anonymous_user_is_rejected(self):
        response = Client().post("/api/v1/behavior/sessions", {"client_session_id": str(uuid.uuid4())}, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_media_serializer_includes_optional_behavior_context(self):
        request = APIRequestFactory().get("/api/v1/media", HTTP_HOST="localhost")
        data = MediaSerializer(self.media, context={"request": request}).data
        self.assertIn("behavior_context", data)
        self.assertIsNone(data["behavior_context"])
