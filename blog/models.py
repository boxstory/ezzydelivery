"""
SEO-optimized Blog models for Ezzy Delivery Qatar
Simple Django implementation with full SEO features
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify
from core.validators import image_validators


class BlogCategory(models.Model):
    """Blog categories"""
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="FontAwesome icon class")
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name = "Blog Category"
        verbose_name_plural = "Blog Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('blog:category', kwargs={'slug': self.slug})


class BlogPost(models.Model):
    """Blog post with full SEO optimization"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]

    # Basic fields
    title = models.CharField(max_length=200, help_text="Blog post title (60 chars max for SEO)")
    slug = models.SlugField(unique=True, max_length=200)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='blog_posts')

    # Content
    intro = models.TextField(max_length=500, help_text="Brief introduction (meta description)")
    content = models.TextField(help_text="Main blog content (Markdown supported)")

    # Featured image
    featured_image = models.ImageField(
        upload_to='blog/', null=True, blank=True, validators=image_validators(max_mb=8))
    featured_image_alt = models.CharField(max_length=255, blank=True, help_text="Alt text for SEO")

    # Taxonomy
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")

    # SEO fields
    seo_title = models.CharField(max_length=70, blank=True, help_text="SEO title (50-60 chars)")
    seo_description = models.CharField(max_length=160, blank=True, help_text="Meta description (140-155 chars)")
    seo_keywords = models.CharField(max_length=500, blank=True, help_text="DEPRECATED - Meta keywords no longer used by search engines")
    canonical_url = models.URLField(blank=True)

    # Metadata
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    reading_time = models.IntegerField(default=5, help_text="Minutes")
    views = models.IntegerField(default=0, editable=False)

    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"
        ordering = ['-published_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:post_detail', kwargs={'slug': self.slug})

    @property
    def get_seo_title(self):
        return self.seo_title or f"{self.title} | Ezzy Delivery Qatar Blog"

    @property
    def get_seo_description(self):
        return self.seo_description or self.intro[:160]

    def get_schema_markup(self):
        """Generate JSON-LD schema for blog post"""
        return {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": self.title,
            "description": self.get_seo_description,
            "author": {
                "@type": "Person",
                "name": self.author.get_full_name() if self.author else "Ezzy Delivery Team"
            },
            "datePublished": self.published_at.isoformat() if self.published_at else None,
            "dateModified": self.updated_at.isoformat(),
            "publisher": {
                "@type": "Organization",
                "name": "EzzyDelivery Qatar",
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png"
                }
            }
        }
