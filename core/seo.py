"""
SEO utilities for EzzyDelivery - Qatar Delivery Services
Focused on Qatar local search optimization
"""

# Qatar Delivery Services - Primary Keywords
QATAR_KEYWORDS = [
    # Core delivery services
    "delivery service Qatar",
    "courier service Qatar",
    "delivery company Qatar",
    "Qatar delivery services",
    "same day delivery Qatar",
    "express delivery Qatar",
    "fast delivery Qatar",
    "delivery service Doha",
    "courier service Doha",

    # E-commerce integration
    "e-commerce delivery Qatar",
    "online store delivery Qatar",
    "Shopify delivery Qatar",
    "WooCommerce delivery Qatar",
    "Qatar fulfillment services",

    # Last mile delivery
    "last mile delivery Qatar",
    "last mile logistics Qatar",
    "delivery management system Qatar",
    "DMS Qatar",

    # Cash on delivery
    "COD service Qatar",
    "cash on delivery Qatar",
    "COD delivery Doha",

    # Local areas
    "delivery service Doha Qatar",
    "Al Wakrah delivery",
    "Al Rayyan delivery",
    "Lusail delivery service",
    "West Bay delivery",

    # Business solutions
    "business delivery solutions Qatar",
    "Qatar logistics services",
    "delivery API Qatar",
    "automated delivery system Qatar",
    "delivery tracking Qatar",

    # Specific services
    "same day pickup Qatar",
    "door to door delivery Qatar",
    "parcel delivery Qatar",
    "package delivery Qatar",
    "freight delivery Qatar",
]

# Long-tail keywords for specific searches
LONG_TAIL_KEYWORDS = [
    "best delivery service in Qatar",
    "affordable delivery service Qatar",
    "reliable courier service Doha",
    "24 hour delivery service Qatar",
    "next day delivery Qatar",
    "weekend delivery service Qatar",
    "delivery service for small business Qatar",
    "e-commerce logistics Qatar",
    "delivery management software Qatar",
]


