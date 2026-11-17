import math
import uuid
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from actions.models import MediaAction, UserBehaviorLog
from files.models import Media, Playlist, PlaylistMedia, Tag
from files.recommendation_config import content_parameters, resolve_strategy
from files.services.content_recommendations import (
    clean_title_text,
    combined_score,
    profile,
    tag_vector,
    text_document,
    text_vectors,
    tokenize,
    unit,
    user_interactions,
)
from files.services.recommendations import get_recommended_media
from users.models import User


class ContentMathTests(SimpleTestCase):
    def test_chinese_and_english_tokens(self):
        self.assertEqual(tokenize('NATURE'), tokenize('nature'))
        self.assertIn('自然', tokenize('<p>自然 森林</p>'))
        self.assertEqual(tokenize('  !!! <b></b>'), [])

    def test_filename_noise_is_removed_without_dropping_normal_terms(self):
        tokens = tokenize(text_document('17416258_Matthias Groeneveld.mp4', '2024 public private Ada Lovelace'))
        self.assertNotIn('17416258', tokens)
        self.assertNotIn('mp4', tokens)
        for retained in ('matthias', 'groeneveld', '2024', 'public', 'private', 'ada', 'lovelace'):
            self.assertIn(retained, tokens)

    def test_filename_structure_is_cleaned_contextually(self):
        self.assertEqual(tokenize(clean_title_text('17416258_Matthias Groeneveld.mp4')), tokenize('Matthias Groeneveld'))
        self.assertEqual(tokenize(text_document('8114282_https_kaboompics.com_.mp4', '')), [])
        self.assertEqual(tokenize(text_document('video1.mp4', '')), [])
        self.assertEqual(tokenize(text_document('public.mp4', 'Private viewing by Ada Lovelace in 2024')), tokenize('Private viewing by Ada Lovelace in 2024'))
        self.assertEqual(tokenize(clean_title_text('Public transit and private viewing.mp4')), tokenize('Public transit and private viewing'))

    def test_file_extension_stripping_does_not_remove_human_names_or_short_numbers(self):
        self.assertEqual(tokenize('2024 travel with Ada Lovelace.mp4'), tokenize('2024 travel with Ada Lovelace'))
        self.assertIn('12345678', tokenize('A collection contains 12345678 records'))
        self.assertIn('mp4', tokenize('MP4 format is mentioned in prose'))
        self.assertNotIn('mp4', tokenize('Attached sample.mp4.'))
        self.assertIn('year', tokenize('2024 year 1080p'))
        self.assertIn('public', tokenize('Public transport; private collection'))

    def test_tags_binary_cleaned_l2(self):
        self.assertEqual(tag_vector([' Nature ', 'nature', '自然']), {'nature': 1 / math.sqrt(2), '自然': 1 / math.sqrt(2)})
        self.assertEqual(tag_vector(['!!!']), {})

    def test_shared_tfidf_and_empty_vocabulary(self):
        vectors = text_vectors({1: 'cat dog', 2: 'CAT', 3: ''})
        self.assertGreater(vectors[1]['dog'], vectors[1]['cat'])
        self.assertEqual(vectors[2], {'cat': 1})
        self.assertEqual(text_vectors({1: '!!!', 2: ''}), {1: {}, 2: {}})
        self.assertEqual(unit({}), {})

    def test_weighted_profile(self):
        result = profile({1: {'a': 1}, 2: {'b': 1}}, {1: 1, 2: 3})
        self.assertAlmostEqual(result['b'] / result['a'], 3)
        self.assertEqual(profile({1: {}}, {1: 4}), {})

    def test_channels_missing_zero_similarity_and_alpha(self):
        a, b = {'a': 1}, {'b': 1}
        self.assertEqual(combined_score(a, a, a, b, 0.5), 0.5)
        self.assertEqual(combined_score(a, a, a, b, 0), 0)
        self.assertEqual(combined_score(a, a, a, b, 1), 1)
        self.assertEqual(combined_score({}, a, {}, a, 0.5), 1)
        self.assertEqual(combined_score(a, a, a, {}, 0.5), 1)
        self.assertEqual(combined_score(a, a, {}, a, 1), 0)
        self.assertEqual(combined_score({}, {}, {}, {}, 0.5), 0)
        self.assertEqual(combined_score(a, a, b, b, 0.5), 0)

    def test_configuration(self):
        for empty in ('', None):
            self.assertEqual(resolve_strategy(empty, True), 'cf')
            self.assertEqual(resolve_strategy(empty, False), 'legacy')
        for strategy in ('cf', 'content', 'legacy'):
            self.assertEqual(resolve_strategy(strategy, False), strategy)
        for invalid in ('CF', 'other', ' '):
            with self.assertRaises(ImproperlyConfigured):
                resolve_strategy(invalid)
        for alpha in (-0.1, 1.1, 'bad', float('nan')):
            with self.assertRaises(ImproperlyConfigured):
                content_parameters(alpha, {})
        for weight in (-1, 'bad', float('inf')):
            with self.assertRaises(ImproperlyConfigured):
                content_parameters(0.5, {'watch': weight})

    def test_dispatch_compatibility_and_explicit_overrides(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        for strategy, enabled, expected in [('', False, False), ('', True, True), ('cf', False, True), ('legacy', True, False)]:
            with self.settings(RECOMMENDATION_STRATEGY=strategy, ENABLE_COLLABORATIVE_FILTERING=enabled), patch(
                'files.services.recommendations._get_original_recommendations', return_value=[]
            ) as original:
                get_recommended_media(request, 3)
                original.assert_called_once_with(request, 3, enabled=expected)
        with self.settings(RECOMMENDATION_STRATEGY='content'), patch('files.services.content_recommendations.get_content_recommendations', return_value=[]) as content, patch(
            'files.services.recommendations._get_original_recommendations'
        ) as original:
            get_recommended_media(request, 1, current_media_id=4)
            content.assert_called_once_with(request.user, 1, 4)
            original.assert_not_called()
        with self.settings(RECOMMENDATION_STRATEGY='invalid'), self.assertRaises(ImproperlyConfigured):
            get_recommended_media(request)

    def test_actual_environment_loader_and_invalid_value(self):
        import os
        import subprocess
        import sys

        env = dict(os.environ, RECOMMENDATION_STRATEGY='content', CONTENT_RECOMMENDATION_ALPHA='0.25')
        code = 'import cms.settings as s; print(s.RECOMMENDATION_STRATEGY, s.CONTENT_RECOMMENDATION_ALPHA)'
        valid = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertIn('content 0.25', valid.stdout)
        env['RECOMMENDATION_STRATEGY'] = 'invalid'
        invalid = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn('ImproperlyConfigured', invalid.stderr)

    def test_missing_strategy_setting_keeps_old_switch(self):
        from django.conf import settings

        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        for enabled in (True, False):
            with self.settings(ENABLE_COLLABORATIVE_FILTERING=enabled, RECOMMENDATION_STRATEGY=''):
                del settings.RECOMMENDATION_STRATEGY
                with patch('files.services.recommendations._get_original_recommendations', return_value=[]) as original:
                    get_recommended_media(request)
                    original.assert_called_once_with(request, 50, enabled=enabled)


@override_settings(RECOMMENDATION_STRATEGY='content', CONTENT_RECOMMENDATION_ALPHA=0.5, CONTENT_RECOMMENDATION_WEIGHTS={'watch': 1, 'like': 3, 'playlist': 4})
class ContentRecommendationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='content-user', password='test-only-password')
        self.request = RequestFactory().get('/')
        self.request.user = self.user
        self.seed = self.media('自然 forest', description='green landscape', tags=['自然'])
        self.match = self.media('自然 forest', description='green landscape', tags=['自然'])
        self.other = self.media('quantum physics', tags=['科学'], views=999)
        MediaAction.objects.create(user=self.user, media=self.seed, action='watch')

    def media(self, title, tags=(), **kwargs):
        media = Media(
            user=self.user,
            title=title,
            friendly_token=uuid.uuid4().hex,
            media_file='original/content-test.mp4',
            media_type='video',
            state='public',
            encoding_status='success',
            is_reviewed=True,
            listable=True,
        )
        for key, value in kwargs.items():
            setattr(media, key, value)
        Media.objects.bulk_create([media])  # No real files, initialization or Celery tasks.
        media.tags.set([Tag.objects.get_or_create(title=title)[0] for title in tags])
        return media

    def recommendations(self, **kwargs):
        return get_recommended_media(self.request, **kwargs)

    def test_matching_short_list_and_no_cf_cache_access(self):
        with patch('files.services.recommendations.get_collaborative_recommendations') as cf, patch('files.services.recommendations.cache.get', side_effect=AssertionError('CF cache read')), patch(
            'files.services.recommendations.cache.set', side_effect=AssertionError('CF cache write')
        ):
            result = self.recommendations()
        self.assertEqual([m.pk for m in result], [self.match.pk])
        self.assertEqual(result[0].recommendation_algorithm_id, 'CONTENT')
        self.assertEqual(result[0].recommendation_algorithm_version, 'tag_text_content_v2')
        cf.assert_not_called()

    def test_dedup_and_dislike_removes_all_positive_interest(self):
        for action in ['watch', 'like', 'like']:
            MediaAction.objects.create(user=self.user, media=self.seed, action=action)
        for title in ['list-one', 'list-two']:
            playlist = Playlist.objects.create(user=self.user, title=title)
            PlaylistMedia.objects.create(playlist=playlist, media=self.seed)
        scores, excluded = user_interactions(self.user, {'watch': 1, 'like': 3, 'playlist': 4})
        self.assertEqual(scores, {self.seed.pk: 8})
        MediaAction.objects.create(user=self.user, media=self.seed, action='dislike')
        self.assertEqual(user_interactions(self.user, {'watch': 1, 'like': 3, 'playlist': 4}), ({}, {self.seed.pk}))

    def test_filters_even_if_listable_is_inconsistent(self):
        invalid = [
            {'state': 'private'},
            {'state': 'unlisted'},
            {'is_reviewed': False},
            {'encoding_status': 'pending'},
            {'listable': False},
            {'media_type': 'audio'},
            {'media_type': 'image'},
            {'media_type': 'pdf'},
        ]
        for fields in invalid:
            self.media('自然 forest', tags=['自然'], **fields)
        self.assertEqual([m.pk for m in self.recommendations()], [self.match.pk])

    def test_all_behavior_exclusions_apply_before_limit(self):
        for action in ['watch', 'like', 'dislike']:
            item = self.media('自然 forest', tags=['自然'])
            MediaAction.objects.create(user=self.user, media=item, action=action)
        playlist = Playlist.objects.create(user=self.user, title='collected')
        item = self.media('自然 forest', tags=['自然'])
        PlaylistMedia.objects.create(playlist=playlist, media=item)
        current = self.media('自然 forest', tags=['自然'])
        result = self.recommendations(limit=1, current_media_id=current.pk)
        self.assertEqual([m.pk for m in result], [self.match.pk])

    def test_current_top_candidate_excluded_before_slicing(self):
        another = self.media('自然 forest', tags=['自然'])
        self.assertEqual([m.pk for m in self.recommendations(limit=1, current_media_id=self.match.pk)], [another.pk])

    def test_no_history_and_anonymous_use_strict_popularity(self):
        MediaAction.objects.all().delete()  # Isolated test database only.
        result = self.recommendations(limit=1)
        self.assertEqual(result[0].pk, self.other.pk)
        self.assertEqual(result[0].recommendation_algorithm_id, 'LEGACY')
        self.assertEqual(result[0].recommendation_algorithm_version, '')
        self.request.user = AnonymousUser()
        self.assertEqual(self.recommendations(limit=1)[0].pk, self.other.pk)

    def test_no_history_features_or_no_match_fall_back(self):
        self.seed.tags.clear()
        Media.objects.filter(pk=self.seed.pk).update(title='', description='')
        self.assertEqual(self.recommendations(limit=1)[0].recommendation_algorithm_id, 'LEGACY')
        Media.objects.filter(pk=self.seed.pk).update(title='unmatchedword')
        self.assertEqual(self.recommendations(limit=1)[0].recommendation_algorithm_id, 'LEGACY')

    def test_content_edits_are_visible_next_request(self):
        self.assertEqual(self.recommendations()[0].pk, self.match.pk)
        self.match.tags.clear()
        Media.objects.filter(pk=self.match.pk).update(title='unrelatedword', description='')
        result = self.recommendations()
        self.assertTrue(all(m.recommendation_algorithm_id == 'LEGACY' for m in result))
        Media.objects.filter(pk=self.other.pk).update(description='forest green landscape')
        self.assertEqual([m.pk for m in self.recommendations()], [self.other.pk])

    def test_exhaustion_never_reintroduces_seen_or_disliked(self):
        for item in (self.match, self.other):
            MediaAction.objects.create(user=self.user, media=item, action='watch')
        self.assertEqual(self.recommendations(), [])

    def test_query_count_is_bounded(self):
        for _ in range(8):
            self.media('自然 forest', tags=['自然'])
        with CaptureQueriesContext(connection) as queries:
            self.recommendations()
        self.assertLessEqual(len(queries), 4)

    def test_list_autoplay_and_content_signed_attribution(self):
        self.client.force_login(self.user)
        response = self.client.get('/api/v1/media?show=recommended')
        self.assertEqual(response.status_code, 200)
        item = response.json()['results'][0]
        context = item['behavior_context']
        self.assertEqual(context['algorithm_id'], 'CONTENT')
        self.assertEqual(context['algorithm_version'], 'tag_text_content_v2')
        self.assertEqual(context['recommendation_rank'], 1)
        detail = self.client.get('/api/v1/media/' + self.seed.friendly_token)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['autoplay_next']['title'], self.match.title)
        self.assertEqual(detail.json()['autoplay_next']['behavior_context']['algorithm_id'], 'CONTENT')
        session = self.client.post('/api/v1/behavior/sessions', {'client_session_id': str(uuid.uuid4())}, content_type='application/json').json()['session_id']
        response = self.client.post(
            '/api/v1/behavior/interactions',
            {
                'session_id': session,
                'video_id': self.match.friendly_token,
                'recommendation_context': context['attribution_token'],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        log = UserBehaviorLog.objects.get(interaction_id=response.json()['interaction_id'])
        self.assertEqual(log.algorithm_id, 'CONTENT')
        self.assertEqual(log.algorithm_version, 'tag_text_content_v2')
        self.assertEqual(str(log.recommendation_request_id), context['recommendation_request_id'])
        self.assertEqual(log.recommendation_rank, 1)

    def test_fallback_filters_current_and_invalid_candidates(self):
        MediaAction.objects.all().delete()
        self.media('private', state='private', views=9999)
        result = self.recommendations(limit=1, current_media_id=self.other.pk)
        self.assertEqual(len(result), 1)
        self.assertNotEqual(result[0].pk, self.other.pk)
        self.assertEqual(result[0].recommendation_algorithm_id, 'LEGACY')

    def test_zero_weights_have_no_profile_but_still_exclude_seen(self):
        with self.settings(CONTENT_RECOMMENDATION_WEIGHTS={'watch': 0, 'like': 0, 'playlist': 0}):
            result = self.recommendations()
        self.assertNotIn(self.seed.pk, [m.pk for m in result])
        self.assertTrue(all(m.recommendation_algorithm_id == 'LEGACY' for m in result))

    def test_tags_are_not_duplicated_into_text(self):
        with self.settings(CONTENT_RECOMMENDATION_ALPHA=0):
            Media.objects.filter(pk=self.seed.pk).update(title='', description='')
            result = self.recommendations()
        self.assertTrue(all(m.recommendation_algorithm_id == 'LEGACY' for m in result))

    def test_fallback_signed_attribution_keeps_legacy_empty_version(self):
        from files.recommendation_attribution import read_recommendation_attribution

        MediaAction.objects.all().delete()
        self.client.force_login(self.user)
        response = self.client.get('/api/v1/media?show=recommended')
        self.assertEqual(response.status_code, 200)
        item = response.json()['results'][0]
        context = item['behavior_context']
        self.assertEqual(context['algorithm_id'], 'LEGACY')
        self.assertEqual(context['algorithm_version'], '')
        verified = read_recommendation_attribution(context['attribution_token'], self.user, self.other.friendly_token)
        self.assertEqual(verified['algorithm_id'], 'LEGACY')
        self.assertEqual(verified['recommendation_rank'], 1)

    def test_private_history_cannot_add_features_to_public_corpus(self):
        self.media('secrettopic', state='private', tags=['秘密'])
        with patch('files.services.content_recommendations.text_vectors', wraps=text_vectors) as fit:
            self.recommendations()
        self.assertNotIn('secrettopic', str(fit.call_args))

    def test_alpha_endpoints_choose_tag_or_text_matches(self):
        self.match.tags.clear()  # Text-only match; missing tag channel.
        tag_only = self.media('differentword', tags=['自然'])
        with self.settings(CONTENT_RECOMMENDATION_ALPHA=1):
            self.assertEqual([m.pk for m in self.recommendations()], [tag_only.pk])
        with self.settings(CONTENT_RECOMMENDATION_ALPHA=0):
            self.assertEqual([m.pk for m in self.recommendations()], [self.match.pk])
