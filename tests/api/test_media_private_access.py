from django.core.files import File
from django.test import Client, TestCase

from files.models import Media
from files.tests import create_account


class PrivateMediaAccessTest(TestCase):
    fixtures = ["fixtures/categories.json", "fixtures/encoding_profiles.json"]

    def setUp(self):
        self.password = "this_is_a_fake_password"
        self.owner = create_account(username="private_owner", password=self.password)
        self.other = create_account(username="private_other", password=self.password)

        with open("fixtures/test_image.png", "rb") as source:
            self.media = Media.objects.create(
                title="Secret private title",
                user=self.owner,
                media_file=File(source),
            )
        self.media.state = "private"
        self.media.save()

        self.api_url = f"/api/v1/media/{self.media.friendly_token}"
        self.page_url = f"/view?m={self.media.friendly_token}"

    def test_anonymous_private_api_returns_401(self):
        response = Client().get(self.api_url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "media is private"})

    def test_anonymous_private_page_redirects_without_leaking_title(self):
        response = Client().get(self.page_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertNotIn(self.media.title.encode(), response.content)

    def test_other_user_cannot_open_private_page(self):
        client = Client()
        self.assertTrue(
            client.login(username=self.other.username, password=self.password)
        )

        self.assertEqual(client.get(self.page_url).status_code, 403)
        self.assertEqual(client.get(self.api_url).status_code, 401)

    def test_owner_can_open_private_page_and_api(self):
        client = Client()
        self.assertTrue(
            client.login(username=self.owner.username, password=self.password)
        )

        self.assertEqual(client.get(self.page_url).status_code, 200)
        self.assertEqual(client.get(self.api_url).status_code, 200)