class SEOMetadata:
    """SEO metadata generator for Qatar delivery services"""

    # Default metadata for the site
    SITE_NAME = "EzzyDelivery Qatar"
    SITE_TAGLINE = "Professional Delivery Services in Qatar | Same Day Delivery Doha"
    DEFAULT_DESCRIPTION = (
        "EzzyDelivery - Qatar's leading delivery and courier service. "
        "Same day delivery in Doha, Al Wakrah, Lusail. E-commerce fulfillment, "
        "COD services, real-time tracking. Reliable last mile delivery solutions for businesses."
    )
    DEFAULT_KEYWORDS = ", ".join(QATAR_KEYWORDS[:20])  # Top 20 keywords

    SITE_URL = "https://ezzydelivery.qa"  # Update with actual domain
    SITE_AUTHOR = "EzzyDelivery Qatar"
    SITE_LANGUAGE = "en-QA"
    SITE_REGION = "QA"

    # Contact information for local SEO
    BUSINESS_NAME = "EzzyDelivery"
    BUSINESS_PHONE = "+974-XXXX-XXXX"  # Update with actual phone
    BUSINESS_EMAIL = "info@ezzydelivery.qa"
    BUSINESS_ADDRESS = "Doha, Qatar"  # Update with actual address

    # Social media
    FACEBOOK_URL = "https://facebook.com/ezzydeliveryqa"
    INSTAGRAM_URL = "https://instagram.com/ezzydeliveryqa"
    TWITTER_HANDLE = "@ezzydeliveryqa"

    @staticmethod
    def get_page_meta(
        title=None,
        description=None,
        keywords=None,
        url=None,
        image=None,
        page_type="website"
    ):
        """
        Generate complete SEO metadata for a page

        Args:
            title: Page title (will append site name)
            description: Page description
            keywords: List of keywords or comma-separated string
            url: Canonical URL
            image: OG image URL
            page_type: Schema.org type (website, article, product, etc.)

        Returns:
            dict: Complete metadata dictionary
        """
        # Handle keywords
        if keywords:
            if isinstance(keywords, list):
                keywords = ", ".join(keywords)
        else:
            keywords = SEOMetadata.DEFAULT_KEYWORDS

        # Append site name to title
        full_title = f"{title} | {SEOMetadata.SITE_NAME}" if title else SEOMetadata.SITE_NAME

        # Use defaults if not provided
        description = description or SEOMetadata.DEFAULT_DESCRIPTION
        url = url or SEOMetadata.SITE_URL
        image = image or f"{SEOMetadata.SITE_URL}/static/images/ezzy-delivery-og.jpg"

        return {
            # Basic meta tags
            'title': full_title,
            'description': description,
            'keywords': keywords,
            'author': SEOMetadata.SITE_AUTHOR,
            'canonical_url': url,

            # Language and region
            'language': SEOMetadata.SITE_LANGUAGE,
            'region': SEOMetadata.SITE_REGION,

            # Open Graph
            'og_title': full_title,
            'og_description': description,
            'og_url': url,
            'og_image': image,
            'og_type': page_type,
            'og_site_name': SEOMetadata.SITE_NAME,
            'og_locale': 'en_QA',

            # Twitter Card
            'twitter_card': 'summary_large_image',
            'twitter_title': full_title,
            'twitter_description': description,
            'twitter_image': image,
            'twitter_site': SEOMetadata.TWITTER_HANDLE,

            # Mobile
            'viewport': 'width=device-width, initial-scale=1.0',
            'mobile_optimized': 'width',
            'handheld_friendly': 'true',

            # Additional
            'robots': 'index, follow',
            'revisit_after': '7 days',
            'distribution': 'global',
            'rating': 'general',
        }

    @staticmethod
    def get_home_meta():
        """Optimized metadata for homepage"""
        return SEOMetadata.get_page_meta(
            title="Professional Delivery & Courier Service in Qatar | Doha Same Day Delivery",
            description=(
                "EzzyDelivery - Qatar's #1 delivery service. Same day delivery in Doha, "
                "Al Wakrah, Lusail & nationwide. E-commerce fulfillment, COD, real-time tracking. "
                "Trusted by 500+ businesses. Fast, reliable, affordable delivery solutions."
            ),
            keywords=QATAR_KEYWORDS[:15],
        )

    @staticmethod
    def get_pricing_meta():
        """Metadata for pricing page"""
        return SEOMetadata.get_page_meta(
            title="Delivery Service Pricing Qatar | Affordable Courier Rates Doha",
            description=(
                "Transparent delivery pricing in Qatar. Competitive rates for same day delivery, "
                "express courier, COD services. Special packages for businesses. "
                "Get instant quote for delivery services in Doha and all Qatar."
            ),
            keywords=[
                "delivery rates Qatar",
                "courier service price Doha",
                "delivery cost Qatar",
                "affordable delivery Qatar",
                "delivery pricing Doha",
            ],
        )

    @staticmethod
    def get_contact_meta():
        """Metadata for contact page"""
        return SEOMetadata.get_page_meta(
            title="Contact Us | EzzyDelivery Qatar Customer Support Doha",
            description=(
                "Contact EzzyDelivery Qatar for delivery inquiries. "
                "Customer support in Doha. Phone, email, WhatsApp available. "
                "24/7 support for urgent delivery needs in Qatar."
            ),
            keywords=[
                "contact delivery service Qatar",
                "delivery customer support Doha",
                "Qatar courier contact",
            ],
        )

    @staticmethod
    def get_business_dashboard_meta():
        """Metadata for business dashboard"""
        return SEOMetadata.get_page_meta(
            title="Business Dashboard | Manage Delivery Orders Qatar",
            description=(
                "EzzyDelivery business portal. Manage orders, track deliveries, "
                "view analytics for your Qatar delivery operations. "
                "Real-time delivery management system."
            ),
            keywords=[
                "delivery management Qatar",
                "order tracking system Qatar",
                "business delivery portal",
            ],
        )

    @staticmethod
    def get_services_meta():
        """Metadata for services page"""
        return SEOMetadata.get_page_meta(
            title="Delivery Services Qatar | Same Day, Express, COD - EzzyDelivery",
            description=(
                "Complete delivery solutions in Qatar: Same day delivery, express courier, "
                "COD services, e-commerce fulfillment, last mile logistics. "
                "Serving Doha, Al Wakrah, Lusail and all Qatar."
            ),
            keywords=[
                "delivery services Qatar",
                "same day delivery Doha",
                "express courier Qatar",
                "COD service Qatar",
                "last mile delivery",
                "logistics services Qatar",
            ],
        )

    @staticmethod
    def get_fulfillment_meta():
        """Metadata for fulfillment page"""
        return SEOMetadata.get_page_meta(
            title="E-commerce Fulfillment Services Qatar | 3PL Warehousing Doha",
            description=(
                "Professional e-commerce fulfillment and 3PL services in Qatar. "
                "Warehousing, inventory management, order processing, same day dispatch. "
                "Complete fulfillment solutions for online stores in Doha."
            ),
            keywords=[
                "fulfillment services Qatar",
                "3PL Qatar",
                "e-commerce warehousing Doha",
                "order fulfillment Qatar",
                "inventory management Qatar",
            ],
        )

    @staticmethod
    def get_qcommerce_meta():
        """Metadata for quick commerce page"""
        return SEOMetadata.get_page_meta(
            title="Quick Commerce Delivery Qatar | Q-Commerce Solutions Doha",
            description=(
                "Quick commerce and on-demand delivery solutions in Qatar. "
                "Ultra-fast delivery for groceries, food, essentials. "
                "Q-commerce technology for rapid delivery in Doha and Qatar."
            ),
            keywords=[
                "quick commerce Qatar",
                "q-commerce Doha",
                "on-demand delivery Qatar",
                "rapid delivery services",
                "grocery delivery Qatar",
            ],
        )

    @staticmethod
    def get_about_meta():
        """Metadata for about page"""
        return SEOMetadata.get_page_meta(
            title="About EzzyDelivery | Leading Delivery Company in Qatar",
            description=(
                "About EzzyDelivery - Qatar's trusted delivery partner. "
                "Learn about our mission, values, and commitment to excellence "
                "in delivery services across Doha and Qatar since 2020."
            ),
            keywords=[
                "about EzzyDelivery",
                "delivery company Qatar",
                "Qatar logistics company",
                "trusted delivery partner",
            ],
        )

    @staticmethod
    def get_careers_meta():
        """Metadata for careers page"""
        return SEOMetadata.get_page_meta(
            title="Careers at EzzyDelivery Qatar | Join Our Delivery Team Doha",
            description=(
                "Join EzzyDelivery Qatar team. Career opportunities for drivers, "
                "operations staff, customer service in Doha. "
                "Be part of Qatar's leading delivery service."
            ),
            keywords=[
                "delivery jobs Qatar",
                "driver jobs Doha",
                "careers EzzyDelivery",
                "logistics jobs Qatar",
            ],
        )

    @staticmethod
    def get_terms_meta():
        """Metadata for terms page"""
        return SEOMetadata.get_page_meta(
            title="Terms and Conditions | EzzyDelivery Qatar Delivery Service",
            description=(
                "Terms and conditions for EzzyDelivery Qatar delivery services. "
                "Service agreement, liability, delivery terms for businesses and customers."
            ),
            keywords=[
                "delivery terms Qatar",
                "service conditions",
                "EzzyDelivery terms",
            ],
        )

    @staticmethod
    def get_privacy_meta():
        """Metadata for privacy page"""
        return SEOMetadata.get_page_meta(
            title="Privacy Policy | EzzyDelivery Qatar Data Protection",
            description=(
                "Privacy policy and data protection at EzzyDelivery Qatar. "
                "How we collect, use, and protect your information. "
                "GDPR compliant delivery service."
            ),
            keywords=[
                "privacy policy Qatar",
                "data protection",
                "EzzyDelivery privacy",
            ],
        )


