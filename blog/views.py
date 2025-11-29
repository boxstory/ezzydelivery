from django.shortcuts import render, get_object_or_404
from django.db.models import Count
from .models import BlogPost, BlogCategory
from core.seo import SEOMetadata

def blog_category(request, slug=None):
    """
    Blog category view - displays posts by category or all posts
    """
    # Get all published posts
    posts = BlogPost.objects.filter(status='published').select_related('author', 'category')

    # Filter by category if slug is provided
    category = None
    if slug:
        category = get_object_or_404(BlogCategory, slug=slug)
        posts = posts.filter(category=category)

    # Get trending posts (most viewed)
    trending_posts = BlogPost.objects.filter(status='published').order_by('-views')[:5]

    # Get all categories with post counts
    categories = BlogCategory.objects.annotate(post_count=Count('posts'))

    # SEO metadata
    if category:
        meta = SEOMetadata.get_default_meta(
            title=category.seo_title or f"{category.name} - Ezzy Delivery Blog",
            description=category.seo_description or category.description,
            keywords=f"{category.name}, delivery blog Qatar, logistics insights"
        )
    else:
        meta = SEOMetadata.get_default_meta(
            title="Blog - Ezzy Delivery Qatar",
            description="Latest insights, tips and news about delivery services, logistics and e-commerce in Qatar",
            keywords="delivery blog Qatar, logistics news, ecommerce tips"
        )

    data = {
        'seo': meta,
        'posts': posts,
        'category': category,
        'trending_posts': trending_posts,
        'categories': categories,
    }
    return render(request, 'blog/category.html', data)


def blog_post_detail(request, slug):
    """
    Blog post detail view
    """
    post = get_object_or_404(BlogPost, slug=slug, status='published')

    # Increment view count
    post.views += 1
    post.save(update_fields=['views'])

    # Get related posts from same category
    related_posts = BlogPost.objects.filter(
        category=post.category,
        status='published'
    ).exclude(id=post.id)[:3]

    # Get trending posts
    trending_posts = BlogPost.objects.filter(status='published').order_by('-views')[:5]

    # SEO metadata
    meta = SEOMetadata.get_default_meta(
        title=post.get_seo_title,
        description=post.get_seo_description,
        keywords=post.seo_keywords or post.tags
    )

    data = {
        'seo': meta,
        'post': post,
        'related_posts': related_posts,
        'trending_posts': trending_posts,
        'schema_markup': post.get_schema_markup(),
    }
    return render(request, 'blog/post_detail.html', data)


def blog_index(request):
    """
    Blog home page - redirect to category view
    """
    return blog_category(request, slug=None)
