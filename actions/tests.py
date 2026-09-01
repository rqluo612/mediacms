import uuid
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from files.models import Media
from files.serializers import MediaSerializer
from users.models import User

from .models import UserBehaviorLog


class BehaviorLoggingApiTest(TestCase):
    fixtures = ["fixtures/categories.json", "fixtures/encoding_profiles.json"]

    def setUp(self):
        self.user = User.objects.create_user(username="P001", password="behavior-test-password", email="p001@example.test")
        self.media = Media(title="Behavior test", user=self.user, media_file="original/behavior-test.mp4", friendly_token="BEHAVIORTEST", duration=30)
        Media.objects.bulk_create([self.media])
        self.client = Client()
        self.assertTrue(self.client.login(username="P001", password="behavior-test-password"))

    def create_session(self):
        response = self.client.post("/api/v1/behavior/sessions", {"client_session_id": str(uuid.uuid4())}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        return response.json()["session_id"]

    def create_log(self, session_id):
        response = self.client.post("/api/v1/behavior/interactions", {"session_id": session_id, "video_id": self.media.friendly_token, "entry_context": "DIRECT"}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        return response.json()["interaction_id"]

    def test_single_log_collects_playback_and_share_summary(self):
        interaction_id = self.create_log(self.create_session())
        for sequence, event_type in ((1, "exposure"), (2, "play"), (3, "share")):
            payload = {"channel": "copy_link"} if event_type == "share" else {"position": 0, "visible": True}
            response = self.client.post(f"/api/v1/behavior/interactions/{interaction_id}/events", {"event_id": str(uuid.uuid4()), "client_sequence": sequence, "event_type": event_type, "payload": payload}, content_type="application/json")
            self.assertEqual(response.status_code, 201)
        UserBehaviorLog.objects.filter(interaction_id=interaction_id).update(play_start_time=timezone.now() - timedelta(seconds=24), exposure_time=timezone.now() - timedelta(seconds=25))
        heartbeat = self.client.patch(f"/api/v1/behavior/interactions/{interaction_id}/heartbeat", {"client_sequence": 4, "playing": True, "visible": True, "watch_duration": 23.4, "video_duration": 30}, content_type="application/json")
        self.assertEqual(heartbeat.json()["completion_ratio"], 0.78)
        ended = self.client.post(f"/api/v1/behavior/interactions/{interaction_id}/end", {"client_sequence": 5, "end_reason": "next", "watch_duration": 23.4, "video_duration": 30}, content_type="application/json")
        self.assertEqual(ended.status_code, 200)
        self.assertGreater(ended.json()["skip_time"], 0)
        log = UserBehaviorLog.objects.get(interaction_id=interaction_id)
        self.assertEqual(log.user_id, "P001")
        self.assertTrue(log.shared)
        self.assertEqual(UserBehaviorLog.objects.count(), 1)

    def test_idle_session_ends_all_rows_at_last_activity(self):
        session_id = self.create_session()
        interaction_id = self.create_log(session_id)
        last_activity = timezone.now() - timedelta(minutes=6)
        UserBehaviorLog.objects.filter(interaction_id=interaction_id).update(last_activity_at=last_activity, session_start=timezone.now() - timedelta(minutes=10))
        response = self.client.post("/api/v1/behavior/interactions", {"session_id": session_id, "video_id": self.media.friendly_token, "entry_context": "DIRECT"}, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        log = UserBehaviorLog.objects.get(interaction_id=interaction_id)
        self.assertEqual(log.session_end, last_activity)
        self.assertEqual(log.end_reason, "session_timeout")
        self.assertIsNotNone(log.skip_time)

    def test_ended_event_recovers_missing_play_start_from_measured_watch_time(self):
        interaction_id = self.create_log(self.create_session())
        ended = self.client.post(
            f"/api/v1/behavior/interactions/{interaction_id}/end",
            {"client_sequence": 1, "end_reason": "ended", "watch_duration": 2.1, "video_duration": 2.216},
            content_type="application/json",
        )
        self.assertEqual(ended.status_code, 200)
        log = UserBehaviorLog.objects.get(interaction_id=interaction_id)
        self.assertIsNotNone(log.play_start_time)
        self.assertEqual(float(log.watch_duration), 2.1)
        self.assertGreater(float(log.completion_ratio), 0.94)
        self.assertIsNone(log.skip_time)

    def test_anonymous_user_is_rejected(self):
        response = Client().post("/api/v1/behavior/sessions", {"client_session_id": str(uuid.uuid4())}, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_media_serializer_includes_optional_behavior_context(self):
        request = APIRequestFactory().get("/api/v1/media", HTTP_HOST="localhost")
        data = MediaSerializer(self.media, context={"request": request}).data
        self.assertIn("behavior_context", data)
        self.assertIsNone(data["behavior_context"])
