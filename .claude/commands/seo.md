---
description: SEO expert mode for search optimization
---

# SEO Expert Mode

You are now in SEO expert mode for the EzzyDelivery project. Reference the skill file at `.claude/skills/seo.md` for detailed patterns.

## SEO Stack
| Component | Location |
|-----------|----------|
| Meta Tags | `templates/base.html` |
| Structured Data | JSON-LD in template blocks |
| Sitemap | `webpages/sitemaps.py` |
| Robots.txt | `static/robots.txt` |

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

User-agent: PerplexityBot
Allow: /

User-agent: anthropic-ai
Allow: /
```

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
