from django.core.management.base import BaseCommand

from apps.admissions.catalog_v1 import CATALOG, VERIFIED_AT
from apps.admissions.models import University, UniversityProgram


class Command(BaseCommand):
    help = 'Load the source-backed Naseeb Edu US and Canada university catalog.'

    def handle(self, *args, **options):
        university_count = 0
        program_count = 0

        for name, country, city, institution_type, programs in CATALOG:
            canonical_majors = sorted({canonical_major for _, canonical_major, _ in programs})
            university, _ = University.objects.update_or_create(
                name=name,
                country=country,
                defaults={
                    'city': city,
                    'institution_type': institution_type,
                    'popular_majors': ','.join(canonical_majors),
                    'catalog_source_url': programs[0][2],
                    'catalog_verified_at': VERIFIED_AT,
                    'notes': 'Curated for the Naseeb Edu first-release recommendation catalog.',
                },
            )
            university_count += 1

            for program_name, canonical_major, source_url in programs:
                UniversityProgram.objects.update_or_create(
                    university=university,
                    name=program_name,
                    defaults={
                        'canonical_major': canonical_major,
                        'degree_level': UniversityProgram.DegreeLevel.BACHELOR,
                        'teaching_language': 'English',
                        'source_url': source_url,
                        'verified_at': VERIFIED_AT,
                        'international_students_eligible': True,
                        'is_active': True,
                    },
                )
                program_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Loaded {university_count} universities and {program_count} programs.'
        ))
