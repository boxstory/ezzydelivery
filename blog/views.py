from django.shortcuts import render, get_object_or_404
from django.db.models import Count
from .models import BlogPost, BlogCategory
from core.seo import SEOMetadata
from core.json_utils import safe_json

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

    # SEO metadata - unique for each category/blog index
    if category:
        meta = SEOMetadata.get_page_meta(
            title=category.seo_title or f"{category.name} Articles | EzzyDelivery Qatar Blog",
            description=category.seo_description or (
                f"Read {category.name} articles on EzzyDelivery Qatar blog. "
                f"Tips, insights & guides for delivery and logistics in Qatar."
            )[:155],
        )
    else:
        meta = SEOMetadata.get_page_meta(
            title="Delivery & Logistics Blog Qatar | EzzyDelivery",  # 50 chars
            description=(
                "EzzyDelivery Qatar blog: tips, insights & guides for e-commerce delivery, "
                "logistics, and supply chain management. Expert advice for Qatar businesses."
            ),  # 155 chars
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

    # SEO metadata - unique per blog post from DB fields
    meta = SEOMetadata.get_page_meta(
        title=post.get_seo_title,
        description=post.get_seo_description,
    )

    data = {
        'seo': meta,
        'post': post,
        'related_posts': related_posts,
        'trending_posts': trending_posts,
        # Serialise here: rendering the dict straight into the template emitted a
        # Python repr (single quotes, None) which is not valid JSON-LD, so search
        # engines silently dropped the block.
        'schema_markup': safe_json(post.get_schema_markup()),
    }
    return render(request, 'blog/post_detail.html', data)


def blog_index(request):
    """
    Blog home page - redirect to category view
    """
    return blog_category(request, slug=None)
