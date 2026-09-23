from django.core.management.base import BaseCommand

from files.services.recommendations import build_and_cache_item_similarities
from files.tasks import get_list_of_popular_media


class Command(BaseCommand):
    help = "Rebuild the popular-media and collaborative-filtering caches."

    def handle(self, *args, **options):
        get_list_of_popular_media()
        similarities = build_and_cache_item_similarities()
        self.stdout.write(
            self.style.SUCCESS(
                "Recommendation caches rebuilt "
                f"({len(similarities)} media with collaborative similarities)."
            )
        )
