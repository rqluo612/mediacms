"""Run recommendation tests with isolated PostgreSQL, files and cache."""

import os
import sys
import tempfile
import uuid
from pathlib import Path

from django.conf import settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "cms.settings"
os.environ["TESTING"] = "1"
os.environ.pop("USE_SQLITE_TEST_DB", None)


with tempfile.TemporaryDirectory(prefix="recommendation-tests-") as root:
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.MEDIA_ROOT = root
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # Unique disposable test database; never reuse/drop a pre-existing database.
    settings.DATABASES["default"]["TEST"] = {"NAME": "test_recommendations_" + uuid.uuid4().hex[:12]}
    import django

    django.setup()
    from django.test.runner import DiscoverRunner

    labels = sys.argv[1:] or [
        "tests.services.test_content_recommendations",
        "tests.services.test_recommendations",
        "tests.api.test_media_recommendations",
        "actions.tests",
        "tests.uploader.test_metadata",
        "tests.uploader.test_transcoding",
    ]
    failures = DiscoverRunner(verbosity=1, interactive=False).run_tests(labels)
    raise SystemExit(bool(failures))
