# SEO Expert Skill - EzzyDelivery Qatar

Use this skill when working on SEO tasks: meta tags, structured data, sitemaps, content optimization, image alt tags, AI search optimization, and search engine visibility.

## AI Search Optimization (GEO)

### LLMs.txt
The site provides `/llms.txt` for AI language models following llmstxt.org specification.

```python
# core/views_seo.py
@require_GET
def llms_txt(request):
    """AI-friendly content for language models."""
    # Returns company info, services, coverage, links
```

### Schema.org JSON-LD
All pages include structured data in `templates/includes/head.html`:
- `LocalBusiness` schema with ratings, services, areas
- `WebSite` schema with search action

### robots.txt AI Crawlers
```txt
User-agent: GPTBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: PerplexityBot
Allow: /
```

## Image Alt Tag Rules

**IMPORTANT: Every image MUST have a descriptive alt attribute.**

### Alt Tag Best Practices
```html
<!-- GOOD: Descriptive, keyword-rich alt text -->
<img src="delivery-truck.jpg" alt="EzzyDelivery truck making same-day delivery in Doha Qatar">
<img src="driver-app.png" alt="Driver mobile app showing real-time delivery tracking map">
<img src="warehouse.jpg" alt="EzzyDelivery warehouse with organized inventory shelves in Qatar">

<!-- BAD: Empty, generic, or keyword-stuffed alt text -->
<img src="truck.jpg" alt="">  <!-- Empty - never do this -->
<img src="truck.jpg" alt="image">  <!-- Too generic -->
<img src="truck.jpg" alt="truck truck delivery delivery fast">  <!-- Keyword stuffing -->
```

### Alt Tag Guidelines
1. **Be descriptive**: Describe what's in the image as if explaining to someone who can't see it
2. **Include keywords naturally**: Add relevant keywords without stuffing
3. **Keep it concise**: 125 characters or less is ideal
4. **Context matters**: Relate the alt text to the page content
5. **Decorative images**: Use `alt=""` ONLY for purely decorative images (borders, spacers)
6. **Brand images**: Include brand name when relevant (e.g., "EzzyDelivery logo")

### Django Template Pattern
```html
<!-- For dynamic images -->
<img src="{{ product.image.url }}"
     alt="{{ product.name }} - {{ product.category.name }}"
     loading="lazy">

<!-- For blog post featured images -->
<img src="{{ post.featured_image.url }}"
     alt="{{ post.image_alt|default:post.title }}"
     loading="lazy">

<!-- With fallback -->
<img src="{{ item.image.url }}"
     alt="{% if item.image_alt %}{{ item.image_alt }}{% else %}{{ item.name }} product image{% endif %}"
     loading="lazy">
```

### Model Field for Alt Text
```python
# Add to models that have images
class Product(models.Model):
    image = models.ImageField(upload_to='products/')
    image_alt = models.CharField(
        max_length=125,
        blank=True,
        help_text="Descriptive alt text for SEO (max 125 chars)"
    )
```

## SEO Stack

| Component | Implementation | Location |
|-----------|----------------|----------|
| Meta Tags | Django templates | `templates/base.html` |
| Structured Data | JSON-LD | Template blocks |
| Sitemap | Django Sitemap Framework | `webpages/sitemaps.py` |
| Robots.txt | Static file | `static/robots.txt` |
| Canonical URLs | Template tags | `<link rel="canonical">` |
| Blog/Content | Django Blog App | `blog/` |

## Meta Tag Implementation

