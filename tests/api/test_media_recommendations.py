from unittest.mock import patch

from django.core.cache import cache
from django.core.files import File
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from actions.models import MediaAction
from files.models import Media, Playlist, PlaylistMedia
from files.services.recommendations import (
    build_and_cache_item_similarities,
    get_recommended_media,
)
from files.tests import create_account


CF_SETTINGS = {
    "ENABLE_COLLABORATIVE_FILTERING": True,
    "COLLABORATIVE_FILTERING_MIN_INTERACTIONS": 2,
    "COLLABORATIVE_FILTERING_WEIGHTS": {"watch": 1.0, "like": 3.0, "playlist": 4.0},
    "COLLABORATIVE_FILTERING_ALGORITHM_VERSION": "item_cf_test",
}


@override_settings(**CF_SETTINGS)
class MediaRecommendationApiTest(TestCase):
    fixtures = ["fixtures/categories.json", "fixtures/encoding_profiles.json"]

    def setUp(self):
        cache.clear()
        self.password = "this_is_a_fake_password"
        self.target = create_account(username="recommend_target", password=self.password)
        self.peer_one = create_account(username="recommend_peer_one", password=self.password)
        self.peer_two = create_account(username="recommend_peer_two", password=self.password)
        self.media_a = self._create_media("Media A")
        self.media_b = self._create_media("Media B")
        self.media_c = self._create_media("Media C")
        self.media_d = self._create_media("Media D")
        self.private_media = self._create_media("Private candidate", listable=False, state="private")

        self._action(self.target, self.media_a, "watch")
        self._action(self.target, self.media_b, "like")

        self._action(self.peer_one, self.media_a, "watch")
        self._action(self.peer_one, self.media_b, "like")
        self._add_to_playlist(self.peer_one, self.media_c)
        self._add_to_playlist(self.peer_one, self.private_media)

        self._action(self.peer_two, self.media_b, "like")
        self._add_to_playlist(self.peer_two, self.media_c)
        self._action(self.peer_two, self.media_d, "watch")
        build_and_cache_item_similarities()

    def tearDown(self):
        cache.clear()

    def _create_media(self, title, listable=True, state="public"):
        with open("fixtures/test_image2.jpg", "rb") as source:
            media = Media.objects.create(
                title=title,
                user=self.peer_one,
                media_file=File(source),
                state=state,
                encoding_status="success",
                is_reviewed=True,
            )
        Media.objects.filter(pk=media.pk).update(
            state=state,
            encoding_status="success",
            is_reviewed=True,
            listable=listable,
        )
        media.refresh_from_db()
        return media

    @staticmethod
    def _action(user, media, action):
        MediaAction.objects.create(user=user, media=media, action=action)

    @staticmethod
    def _add_to_playlist(user, media):
        playlist, _ = Playlist.objects.get_or_create(user=user, title=f"{user.username} playlist")
        PlaylistMedia.objects.get_or_create(playlist=playlist, media=media)

    def _login(self, user=None):
        client = Client()
        self.assertTrue(client.login(username=(user or self.target).username, password=self.password))
        return client

    def test_personalized_results_exclude_interacted_and_private_media(self):
        response = self._login().get("/api/v1/media?show=recommended")

        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()["results"]]
        self.assertIn("Media C", titles)
        self.assertNotIn("Media A", titles)
        self.assertNotIn("Media B", titles)
        self.assertNotIn("Private candidate", titles)
        self.assertEqual(len(titles), len(set(titles)))

    def test_anonymous_user_uses_legacy_fallback(self):
        with patch("files.services.recommendations.get_collaborative_recommendations") as collaborative:
            response = Client().get("/api/v1/media?show=recommended")

        self.assertEqual(response.status_code, 200)
        collaborative.assert_not_called()

    def test_new_user_uses_fallback(self):
        newcomer = create_account(username="recommend_new", password=self.password)
        response = self._login(newcomer).get("/api/v1/media?show=recommended")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["results"])

    def test_online_recommendation_avoids_n_plus_one_queries(self):
        request = RequestFactory().get("/api/v1/media?show=recommended")
        request.user = self.target

        with CaptureQueriesContext(connection) as queries:
            results = get_recommended_media(request, limit=1)
            list(results)

        self.assertEqual([item.title for item in results], ["Media C"])
        self.assertLessEqual(len(queries), 7)

    def test_algorithm_exception_uses_legacy_fallback(self):
        with patch(
            "files.services.recommendations.get_collaborative_recommendations",
            side_effect=RuntimeError("expected test failure"),
        ):
            response = self._login().get("/api/v1/media?show=recommended")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["results"])

    @override_settings(ENABLE_COLLABORATIVE_FILTERING=False)
    def test_disabled_switch_completely_uses_legacy_logic(self):
        with patch("files.services.recommendations.get_collaborative_recommendations") as collaborative:
            response = self._login().get("/api/v1/media?show=recommended")

        self.assertEqual(response.status_code, 200)
        collaborative.assert_not_called()
