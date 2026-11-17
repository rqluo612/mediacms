import json
import uuid
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, RequestFactory
from django.contrib.auth import get_user_model

from uploader.forms import FineUploaderUploadForm, FineUploaderUploadSuccessForm
from uploader.metadata import normalize_tags, validate_metadata, upload_token, resolve_tags
from uploader.views import FineUploaderView


class MetadataTests(SimpleTestCase):
    def test_defaults_and_normalization(self):
        self.assertEqual(validate_metadata({'tags': '[" 科学  实验 ", "Science", "science"]'}, 'lesson.mp4'),
                         {'title': 'lesson', 'description': '', 'tags': ['科学 实验', 'science']})

    def test_limits(self):
        for data in [dict(title=' '), dict(title='字' * 101), dict(description='字' * 301),
                     dict(tags=[]), dict(tags=['x' * 21, 'y']),
                     dict(tags=['a', 'b', 'c', 'd', 'e', 'f']), dict(tags='invalid'), dict(tags=[1, 'a'])]:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                validate_metadata({'tags': ['a', 'b'], **data}, 'test.mp4')
        self.assertEqual(len(validate_metadata({'title': '字' * 100, 'description': '字' * 300,
                                               'tags': ['a', 'b', 'c', 'd', '字' * 20]}, 'x.mp4')['tags']), 5)

    def test_forms_validate_chunks_and_completion(self):
        data = {'qquuid': str(uuid.uuid4()), 'qqfilename': 'video.mp4', 'qqtotalparts': 2,
                'title': 'Video', 'tags': json.dumps(['science', 'nature'])}
        chunk = FineUploaderUploadForm(data, {'qqfile': SimpleUploadedFile('video.mp4', b'chunk')})
        done = FineUploaderUploadSuccessForm(data)
        self.assertTrue(chunk.is_valid(), chunk.errors)
        self.assertTrue(done.is_valid(), done.errors)
        data['tags'] = '[]'
        self.assertFalse(FineUploaderUploadSuccessForm(data).is_valid())
        data['qquuid'] = '../invalid'
        self.assertFalse(FineUploaderUploadSuccessForm(data).is_valid())

    def test_token_scoped_to_user_and_file(self):
        self.assertEqual(upload_token(1, 'file-a'), upload_token(1, 'file-a'))
        self.assertNotEqual(upload_token(1, 'file-a'), upload_token(2, 'file-a'))
        self.assertNotEqual(upload_token(1, 'file-a'), upload_token(1, 'file-b'))


class UploadPersistenceTests(TestCase):
    def test_reuse_legacy_tag(self):
        from files.models import Tag
        tag = Tag.objects.create(title='Science')
        self.assertEqual(resolve_tags(['science', 'nature'])[0], tag)
        self.assertEqual(Tag.objects.filter(title__iexact='science').count(), 1)

    def test_duplicate_request_returns_existing_without_touching_chunks(self):
        from files.models import Media
        user = get_user_model().objects.create_user(username='upload-test')
        upload_id = str(uuid.uuid4())
        # Bulk insert avoids transcoding side effects; this test only exercises deduplication.
        Media.objects.bulk_create([Media(user=user, title='Existing', friendly_token=upload_token(user.pk, upload_id))])
        request = RequestFactory().post('/uploader/upload/?done')
        request.user = user
        view = FineUploaderView()
        view.setup(request)
        form = FineUploaderUploadSuccessForm({'qquuid': upload_id, 'qqfilename': 'x.mp4',
                                             'qqtotalparts': 2, 'tags': '["a", "b"]'})
        self.assertTrue(form.is_valid(), form.errors)
        with patch('uploader.views.ChunkedFineUploader') as uploader:
            self.assertEqual(view.form_valid(form).status_code, 200)
            uploader.assert_not_called()
        self.assertEqual(Media.objects.filter(user=user).count(), 1)


class ChunkRetryTests(SimpleTestCase):
    def test_repeated_chunk_replaces_original_and_combines_in_order(self):
        import tempfile
        from django.test import override_settings
        from uploader.fineuploader import ChunkedFineUploader
        with tempfile.TemporaryDirectory() as root, override_settings(
            MEDIA_ROOT=root, UPLOAD_DIR='uploads', CHUNKS_DIR='chunks',
            FILE_STORAGE='django.core.files.storage.FileSystemStorage'
        ):
            data = {'qquuid': str(uuid.uuid4()), 'qqfilename': 'video.mp4', 'qqtotalparts': 2}
            for index, content in [(1, b'old'), (0, b'first'), (1, b'second')]:
                part = ChunkedFineUploader({**data, 'qqpartindex': index,
                                           'qqfile': SimpleUploadedFile('video.mp4', content)})
                part.save()
            complete = ChunkedFineUploader(data)
            complete.combine_chunks()
            with complete.storage.open(complete.real_path, 'rb') as result:
                self.assertEqual(result.read(), b'firstsecond')
            # Chunks remain available until the media transaction commits.
            self.assertTrue(complete.storage.exists(complete.chunk_file))


class CompatibilityTests(SimpleTestCase):
    def test_non_video_without_metadata(self):
        for name in ['image.jpg', 'sound.mp3', 'document.pdf']:
            self.assertEqual(validate_metadata({}, name), {'title': name, 'description': '', 'tags': []})

    def test_one_normalized_tag(self):
        self.assertEqual(validate_metadata({'tags': [' A ', 'a', ' ']}, 'x.mp4')['tags'], ['a'])


class UploadScriptVersionTests(SimpleTestCase):
    def test_content_change_invalidates_url(self):
        import tempfile
        from pathlib import Path
        from files.templatetags.custom_filters import upload_metadata_version
        with tempfile.TemporaryDirectory() as root, self.settings(STATIC_ROOT=root):
            script = Path(root) / 'js/upload-metadata.js'
            script.parent.mkdir()
            script.write_text('old')
            old = upload_metadata_version()
            script.write_text('new')
            self.assertNotEqual(old, upload_metadata_version())
            self.assertEqual(upload_metadata_version(), upload_metadata_version())
