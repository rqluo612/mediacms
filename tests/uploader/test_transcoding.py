from unittest.mock import patch

from django.test import TestCase


class TranscodeCommitTests(TestCase):
    def test_tasks_wait_for_commit_and_bind_each_encoding(self):
        from files.models import Media, EncodeProfile
        from django.db import transaction
        media = Media(pk=900, friendly_token='commit-test', duration=1, video_height=1080)
        profiles = [EncodeProfile(pk=901, extension='mp4', resolution=360),
                    EncodeProfile(pk=902, extension='mp4', resolution=720)]
        ids = iter([801, 802])
        def save(encoding, *args, **kwargs):
            encoding.pk = next(ids)
        with patch('files.models.media.Encoding.save', save), patch('files.tasks.encode_media.apply_async') as send:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    media.encode(profiles=profiles)
                    send.assert_not_called()
                send.assert_not_called()
            self.assertEqual([call.kwargs['args'] for call in send.call_args_list],
                             [['commit-test', 901, 801], ['commit-test', 902, 802]])

    def test_rollback_does_not_publish(self):
        from files.models import Media, EncodeProfile
        from django.db import transaction
        media = Media(pk=900, friendly_token='rollback-test', duration=1, video_height=1080)
        profile = EncodeProfile(pk=901, extension='gif', resolution=360)
        with patch('files.models.media.Encoding.save'), patch('files.tasks.encode_media.apply_async') as send:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    with transaction.atomic():
                        media.encode(profiles=[profile])
                        raise ValueError('rollback')
                except ValueError:
                    pass
            send.assert_not_called()
