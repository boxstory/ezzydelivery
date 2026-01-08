"""
Master command to seed all blog content for EzzyDelivery Qatar
Runs all blog seeding commands in sequence

Run: python manage.py seed_all_blog_content

Individual commands can also be run separately:
- python manage.py seed_blog_categories
- python manage.py seed_pillar_pages
- python manage.py seed_seo_articles_batch1
- python manage.py seed_seo_articles_batch2
- python manage.py seed_seo_articles_batch3
- python manage.py seed_seo_articles_batch4
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from blog.models import BlogPost, BlogCategory


class Command(BaseCommand):
    help = 'Seed all blog content (categories + pillar pages + SEO articles)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--categories-only',
            action='store_true',
            help='Only create categories',
        )
        parser.add_argument(
            '--pillar-only',
            action='store_true',
            help='Only create pillar pages',
        )
        parser.add_argument(
            '--articles-only',
            action='store_true',
            help='Only create SEO articles',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(self.style.HTTP_INFO('EZZYDELIVERY BLOG CONTENT SEEDER'))
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write('')

        # Track what to run
        run_categories = True
        run_pillar = True
        run_articles = True

        if options['categories_only']:
            run_pillar = False
            run_articles = False
        elif options['pillar_only']:
            run_categories = False
            run_articles = False
        elif options['articles_only']:
            run_categories = False
            run_pillar = False

        # Run selected commands
        if run_categories:
            self.stdout.write(self.style.MIGRATE_HEADING('\n[1/6] Creating Blog Categories...'))
            call_command('seed_blog_categories')

        if run_pillar:
            self.stdout.write(self.style.MIGRATE_HEADING('\n[2/6] Creating Pillar Pages...'))
            call_command('seed_pillar_pages')

        if run_articles:
            self.stdout.write(self.style.MIGRATE_HEADING('\n[3/6] Creating SEO Articles - Batch 1 (Local Delivery Problems)...'))
            call_command('seed_seo_articles_batch1')

            self.stdout.write(self.style.MIGRATE_HEADING('\n[4/6] Creating SEO Articles - Batch 2 (Pricing Explainers)...'))
            call_command('seed_seo_articles_batch2')

            self.stdout.write(self.style.MIGRATE_HEADING('\n[5/6] Creating SEO Articles - Batch 3 (Comparisons)...'))
            call_command('seed_seo_articles_batch3')

            self.stdout.write(self.style.MIGRATE_HEADING('\n[6/6] Creating SEO Articles - Batch 4 (Use Cases)...'))
            call_command('seed_seo_articles_batch4')

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(self.style.HTTP_INFO('SUMMARY'))
        self.stdout.write(self.style.HTTP_INFO('='*60))

        total_categories = BlogCategory.objects.count()
        total_posts = BlogPost.objects.count()
        published_posts = BlogPost.objects.filter(status='published').count()

        self.stdout.write(f'Total Categories: {total_categories}')
        self.stdout.write(f'Total Blog Posts: {total_posts}')
        self.stdout.write(f'Published Posts: {published_posts}')
        self.stdout.write('')

        # Content breakdown by category
        self.stdout.write(self.style.MIGRATE_LABEL('Posts by Category:'))
        for category in BlogCategory.objects.all():
            count = BlogPost.objects.filter(category=category, status='published').count()
            self.stdout.write(f'  - {category.name}: {count} posts')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Blog content seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('  1. Visit /blog/ to see your content')
        self.stdout.write('  2. Visit /sitemap.xml to verify blog posts are indexed')
        self.stdout.write('  3. Submit sitemap to Google Search Console')
        self.stdout.write('')
