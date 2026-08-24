from unittest.mock import patch

from django.core.files import File
from django.test import Client, TestCase

from files.models import Media
from files.tests import create_account


class MediaWritePermissionsTest(TestCase):
    fixtures = ["fixtures/categories.json", "fixtures/encoding_profiles.json"]

    def setUp(self):
        self.password = "this_is_a_fake_password"
        self.user = create_account(username="media_writer", password=self.password)

        with open("fixtures/test_image.png", "rb") as source:
            self.media = Media.objects.create(
                title="Public action test",
                user=self.user,
                media_file=File(source),
                state="public",
                enable_comments=True,
            )

        token = self.media.friendly_token
        self.actions_url = f"/api/v1/media/{token}/actions"
        self.comments_url = f"/api/v1/media/{token}/comments"

    def test_anonymous_media_action_requires_authentication(self):
        response = Client().post(
            self.actions_url,
            data={"type": "like"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    @patch("files.views.media.save_user_action.delay")
    def test_authenticated_user_can_like_media(self, save_action):
        client = Client()
        self.assertTrue(client.login(username=self.user.username, password=self.password))

        response = client.post(
            self.actions_url,
            data={"type": "like"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        save_action.assert_called_once()

    def test_anonymous_user_cannot_submit_comment(self):
        response = Client().post(
            self.comments_url,
            data={"text": "Anonymous comment"},
            content_type="application/json",
        )

        self.assertIn(response.status_code, (401, 403))

    def test_authenticated_user_can_submit_comment(self):
        client = Client()
        self.assertTrue(client.login(username=self.user.username, password=self.password))

        response = client.post(
            self.comments_url,
            data={"text": "Authenticated comment"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["text"], "Authenticated comment")

    def test_anonymous_user_cannot_upload(self):
        response = Client().post("/fu/upload/")

        self.assertEqual(response.status_code, 403)

    def test_authenticated_user_reaches_upload_validation(self):
        client = Client()
        self.assertTrue(client.login(username=self.user.username, password=self.password))

        response = client.post("/fu/upload/")

        self.assertEqual(response.status_code, 400)
