---
description: SEO expert mode for search optimization
---

# SEO Expert Mode

You are now in SEO expert mode for the EzzyDelivery project. Reference the skill file at `.claude/skills/seo.md` for detailed patterns.

## SEO Stack
| Component | Location |
|-----------|----------|
| Meta Tags | `templates/includes/head.html` |
| SEO Metadata | `core/seo.py` (SEOMetadata, SEOLandingPages) |
| Structured Data | JSON-LD in `templates/includes/head.html` |
| Sitemap | `core/sitemaps.py` |
| Robots.txt | `core/views_seo.py` (dynamic) |
| LLMs.txt | `core/views_seo.py` (AI search) |
| Landing Pages | `webpages/templates/webpages/seo/` |

## Critical Rules

### Image Alt Tags (MANDATORY)
```html
<!-- ALWAYS include descriptive alt text -->
<img src="image.jpg" alt="EzzyDelivery truck making same-day delivery in Lagos">

<!-- NEVER do this -->
<img src="image.jpg" alt="">
<img src="image.jpg" alt="image">
```
- Max 125 characters
- Keyword-rich but natural
- Describe the image content

### Meta Tags
- Title: Under 60 characters
- Description: Under 160 characters
- Every page needs unique meta tags

### Structured Data (JSON-LD)
- Organization Schema for brand
- LocalBusiness Schema for location
- FAQ Schema for Q&A pages
- BlogPosting Schema for articles
- Validate with Google Rich Results Test

## AI Search SEO (GEO)

### Content Structure for AI
- Clear, direct answers in first paragraph
- Question-based H2/H3 headings
- Bulleted/numbered lists
- Comparison tables
- Definition statements ("X is...")

### E-E-A-T Signals
- Author bylines with credentials
- Customer testimonials
- Case studies with real data
- Contact information visible

### robots.txt AI Crawlers
```txt
User-agent: GPTBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: PerplexityBot
Allow: /
```

## SEO Landing Pages (21 total)

### Location Pages
- `/delivery-doha/`
- `/al-wakrah-delivery/`
- `/lusail-delivery/`

### Service Pages
- `/delivery-companies-in-qatar/`
- `/same-day-delivery-qatar/`
- `/cod-delivery-service-qatar/`
- `/ecommerce-delivery-qatar/`
- `/express-delivery-qatar/`
- `/courier-service-qatar/`
- `/3pl-qatar/`
- `/last-mile-delivery-qatar/`
- `/logistics-services-qatar/`
- `/shopify-delivery-qatar/`
- `/business-delivery-qatar/`
- `/package-delivery-qatar/`
- `/food-delivery-partner-qatar/`

### Arabic Keywords
- `/توصيل-قطر/`
- `/شركة-توصيل-الدوحة/`

## Checklists

### Page Content
- [ ] H1 with primary keyword (one per page)
- [ ] Alt text on ALL images
- [ ] Internal links to related content
- [ ] Minimum 300 words

### Technical SEO
- [ ] Meta title < 60 chars
- [ ] Meta description < 160 chars
- [ ] Canonical URLs set
- [ ] Mobile-friendly
- [ ] HTTPS enabled

Please describe your SEO task.