def generate_json_ld_local_business():
    """
    Generate JSON-LD structured data for Local Business (Qatar)
    This helps with Google My Business and local search rankings
    """
    return {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": "EzzyDelivery",
        "image": f"{SEOMetadata.SITE_URL}/static/images/ezzy-logo.png",
        "@id": SEOMetadata.SITE_URL,
        "url": SEOMetadata.SITE_URL,
        "telephone": SEOMetadata.BUSINESS_PHONE,
        "priceRange": "$$",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": SEOMetadata.BUSINESS_ADDRESS,
            "addressLocality": "Doha",
            "addressRegion": "Doha",
            "postalCode": "",
            "addressCountry": "QA"
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 25.286106,  # Doha coordinates
            "longitude": 51.534817
        },
        "sameAs": [
            SEOMetadata.FACEBOOK_URL,
            SEOMetadata.INSTAGRAM_URL,
            f"https://twitter.com/{SEOMetadata.TWITTER_HANDLE.replace('@', '')}"
        ],
        "areaServed": [
            {
                "@type": "City",
                "name": "Doha",
                "containedIn": {
                    "@type": "Country",
                    "name": "Qatar"
                }
            },
            {
                "@type": "City",
                "name": "Al Wakrah"
            },
            {
                "@type": "City",
                "name": "Al Rayyan"
            },
            {
                "@type": "City",
                "name": "Lusail"
            }
        ],
        "serviceType": [
            "Delivery Service",
            "Courier Service",
            "Same Day Delivery",
            "Express Delivery",
            "COD Service",
            "E-commerce Fulfillment",
            "Last Mile Delivery"
        ],
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday"
                ],
                "opens": "08:00",
                "closes": "22:00"
            }
        ]
    }


def generate_json_ld_organization():
    """Generate JSON-LD for Organization"""
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "EzzyDelivery",
        "url": SEOMetadata.SITE_URL,
        "logo": f"{SEOMetadata.SITE_URL}/static/images/ezzy-logo.png",
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": SEOMetadata.BUSINESS_PHONE,
            "contactType": "Customer Service",
            "areaServed": "QA",
            "availableLanguage": ["English", "Arabic"]
        },
        "sameAs": [
            SEOMetadata.FACEBOOK_URL,
            SEOMetadata.INSTAGRAM_URL,
        ]
    }


def generate_json_ld_breadcrumb(items):
    """
    Generate JSON-LD for breadcrumb navigation

    Args:
        items: List of tuples (name, url)

    Example:
        items = [
            ("Home", "/"),
            ("Services", "/services/"),
            ("Pricing", "/pricing/")
        ]
    """
    item_list = []
    for position, (name, url) in enumerate(items, start=1):
        item_list.append({
            "@type": "ListItem",
            "position": position,
            "name": name,
            "item": f"{SEOMetadata.SITE_URL}{url}" if not url.startswith('http') else url
        })

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": item_list
    }


def generate_json_ld_service(service_name, description, price_range=""):
    """Generate JSON-LD for a specific service"""
    return {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": service_name,
        "provider": {
            "@type": "Organization",
            "name": "EzzyDelivery"
        },
        "description": description,
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        },
        "offers": {
            "@type": "Offer",
            "priceRange": price_range
        }
    }
