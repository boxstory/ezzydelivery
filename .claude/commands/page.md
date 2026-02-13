---
description: Create new pages with views and templates
---

# Create New Page

You are creating a new page for the EzzyDelivery project. Reference skills at `.claude/skills/`.

## Step 1: Determine Page Type

| Type | Extends | App | Use Case |
|------|---------|-----|----------|
| Public | `base.html` | webpages | Marketing, landing pages |
| Dashboard | `wf_dashboard_base.html` | workforce/app | Staff operations |
| API | DRF ViewSet | ezzy_api | JSON endpoints |

## Step 2: Create View

### Class-Based View (Preferred)
```python
# {app}/views.py
from django.views.generic import TemplateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin

class MyPageView(LoginRequiredMixin, TemplateView):
    template_name = '{app}/my_page.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Page Title'
        return context
```

### ListView with Filters
```python
class MyListView(LoginRequiredMixin, ListView):
    model = MyModel
    template_name = '{app}/my_list.html'
    context_object_name = 'items'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        # Add select_related/prefetch_related
        qs = qs.select_related('related_model')
        # Add filters from GET params
        if search := self.request.GET.get('search'):
            qs = qs.filter(name__icontains=search)
        return qs
```

## Step 3: Add URL

```python
# {app}/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('my-page/', views.MyPageView.as_view(), name='my_page'),
]
```

## Step 4: Create Template

### Dashboard Page
```html
{% extends 'wf_dashboard_base.html' %}
{% load static %}

{% block extra_css %}
<link rel="stylesheet" href="{% static '{app}/css/my_page.css' %}">
{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>{{ title }}</h1>
        <a href="{% url 'add_item' %}" class="btn btn-primary">
            <i class="fa-solid fa-plus"></i> Add New
        </a>
    </div>

    <!-- Content here -->
</div>
{% endblock %}

{% block extra_js %}
<script src="{% static '{app}/js/my_page.js' %}"></script>
{% endblock %}
```

### Public Page (with SEO)
```html
{% extends 'base.html' %}
{% load static %}

{% block title %}Page Title - EzzyDelivery{% endblock %}
{% block meta_description %}Description under 160 characters for SEO.{% endblock %}

{% block content %}
<div class="container py-5">
    <h1>Page Title</h1>
    <!-- Content -->
</div>
{% endblock %}
```

## Step 5: Add Navigation Link

### Dashboard Sidebar
```html
<!-- workforce/templates/workforce/parts/dashboard_sidebar_workforce.html -->
<a href="{% url 'my_page' %}" class="nav-link">
    <i class="fa-solid fa-icon"></i>
    <span>My Page</span>
</a>
```

## SEO Checklist (Public Pages)
- [ ] Meta title < 60 chars
- [ ] Meta description < 160 chars
- [ ] H1 with primary keyword
- [ ] Alt text on all images
- [ ] Internal links to related content

## Image Alt Tags (Required)
```html
<img src="{{ item.image.url }}"
     alt="{{ item.name }} - descriptive text"
     loading="lazy">
```

Please provide:
1. Page name and purpose
2. Which app it belongs to
3. Public or dashboard page
4. Data/features needed
