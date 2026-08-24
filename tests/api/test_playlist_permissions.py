from django.core.files import File
from django.test import Client, TestCase

from files.models import Media
from files.tests import create_account


class PlaylistPermissionsTest(TestCase):
    fixtures = ["fixtures/categories.json", "fixtures/encoding_profiles.json"]

    def setUp(self):
        self.password = "this_is_a_fake_password"
        self.owner = create_account(username="playlist_owner", password=self.password)
        self.other = create_account(username="playlist_other", password=self.password)

        with open("fixtures/test_image.png", "rb") as source:
            self.media = Media.objects.create(
                title="Playlist public media",
                user=self.owner,
                media_file=File(source),
                state="public",
            )

        owner_client = Client()
        self.assertTrue(owner_client.login(username=self.owner.username, password=self.password))
        response = owner_client.post(
            "/api/v1/playlists",
            data={"title": "Public test playlist", "description": "Visible anonymously"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.playlist_token = response.json()["friendly_token"]
        self.detail_url = f"/api/v1/playlists/{self.playlist_token}"

    def test_anonymous_user_can_view_playlist_list_and_detail(self):
        client = Client()

        listing = client.get(f"/api/v1/playlists?author={self.owner.username}")
        detail = client.get(self.detail_url)

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["title"], "Public test playlist")

    def test_anonymous_user_cannot_create_or_modify_playlist(self):
        client = Client()

        create = client.post(
            "/api/v1/playlists",
            data={"title": "Anonymous playlist"},
            content_type="application/json",
        )
        update = client.put(
            self.detail_url,
            data={"type": "add", "media_friendly_token": self.media.friendly_token},
            content_type="application/json",
        )

        self.assertIn(create.status_code, (401, 403))
        self.assertIn(update.status_code, (401, 403))

    def test_owner_can_add_and_remove_media(self):
        client = Client()
        self.assertTrue(client.login(username=self.owner.username, password=self.password))

        add = client.put(
            self.detail_url,
            data={"type": "add", "media_friendly_token": self.media.friendly_token},
            content_type="application/json",
        )
        after_add = client.get(self.detail_url)
        remove = client.put(
            self.detail_url,
            data={"type": "remove", "media_friendly_token": self.media.friendly_token},
            content_type="application/json",
        )
        after_remove = client.get(self.detail_url)

        self.assertEqual(add.status_code, 201)
        self.assertEqual(len(after_add.json()["playlist_media"]), 1)
        self.assertEqual(remove.status_code, 201)
        self.assertEqual(len(after_remove.json()["playlist_media"]), 0)

    def test_other_user_cannot_modify_playlist(self):
        client = Client()
        self.assertTrue(client.login(username=self.other.username, password=self.password))

        response = client.put(
            self.detail_url,
            data={"type": "add", "media_friendly_token": self.media.friendly_token},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