### Base Template Pattern
```html
<!-- templates/base.html -->
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <!-- Primary Meta Tags -->
    <title>{% block title %}EzzyDelivery - Fast Local Delivery{% endblock %}</title>
    <meta name="title" content="{% block meta_title %}EzzyDelivery - Fast Local Delivery{% endblock %}">
    <meta name="description" content="{% block meta_description %}EzzyDelivery provides fast, reliable local delivery services for businesses. Same-day delivery, real-time tracking, and professional drivers.{% endblock %}">
    <meta name="keywords" content="{% block meta_keywords %}delivery service, local delivery, same-day delivery, courier service, business delivery{% endblock %}">
    <meta name="author" content="EzzyDelivery">

    <!-- Canonical URL -->
    <link rel="canonical" href="{% block canonical_url %}{{ request.build_absolute_uri }}{% endblock %}">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="{% block og_type %}website{% endblock %}">
    <meta property="og:url" content="{% block og_url %}{{ request.build_absolute_uri }}{% endblock %}">
    <meta property="og:title" content="{% block og_title %}{{ block.super }}{% endblock %}">
    <meta property="og:description" content="{% block og_description %}{% endblock %}">
    <meta property="og:image" content="{% block og_image %}{{ request.scheme }}://{{ request.get_host }}{% static 'webpages/images/og-default.jpg' %}{% endblock %}">
    <meta property="og:site_name" content="EzzyDelivery">
    <meta property="og:locale" content="en_US">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{{ request.build_absolute_uri }}">
    <meta name="twitter:title" content="{% block twitter_title %}{{ block.super }}{% endblock %}">
    <meta name="twitter:description" content="{% block twitter_description %}{% endblock %}">
    <meta name="twitter:image" content="{% block twitter_image %}{% endblock %}">

    <!-- Robots -->
    <meta name="robots" content="{% block robots %}index, follow{% endblock %}">

    <!-- Structured Data -->
    {% block structured_data %}{% endblock %}
</head>
```

### Page-Specific Meta Tags
```html
<!-- webpages/templates/webpages/service_detail.html -->
{% extends 'base.html' %}

{% block title %}{{ service.name }} - EzzyDelivery{% endblock %}
{% block meta_title %}{{ service.name }} | Professional Delivery Service{% endblock %}
{% block meta_description %}{{ service.meta_description|default:service.description|truncatewords:25 }}{% endblock %}
{% block meta_keywords %}{{ service.keywords }}, delivery service, EzzyDelivery{% endblock %}

{% block og_title %}{{ service.name }} - EzzyDelivery{% endblock %}
{% block og_description %}{{ service.meta_description }}{% endblock %}
{% block og_image %}{{ service.image.url }}{% endblock %}
```

## Structured Data (JSON-LD)

### Organization Schema
```html
{% block structured_data %}
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "EzzyDelivery",
    "url": "https://ezzydelivery.com",
    "logo": "https://ezzydelivery.com{% static 'webpages/images/logo.png' %}",
    "description": "Fast, reliable local delivery services for businesses",
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "123 Delivery Street",
        "addressLocality": "City",
        "addressRegion": "State",
        "postalCode": "12345",
        "addressCountry": "US"
    },
    "contactPoint": {
        "@type": "ContactPoint",
        "telephone": "+1-234-567-8900",
        "contactType": "customer service",
        "availableLanguage": "English"
    },
    "sameAs": [
        "https://facebook.com/ezzydelivery",
        "https://twitter.com/ezzydelivery",
        "https://linkedin.com/company/ezzydelivery"
    ]
}
</script>
{% endblock %}
```

### Local Business Schema
```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    "name": "EzzyDelivery",
    "@id": "https://ezzydelivery.com",
    "url": "https://ezzydelivery.com",
    "image": "https://ezzydelivery.com/static/images/storefront.jpg",
    "priceRange": "$$",
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "123 Delivery Street",
        "addressLocality": "City",
        "addressRegion": "State",
        "postalCode": "12345",
        "addressCountry": "US"
    },
    "geo": {
        "@type": "GeoCoordinates",
        "latitude": 40.7128,
        "longitude": -74.0060
    },
    "openingHoursSpecification": [
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "opens": "08:00",
            "closes": "20:00"
        },
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Saturday", "Sunday"],
            "opens": "09:00",
            "closes": "18:00"
        }
    ]
}
</script>
```

### Service Schema
```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "Service",
    "serviceType": "{{ service.name }}",
    "provider": {
        "@type": "Organization",
        "name": "EzzyDelivery"
    },
    "description": "{{ service.description }}",
    "areaServed": {
        "@type": "City",
        "name": "{{ service.city }}"
    },
    "hasOfferCatalog": {
        "@type": "OfferCatalog",
        "name": "Delivery Services",
        "itemListElement": [
            {
                "@type": "Offer",
                "itemOffered": {
                    "@type": "Service",
                    "name": "Same-Day Delivery"
                }
            }
        ]
    }
}
</script>
```

