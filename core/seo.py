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
    def get_default_meta(title=None, description=None, keywords=None, url=None, image=None, page_type="website"):
        """Alias for get_page_meta for backwards compatibility"""
        return SEOMetadata.get_page_meta(title, description, keywords, url, image, page_type)

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


# SEO Landing Pages Meta Functions (Based on Search Console Data)

class SEOLandingPages:
    """SEO metadata for high-conversion landing pages targeting Qatar keywords"""

    @staticmethod
    def get_delivery_companies_qatar_meta():
        """Optimized for 'delivery companies in qatar' (443 impressions, pos 5.86)"""
        return SEOMetadata.get_page_meta(
            title="Best Delivery Companies in Qatar 2025 | Compare Courier Services Doha",
            description=(
                "Find the best delivery companies in Qatar for your business. Compare same-day delivery, "
                "COD services, e-commerce fulfillment in Doha, Al Wakrah & Lusail. Ezzy Delivery - "
                "Qatar's trusted logistics partner with 500+ satisfied businesses."
            ),
            keywords=[
                "delivery companies in qatar",
                "best delivery company qatar",
                "courier companies qatar",
                "delivery service providers doha",
                "logistics companies qatar",
                "delivery companies doha",
                "qatar delivery services comparison",
                "top courier companies qatar",
            ],
        )

    @staticmethod
    def get_delivery_service_qatar_meta():
        """Optimized for 'delivery service in qatar' (103 impressions, pos 9.41)"""
        return SEOMetadata.get_page_meta(
            title="Professional Delivery Service in Qatar | Fast & Reliable Courier Doha",
            description=(
                "Expert delivery service in Qatar for businesses & individuals. Same-day delivery, "
                "COD, real-time tracking across Doha, Al Wakrah, Lusail. Ezzy Delivery offers "
                "affordable, reliable courier services in Qatar. Get instant quote!"
            ),
            keywords=[
                "delivery service in qatar",
                "qatar delivery service",
                "delivery service qatar",
                "courier service in qatar",
                "delivery service doha",
                "professional delivery qatar",
                "reliable delivery service qatar",
            ],
        )

    @staticmethod
    def get_same_day_delivery_qatar_meta():
        """Optimized for same-day delivery searches"""
        return SEOMetadata.get_page_meta(
            title="Same Day Delivery Qatar | Express Courier Service Doha in 24 Hours",
            description=(
                "Same day delivery in Qatar guaranteed! Order pickup and delivery within hours across Doha, "
                "Al Wakrah, Lusail. Perfect for urgent deliveries, e-commerce orders, documents. "
                "Ezzy Delivery - Fast, affordable same-day courier service in Qatar."
            ),
            keywords=[
                "same day delivery qatar",
                "same day delivery doha",
                "express delivery qatar",
                "urgent delivery qatar",
                "24 hour delivery qatar",
                "fast delivery service qatar",
                "quick delivery doha",
            ],
        )

    @staticmethod
    def get_cod_delivery_qatar_meta():
        """Optimized for COD service searches"""
        return SEOMetadata.get_page_meta(
            title="COD Delivery Service Qatar | Cash on Delivery Doha - Secure & Fast",
            description=(
                "Reliable COD (Cash on Delivery) service in Qatar. Perfect for online stores, Instagram sellers, "
                "e-commerce businesses. Collect payments on delivery across all Qatar. Low fees, fast settlement, "
                "real-time tracking. Trusted COD delivery partner in Doha."
            ),
            keywords=[
                "COD service qatar",
                "cash on delivery qatar",
                "COD delivery doha",
                "COD delivery service qatar",
                "payment on delivery qatar",
                "cash collection delivery qatar",
                "cod courier service qatar",
            ],
        )

    @staticmethod
    def get_ecommerce_delivery_qatar_meta():
        """Optimized for e-commerce delivery searches"""
        return SEOMetadata.get_page_meta(
            title="E-commerce Delivery Qatar | Online Store Shipping Solutions Doha",
            description=(
                "Complete e-commerce delivery solutions in Qatar. Shopify, WooCommerce, Instagram store integration. "
                "Same-day delivery, COD, automated order sync, real-time tracking. Ezzy Delivery powers 500+ "
                "online stores in Qatar. Start shipping smarter today!"
            ),
            keywords=[
                "ecommerce delivery qatar",
                "online store delivery qatar",
                "shopify delivery qatar",
                "woocommerce delivery qatar",
                "ecommerce fulfillment qatar",
                "online business delivery doha",
                "ecommerce logistics qatar",
            ],
        )

    @staticmethod
    def get_instagram_sellers_delivery_meta():
        """Optimized for Instagram sellers and social commerce"""
        return SEOMetadata.get_page_meta(
            title="Delivery Service for Instagram Sellers Qatar | Social Commerce Shipping Doha",
            description=(
                "Perfect delivery solution for Instagram sellers in Qatar! Easy order management, COD collection, "
                "same-day delivery across Doha. No minimum orders, affordable rates, WhatsApp integration. "
                "Join 200+ Instagram businesses using Ezzy Delivery Qatar."
            ),
            keywords=[
                "instagram seller delivery qatar",
                "social media seller delivery qatar",
                "instagram business delivery doha",
                "small business delivery qatar",
                "home business delivery qatar",
                "online seller delivery service qatar",
            ],
        )

    @staticmethod
    def get_express_delivery_qatar_meta():
        """Optimized for express/urgent delivery searches"""
        return SEOMetadata.get_page_meta(
            title="Express Delivery Qatar | Urgent Courier Service Doha - 2 Hour Pickup",
            description=(
                "Express delivery in Qatar with 2-hour pickup guarantee. Urgent courier service for documents, "
                "parcels, e-commerce orders across Doha, Al Wakrah, Lusail. Fast, reliable, tracked. "
                "Ezzy Delivery - Qatar's fastest express courier service."
            ),
            keywords=[
                "express delivery qatar",
                "express courier qatar",
                "urgent delivery doha",
                "fast delivery service qatar",
                "express shipping qatar",
                "quick courier doha",
                "rapid delivery qatar",
            ],
        )

    @staticmethod
    def get_courier_service_qatar_meta():
        """Optimized for general courier service searches"""
        return SEOMetadata.get_page_meta(
            title="Courier Service Qatar | Professional Delivery Company Doha - Best Rates",
            description=(
                "Professional courier service in Qatar for businesses & individuals. Document delivery, parcel "
                "shipping, e-commerce fulfillment across Doha, Lusail, Al Wakrah. Affordable rates, real-time "
                "tracking, COD available. Trusted courier company in Qatar."
            ),
            keywords=[
                "courier service qatar",
                "courier company qatar",
                "courier doha",
                "parcel delivery qatar",
                "document courier qatar",
                "professional courier doha",
                "courier service doha qatar",
            ],
        )

    @staticmethod
    def get_3pl_qatar_meta():
        """Optimized for 3PL/third-party logistics searches"""
        return SEOMetadata.get_page_meta(
            title="3PL Qatar | Third Party Logistics & Fulfillment Services Doha",
            description=(
                "Complete 3PL solutions in Qatar. Warehousing, inventory management, order fulfillment, "
                "distribution across Qatar. Third-party logistics partner for e-commerce & businesses in Doha. "
                "Ezzy Delivery - Qatar's trusted 3PL provider."
            ),
            keywords=[
                "3pl qatar",
                "third party logistics qatar",
                "3pl services doha",
                "fulfillment center qatar",
                "warehouse services qatar",
                "logistics provider qatar",
                "3pl company doha",
            ],
        )

    @staticmethod
    def get_last_mile_delivery_qatar_meta():
        """Optimized for last mile delivery searches"""
        return SEOMetadata.get_page_meta(
            title="Last Mile Delivery Qatar | Final Mile Logistics Solutions Doha",
            description=(
                "Expert last mile delivery in Qatar. Final mile logistics for e-commerce, retail, B2B. "
                "Same-day delivery, route optimization, real-time tracking across Doha, Lusail, Al Wakrah. "
                "Ezzy Delivery - Optimizing last mile logistics in Qatar."
            ),
            keywords=[
                "last mile delivery qatar",
                "final mile delivery doha",
                "last mile logistics qatar",
                "last mile courier qatar",
                "final mile solutions qatar",
                "last mile delivery service doha",
            ],
        )

    @staticmethod
    def get_logistics_services_qatar_meta():
        """Optimized for broad logistics services searches"""
        return SEOMetadata.get_page_meta(
            title="Logistics Services Qatar | Complete Supply Chain Solutions Doha",
            description=(
                "Comprehensive logistics services in Qatar. Delivery, warehousing, distribution, supply chain "
                "management across Doha & all Qatar. B2B & B2C logistics solutions. Ezzy Delivery - "
                "Your complete logistics partner in Qatar."
            ),
            keywords=[
                "logistics services qatar",
                "logistics company qatar",
                "logistics doha",
                "supply chain qatar",
                "distribution services qatar",
                "logistics provider doha",
                "qatar logistics solutions",
            ],
        )

    @staticmethod
    def get_online_store_delivery_qatar_meta():
        """Optimized for online store delivery searches"""
        return SEOMetadata.get_page_meta(
            title="Online Store Delivery Qatar | E-commerce Shipping Solutions Doha",
            description=(
                "Complete delivery solutions for online stores in Qatar. Shopify, WooCommerce, custom stores. "
                "Same-day delivery, COD, order management, customer notifications. Power your online store "
                "with Ezzy Delivery Qatar - 500+ stores trust us."
            ),
            keywords=[
                "online store delivery qatar",
                "online shop delivery doha",
                "ecommerce shipping qatar",
                "online business delivery qatar",
                "webstore delivery doha",
                "internet store delivery qatar",
            ],
        )
