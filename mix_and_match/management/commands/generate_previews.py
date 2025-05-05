# mix_and_match/management/commands/generate_previews.py

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from mix_and_match.models import UserOutfit
from mix_and_match.utils import update_outfit_preview_image
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generates missing 2D preview images for UserOutfits.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate previews even for outfits that already have one.',
        )
        parser.add_argument(
            '--outfit_ids',
            nargs='+',
            type=int,
            help='Specific outfit IDs to process.',
        )

    def handle(self, *args, **options):
        force_regeneration = options['force']
        specific_ids = options['outfit_ids']

        outfits_to_process = UserOutfit.objects.all()

        if specific_ids:
            self.stdout.write(f"Processing specific outfit IDs: {specific_ids}")
            outfits_to_process = outfits_to_process.filter(id__in=specific_ids)
        elif not force_regeneration:
             # Process only those missing a preview image
             # Check for null=True OR blank=True ('')
             outfits_to_process = outfits_to_process.filter(
                 Q(preview_image__isnull=True) | Q(preview_image='')
             )
             self.stdout.write("Processing outfits missing preview images...")
        else:
             self.stdout.write(self.style.WARNING("Processing ALL outfits (including existing previews) due to --force flag."))

        total_outfits = outfits_to_process.count()
        if total_outfits == 0:
            self.stdout.write(self.style.SUCCESS("No outfits needed processing."))
            return

        self.stdout.write(f"Found {total_outfits} outfit(s) to process.")

        processed_count = 0
        success_count = 0
        failure_count = 0

        for outfit in outfits_to_process.iterator(): # Use iterator for memory efficiency
            processed_count += 1
            self.stdout.write(f"[{processed_count}/{total_outfits}] Processing Outfit ID: {outfit.id}...", ending='')
            try:
                # Ensure items are loaded if needed by generator
                # (generate_outfit_image already selects related items)
                success = update_outfit_preview_image(outfit)
                if success:
                    self.stdout.write(self.style.SUCCESS(" OK"))
                    success_count += 1
                else:
                    self.stdout.write(self.style.WARNING(" FAILED (Generation/Save Error)"))
                    failure_count += 1
            except Exception as e:
                 self.stdout.write(self.style.ERROR(f" ERROR ({e})"))
                 failure_count += 1
                 logger.error(f"Management command error processing Outfit {outfit.id}", exc_info=True)


        self.stdout.write("-" * 30)
        self.stdout.write(self.style.SUCCESS(f"Successfully generated/updated: {success_count}"))
        if failure_count > 0:
             self.stdout.write(self.style.ERROR(f"Failed: {failure_count}"))
        self.stdout.write("Processing complete.")