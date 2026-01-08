"""
Management command to create blog categories for EzzyDelivery Qatar
Run: python manage.py seed_blog_categories
"""

from django.core.management.base import BaseCommand
from blog.models import BlogCategory


class Command(BaseCommand):
    help = 'Create blog categories for SEO content strategy'

    def handle(self, *args, **options):
        self.stdout.write('Creating blog categories...')

        categories = [
            {
                'slug': 'delivery-services-qatar',
                'name': 'Delivery Services Qatar',
                'description': 'Comprehensive guides on delivery services available in Qatar including same-day, express, and scheduled delivery options.',
                'icon': 'fa-truck-fast',
                'seo_title': 'Delivery Services Qatar | EzzyDelivery Blog',
                'seo_description': 'Expert guides on delivery services in Qatar. Same-day delivery, express courier, and logistics solutions for Doha businesses.'
            },
            {
                'slug': 'restaurant-delivery',
                'name': 'Restaurant Delivery',
                'description': 'Everything restaurant owners need to know about delivery partnerships, food delivery logistics, and growing delivery revenue.',
                'icon': 'fa-utensils',
                'seo_title': 'Restaurant Delivery Partner Qatar | EzzyDelivery',
                'seo_description': 'Restaurant delivery solutions in Qatar. Partner with EzzyDelivery for reliable food delivery services in Doha.'
            },
            {
                'slug': 'ecommerce-logistics',
                'name': 'E-commerce Logistics',
                'description': 'E-commerce fulfillment, warehousing, and last-mile delivery solutions for online businesses in Qatar.',
                'icon': 'fa-cart-shopping',
                'seo_title': 'E-commerce Logistics Qatar | Fulfillment & Delivery',
                'seo_description': 'E-commerce logistics solutions in Qatar. Warehousing, fulfillment, and delivery for online stores in Doha.'
            },
            {
                'slug': 'delivery-pricing',
                'name': 'Delivery Pricing',
                'description': 'Transparent pricing guides, cost comparisons, and money-saving tips for delivery services in Qatar.',
                'icon': 'fa-tag',
                'seo_title': 'Delivery Pricing Qatar | Cost Guide | EzzyDelivery',
                'seo_description': 'Delivery pricing in Qatar explained. Compare costs, understand fees, and find affordable delivery solutions.'
            },
            {
                'slug': 'local-delivery-problems',
                'name': 'Local Delivery Problems',
                'description': 'Common delivery challenges in Qatar and practical solutions for businesses and consumers.',
                'icon': 'fa-triangle-exclamation',
                'seo_title': 'Delivery Problems Qatar | Solutions & Tips',
                'seo_description': 'Solving common delivery problems in Qatar. Tips for failed deliveries, delays, and logistics challenges.'
            },
            {
                'slug': 'delivery-comparisons',
                'name': 'Delivery Comparisons',
                'description': 'Honest comparisons of delivery services, platforms, and logistics providers in Qatar.',
                'icon': 'fa-scale-balanced',
                'seo_title': 'Delivery Service Comparisons Qatar | EzzyDelivery',
                'seo_description': 'Compare delivery services in Qatar. Honest reviews of courier companies, pricing, and service quality.'
            },
            {
                'slug': 'business-use-cases',
                'name': 'Business Use Cases',
                'description': 'Real-world examples of how Qatar businesses use delivery services to grow and succeed.',
                'icon': 'fa-briefcase',
                'seo_title': 'Delivery Use Cases Qatar | Business Success Stories',
                'seo_description': 'How Qatar businesses use delivery services. Success stories from restaurants, e-commerce, and retail.'
            },
            {
                'slug': 'logistics-guides',
                'name': 'Logistics Guides',
                'description': 'In-depth guides on logistics, supply chain management, and 3PL services in Qatar.',
                'icon': 'fa-warehouse',
                'seo_title': 'Logistics Guides Qatar | 3PL & Supply Chain',
                'seo_description': 'Comprehensive logistics guides for Qatar businesses. 3PL, warehousing, and supply chain optimization.'
            },
        ]

        created_count = 0
        for cat_data in categories:
            cat, created = BlogCategory.objects.get_or_create(
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description'],
                    'icon': cat_data['icon'],
                    'seo_title': cat_data['seo_title'],
                    'seo_description': cat_data['seo_description'],
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Created: {cat.name}'))
            else:
                self.stdout.write(f'  Exists: {cat.name}')

        self.stdout.write(self.style.SUCCESS(f'\nDone! Created {created_count} new categories.'))
        self.stdout.write(f'Total categories: {BlogCategory.objects.count()}')