### Blog Post / Article Schema
```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": "{{ post.title }}",
    "description": "{{ post.meta_description }}",
    "image": "{{ post.featured_image.url }}",
    "datePublished": "{{ post.published_at|date:'c' }}",
    "dateModified": "{{ post.updated_at|date:'c' }}",
    "author": {
        "@type": "Person",
        "name": "{{ post.author.get_full_name }}"
    },
    "publisher": {
        "@type": "Organization",
        "name": "EzzyDelivery",
        "logo": {
            "@type": "ImageObject",
            "url": "https://ezzydelivery.com{% static 'webpages/images/logo.png' %}"
        }
    },
    "mainEntityOfPage": {
        "@type": "WebPage",
        "@id": "{{ request.build_absolute_uri }}"
    }
}
</script>
```

### FAQ Schema
```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {% for faq in faqs %}
        {
            "@type": "Question",
            "name": "{{ faq.question }}",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "{{ faq.answer }}"
            }
        }{% if not forloop.last %},{% endif %}
        {% endfor %}
    ]
}
</script>
```

### Breadcrumb Schema
```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": "https://ezzydelivery.com"
        },
        {
            "@type": "ListItem",
            "position": 2,
            "name": "Services",
            "item": "https://ezzydelivery.com/services/"
        },
        {
            "@type": "ListItem",
            "position": 3,
            "name": "{{ service.name }}",
            "item": "{{ request.build_absolute_uri }}"
        }
    ]
}
</script>
```

## Django Sitemap Configuration

### sitemap.py
```python
# webpages/sitemaps.py
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from blog.models import BlogPost
from webpages.models import Service, City

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return ['home', 'about', 'contact', 'services', 'pricing']

    def location(self, item):
        return reverse(item)

class ServiceSitemap(Sitemap):
    priority = 0.9
    changefreq = 'weekly'

    def items(self):
        return Service.objects.filter(is_active=True)

    def lastmod(self, obj):
        return obj.updated_at

class CitySitemap(Sitemap):
    priority = 0.7
    changefreq = 'monthly'

    def items(self):
        return City.objects.filter(is_active=True)

    def location(self, obj):
        return reverse('city_detail', kwargs={'slug': obj.slug})

class BlogSitemap(Sitemap):
    priority = 0.6
    changefreq = 'weekly'

    def items(self):
        return BlogPost.objects.filter(status='published')

    def lastmod(self, obj):
        return obj.updated_at

# Combine all sitemaps
sitemaps = {
    'static': StaticViewSitemap,
    'services': ServiceSitemap,
    'cities': CitySitemap,
    'blog': BlogSitemap,
}
```

### URL Configuration
```python
# ezzydelivery/urls.py
from django.contrib.sitemaps.views import sitemap
from webpages.sitemaps import sitemaps

urlpatterns = [
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
]
```

## Robots.txt

```txt
# static/robots.txt or served via view
User-agent: *
Allow: /

# Block admin and private areas
Disallow: /admin/
Disallow: /dashboard/
Disallow: /api/
Disallow: /accounts/

# Block search and filter pages (duplicate content)
Disallow: /*?page=
Disallow: /*?search=
Disallow: /*?filter=

# Sitemap
Sitemap: https://ezzydelivery.com/sitemap.xml
```

## SEO Models

```python
# webpages/models.py
from django.db import models

class SEOModel(models.Model):
    """Abstract model for SEO fields"""
    meta_title = models.CharField(max_length=70, blank=True,
        help_text="SEO title (max 70 chars)")
    meta_description = models.CharField(max_length=160, blank=True,
        help_text="SEO description (max 160 chars)")
    meta_keywords = models.CharField(max_length=255, blank=True,
        help_text="Comma-separated keywords")
    canonical_url = models.URLField(blank=True,
        help_text="Canonical URL if different from page URL")
    no_index = models.BooleanField(default=False,
        help_text="Prevent search engines from indexing")

    class Meta:
        abstract = True

class Service(SEOModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    # ... other fields

    def get_absolute_url(self):
        return reverse('service_detail', kwargs={'slug': self.slug})

class BlogPost(SEOModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    content = models.TextField()
    featured_image = models.ImageField(upload_to='blog/')
    published_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('published', 'Published')
    ])

    def get_absolute_url(self):
        return reverse('blog_post', kwargs={'slug': self.slug})
```

