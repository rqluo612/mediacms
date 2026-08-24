from django.test import SimpleTestCase

from files.services.recommendations import calculate_item_similarities, score_candidates


class CollaborativeFilteringMathTest(SimpleTestCase):
    def test_cosine_similarity_uses_sparse_deterministic_matrix(self):
        matrix = {
            1: {10: 1.0, 20: 1.0},
            2: {10: 1.0, 20: 1.0, 30: 1.0},
            3: {20: 1.0, 30: 1.0},
        }

        similarities = calculate_item_similarities(matrix, max_similar_items=10)
        values_10 = dict(similarities[10])
        values_20 = dict(similarities[20])

        self.assertAlmostEqual(values_10[20], 2 / (2 ** 0.5 * 3 ** 0.5))
        self.assertAlmostEqual(values_10[30], 1 / 2)
        self.assertAlmostEqual(values_20[30], 2 / (3 ** 0.5 * 2 ** 0.5))

    def test_candidate_score_is_weighted_sum(self):
        interactions = {10: 1.0, 20: 3.0}
        similarities = {
            10: [(30, 0.5), (40, 0.25)],
            20: [(30, 0.75), (40, 0.5)],
        }

        scores = score_candidates(interactions, similarities)

        self.assertAlmostEqual(scores[30], 2.75)
        self.assertAlmostEqual(scores[40], 1.75)

    def test_similarity_sorting_is_stable_for_equal_scores(self):
        matrix = {
            1: {10: 1.0, 30: 1.0, 20: 1.0},
            2: {10: 1.0, 30: 1.0, 20: 1.0},
        }

        similarities = calculate_item_similarities(matrix, max_similar_items=2)

        self.assertEqual([media_id for media_id, _ in similarities[10]], [20, 30])
