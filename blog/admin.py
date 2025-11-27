from django.contrib import admin
from .models import BlogCategory, BlogPost


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'description']


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'status', 'author', 'published_at', 'views']
    list_filter = ['status', 'category', 'created_at', 'published_at']
    search_fields = ['title', 'content', 'seo_keywords']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['views', 'created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'author', 'status', 'category')
        }),
        ('Content', {
            'fields': ('intro', 'content', 'reading_time')
        }),
        ('Featured Image', {
            'fields': ('featured_image', 'featured_image_alt'),
            'classes': ('collapse',)
        }),
        ('SEO Optimization', {
            'fields': ('seo_title', 'seo_description', 'seo_keywords', 'tags', 'canonical_url'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('views', 'created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)