## URL Best Practices

```python
# Good URL patterns
urlpatterns = [
    # Descriptive, keyword-rich URLs
    path('delivery-services/', views.services, name='services'),
    path('delivery-services/<slug:slug>/', views.service_detail, name='service_detail'),
    path('same-day-delivery/<slug:city>/', views.city_service, name='city_service'),
    path('blog/<slug:slug>/', views.blog_post, name='blog_post'),

    # Avoid
    # path('s/<int:id>/', ...)  # Bad: not descriptive
    # path('service_detail/', ...)  # Bad: underscores
]
```

## Content Optimization Checklist

### Page Content
- [ ] H1 tag with primary keyword (one per page)
- [ ] H2-H6 hierarchy for content structure
- [ ] Primary keyword in first 100 words
- [ ] Internal links to related content
- [ ] External links to authoritative sources
- [ ] **Alt text for ALL images** (descriptive, keyword-rich, max 125 chars)
- [ ] No empty or generic alt attributes (alt="image", alt="photo")
- [ ] Minimum 300 words for main pages

### Technical SEO
- [ ] Meta title under 60 characters
- [ ] Meta description under 160 characters
- [ ] Canonical URLs set correctly
- [ ] Structured data validated (Google Rich Results Test)
- [ ] Mobile-friendly (responsive design)
- [ ] Page load speed optimized
- [ ] HTTPS enabled
- [ ] XML sitemap submitted to Search Console

### Image Optimization
```html
<!-- Use descriptive alt text -->
<img src="delivery-truck.jpg"
     alt="EzzyDelivery truck making same-day delivery in downtown"
     loading="lazy"
     width="800"
     height="600">

<!-- Use WebP with fallback -->
<picture>
    <source srcset="image.webp" type="image/webp">
    <img src="image.jpg" alt="Descriptive alt text">
</picture>
```

## AI Search SEO Checklist (GEO - Generative Engine Optimization)

Optimize content for AI-powered search engines: Google AI Overviews, Bing Copilot, Perplexity, ChatGPT Search, and Claude.

### Content Structure for AI
- [ ] **Clear, direct answers** in the first paragraph (AI extracts these)
- [ ] **Question-based headings** (H2/H3) that match user queries
- [ ] **Bulleted/numbered lists** for easy AI parsing
- [ ] **Concise paragraphs** (2-3 sentences max)
- [ ] **Definition statements** ("X is...", "X refers to...")
- [ ] **Comparison tables** for features, pricing, options

### E-E-A-T Signals (Experience, Expertise, Authoritativeness, Trust)
- [ ] Author bylines with credentials
- [ ] "About Us" page with company history
- [ ] Customer testimonials and reviews
- [ ] Case studies with real data
- [ ] Industry certifications displayed
- [ ] Contact information easily accessible
- [ ] Privacy policy and terms of service

### Structured Data for AI
- [ ] **FAQ Schema** - AI loves extracting Q&A pairs
- [ ] **HowTo Schema** - Step-by-step processes
- [ ] **Organization Schema** - Brand identity
- [ ] **LocalBusiness Schema** - Location-based queries
- [ ] **Review/Rating Schema** - Social proof

### Content Patterns AI Prefers
```html
<!-- Direct answer pattern -->
<h2>What is same-day delivery?</h2>
<p><strong>Same-day delivery</strong> is a shipping service where orders
placed before a cutoff time are delivered within the same business day,
typically within 4-8 hours of order placement.</p>

<!-- List pattern for features -->
<h2>EzzyDelivery Features</h2>
<ul>
    <li><strong>Real-time tracking</strong> - Monitor deliveries live on map</li>
    <li><strong>SMS notifications</strong> - Automatic customer updates</li>
    <li><strong>Proof of delivery</strong> - Photo confirmation</li>
</ul>

<!-- Comparison table pattern -->
<h2>Delivery Speed Comparison</h2>
<table>
    <tr><th>Service</th><th>Delivery Time</th><th>Best For</th></tr>
    <tr><td>Express</td><td>2-4 hours</td><td>Urgent documents</td></tr>
    <tr><td>Same-day</td><td>4-8 hours</td><td>E-commerce orders</td></tr>
    <tr><td>Next-day</td><td>24 hours</td><td>Standard packages</td></tr>
</table>
```

### AI Citation Optimization
- [ ] **Cite sources** when making claims (builds trust)
- [ ] **Include statistics** with dates (e.g., "As of 2024...")
- [ ] **Use quotable sentences** that AI can extract
- [ ] **Provide unique data/insights** not found elsewhere
- [ ] **Update content regularly** (AI prefers fresh content)

### Technical AI SEO
- [ ] Fast page load (AI crawlers have timeouts)
- [ ] Clean HTML structure (proper semantic tags)
- [ ] No content behind JavaScript-only rendering
- [ ] Allow AI crawlers in robots.txt:
```txt
# Allow AI crawlers
User-agent: GPTBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: CCBot
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /
```

### AI-Friendly FAQ Template
```html
<div itemscope itemtype="https://schema.org/FAQPage">
    <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
        <h3 itemprop="name">How fast is EzzyDelivery?</h3>
        <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
            <p itemprop="text">EzzyDelivery offers same-day delivery within
            4-8 hours for orders placed before 2 PM. Express delivery is
            available within 2-4 hours for urgent shipments.</p>
        </div>
    </div>
</div>
```

## SEO Django Template Tags

```python
# webpages/templatetags/seo_tags.py
from django import template
from django.utils.html import strip_tags
from django.utils.text import Truncator

register = template.Library()

@register.simple_tag
def meta_description(text, length=160):
    """Generate meta description from text"""
    clean_text = strip_tags(text)
    return Truncator(clean_text).chars(length, truncate='...')

@register.simple_tag
def meta_title(title, suffix="EzzyDelivery"):
    """Generate SEO-friendly title"""
    if len(title) + len(suffix) + 3 > 60:
        return title[:57] + "..."
    return f"{title} | {suffix}"

@register.inclusion_tag('includes/breadcrumbs.html')
def breadcrumbs(items):
    """Render breadcrumbs with structured data"""
    return {'items': items}
```

## Performance for SEO

```python
# Cache frequently accessed SEO content
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # 15 minutes
def service_list(request):
    services = Service.objects.filter(is_active=True)
    return render(request, 'services.html', {'services': services})

# Use database-level caching for sitemaps
class CachedServiceSitemap(Sitemap):
    def items(self):
        from django.core.cache import cache
        services = cache.get('sitemap_services')
        if not services:
            services = list(Service.objects.filter(is_active=True))
            cache.set('sitemap_services', services, 3600)
        return services
```

## Best Practices Summary

### Traditional SEO
1. **Unique titles/descriptions**: Every page needs unique meta tags
2. **Keyword research**: Target relevant, achievable keywords
3. **Quality content**: Write for users first, search engines second
4. **Mobile-first**: Ensure responsive, fast-loading pages
5. **Internal linking**: Connect related content naturally
6. **Schema markup**: Use structured data for rich snippets
7. **Update regularly**: Keep content fresh and relevant
8. **Monitor performance**: Use Search Console and Analytics
9. **Fix broken links**: Regular audits for 404s
10. **Secure site**: HTTPS is a ranking factor

### Image SEO
11. **Alt text on ALL images**: Descriptive, keyword-rich, max 125 characters
12. **No empty alt attributes**: Never use `alt=""` except for decorative images
13. **Lazy loading**: Use `loading="lazy"` for below-fold images
14. **WebP format**: Use modern formats with fallbacks
15. **Descriptive filenames**: Use `delivery-truck-lagos.jpg` not `IMG_1234.jpg`

### AI Search (GEO)
16. **Direct answers first**: Put the answer in the first paragraph
17. **Question-based headings**: Use H2/H3 that match user queries
18. **Structured content**: Lists, tables, and clear formatting
19. **E-E-A-T signals**: Author credentials, testimonials, certifications
20. **Allow AI crawlers**: Configure robots.txt for GPTBot, Perplexity, etc.
