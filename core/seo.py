"""
SEO utilities for EzzyDelivery - Qatar Delivery Services
Focused on Qatar local search optimization

IMPORTANT: Meta keywords have been removed as they are no longer used by search engines.
Each page MUST have:
- Unique title (50-60 characters)
- Unique meta description (140-155 characters)
- Include: Primary keyword, Location (Qatar/Doha), Service intent
"""


class SEOMetadata:
    """SEO metadata generator for Qatar delivery services"""

    # Default metadata for the site
    SITE_NAME = "EzzyDelivery Qatar"
    SITE_TAGLINE = "Professional Delivery Services in Qatar | Same Day Delivery Doha"
    DEFAULT_DESCRIPTION = (
        "EzzyDelivery offers fast, reliable delivery services across Qatar. "
        "Same-day courier in Doha, Al Wakrah & Lusail. E-commerce fulfillment and COD available."
    )  # 155 chars

    SITE_URL = "https://ezzydelivery.qa"
    SITE_AUTHOR = "EzzyDelivery Qatar"
    SITE_LANGUAGE = "en-QA"
    SITE_REGION = "QA"

    # Contact information for local SEO
    BUSINESS_NAME = "EzzyDelivery"
    BUSINESS_PHONE = "+974-XXXX-XXXX"
    BUSINESS_EMAIL = "info@ezzydelivery.qa"
    BUSINESS_ADDRESS = "Doha, Qatar"

    # Social media
    FACEBOOK_URL = "https://facebook.com/ezzydeliveryqa"
    INSTAGRAM_URL = "https://instagram.com/ezzydeliveryqa"
    TWITTER_HANDLE = "@ezzydeliveryqa"

    @staticmethod
    def get_default_meta(title=None, description=None, url=None, image=None, page_type="website"):
        """Alias for get_page_meta for backwards compatibility"""
        return SEOMetadata.get_page_meta(title, description, url, image, page_type)

    @staticmethod
    def get_page_meta(
        title=None,
        description=None,
        url=None,
        image=None,
        page_type="website",
        **kwargs  # Accept but ignore keywords parameter for backwards compatibility
    ):
        """
        Generate complete SEO metadata for a page

        Args:
            title: Page title (will append site name if short enough)
            description: Page description (140-155 chars recommended)
            url: Canonical URL
            image: OG image URL
            page_type: Schema.org type (website, article, product, etc.)

        Returns:
            dict: Complete metadata dictionary (no keywords)
        """
        # Build title - keep under 60 chars total
        if title:
            # If title + site name is under 60 chars, append site name
            full_title = f"{title} | {SEOMetadata.SITE_NAME}" if len(f"{title} | {SEOMetadata.SITE_NAME}") <= 60 else title
        else:
            full_title = SEOMetadata.SITE_NAME

        # Use defaults if not provided
        description = description or SEOMetadata.DEFAULT_DESCRIPTION
        url = url or SEOMetadata.SITE_URL
        image = image or f"{SEOMetadata.SITE_URL}/static/images/ezzy-delivery-og.jpg"

        return {
            # Basic meta tags
            'title': full_title,
            'description': description,
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

    # =========================================================================
    # MAIN PAGES - Each with unique title (50-60 chars) & description (140-155 chars)
    # =========================================================================

    @staticmethod
    def get_home_meta():
        """Homepage - Primary landing page"""
        return SEOMetadata.get_page_meta(
            title="Fast Delivery Service Qatar | Same-Day Courier Doha",  # 52 chars
            description=(
                "Qatar's trusted delivery partner for businesses. Same-day pickup and delivery in Doha, "
                "Al Wakrah & Lusail. COD, tracking & e-commerce integration."
            ),  # 154 chars
        )

    @staticmethod
    def get_pricing_meta():
        """3PL Pricing page"""
        return SEOMetadata.get_page_meta(
            title="3PL Delivery Pricing Qatar | Get Your Quote Today",  # 51 chars
            description=(
                "Transparent 3PL pricing for Qatar businesses. Competitive rates for same-day delivery, "
                "fulfillment & COD. Volume discounts available. Request quote now."
            ),  # 155 chars
        )

    @staticmethod
    def get_contact_meta():
        """Contact Us page"""
        return SEOMetadata.get_page_meta(
            title="Contact EzzyDelivery Qatar | 24/7 Customer Support",  # 52 chars
            description=(
                "Reach EzzyDelivery Qatar via phone, email or WhatsApp. Our Doha team is available 24/7 "
                "for delivery inquiries, business partnerships & support."
            ),  # 152 chars
        )

    @staticmethod
    def get_services_meta():
        """Services overview page"""
        return SEOMetadata.get_page_meta(
            title="Delivery Services Qatar | Express, COD & Fulfillment",  # 54 chars
            description=(
                "Complete delivery solutions in Qatar: same-day express, cash on delivery, e-commerce "
                "fulfillment & last-mile logistics. Serving all Doha areas."
            ),  # 151 chars
        )

    @staticmethod
    def get_fulfillment_meta():
        """E-commerce Fulfillment page"""
        return SEOMetadata.get_page_meta(
            title="E-commerce Fulfillment Qatar | 3PL Warehouse Doha",  # 51 chars
            description=(
                "Full-service e-commerce fulfillment in Qatar. Warehousing, inventory management, pick & "
                "pack, same-day dispatch. Trusted by 500+ online stores."
            ),  # 152 chars
        )

    @staticmethod
    def get_qcommerce_meta():
        """Quick Commerce page"""
        return SEOMetadata.get_page_meta(
            title="Quick Commerce Delivery Qatar | On-Demand Q-Commerce",  # 53 chars
            description=(
                "Ultra-fast Q-commerce delivery in Qatar. 1-2 hour delivery for groceries, food & essentials. "
                "Technology-powered rapid logistics for Doha businesses."
            ),  # 155 chars
        )

    @staticmethod
    def get_about_meta():
        """About Us page"""
        return SEOMetadata.get_page_meta(
            title="About EzzyDelivery | Qatar's Trusted Delivery Partner",  # 54 chars
            description=(
                "Learn about EzzyDelivery - Qatar's growing delivery company. Our mission, values & "
                "commitment to reliable logistics across Doha since 2020."
            ),  # 147 chars
        )

    @staticmethod
    def get_careers_meta():
        """Careers page"""
        return SEOMetadata.get_page_meta(
            title="Delivery Driver Jobs Qatar | Join EzzyDelivery Doha",  # 52 chars
            description=(
                "Join EzzyDelivery Qatar. We're hiring delivery drivers, operations staff & customer "
                "support in Doha. Competitive pay, flexible hours. Apply now."
            ),  # 152 chars
        )

    @staticmethod
    def get_terms_meta():
        """Terms & Conditions page"""
        return SEOMetadata.get_page_meta(
            title="Terms & Conditions | EzzyDelivery Qatar Service",  # 49 chars
            description=(
                "Read EzzyDelivery Qatar's terms of service. Delivery policies, liability terms, "
                "COD handling & service agreements for businesses and customers."
            ),  # 150 chars
        )

    @staticmethod
    def get_privacy_meta():
        """Privacy Policy page"""
        return SEOMetadata.get_page_meta(
            title="Privacy Policy | EzzyDelivery Qatar Data Protection",  # 53 chars
            description=(
                "EzzyDelivery Qatar privacy policy. How we collect, use & protect your data. "
                "GDPR-compliant practices for secure delivery service operations."
            ),  # 148 chars
        )

    @staticmethod
    def get_business_dashboard_meta():
        """Business Dashboard (authenticated)"""
        return SEOMetadata.get_page_meta(
            title="Business Dashboard | Manage Deliveries Qatar",  # 46 chars
            description=(
                "EzzyDelivery business portal. Manage orders, track deliveries, view analytics & "
                "reports. Real-time delivery management for Qatar businesses."
            ),  # 149 chars
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
            "latitude": 25.286106,
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
            {"@type": "City", "name": "Al Wakrah"},
            {"@type": "City", "name": "Al Rayyan"},
            {"@type": "City", "name": "Lusail"}
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
                    "Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"
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


# =============================================================================
# SEO LANDING PAGES - High-conversion pages targeting specific keywords
# Each MUST have unique title (50-60 chars) and description (140-155 chars)
# =============================================================================

class SEOLandingPages:
    """SEO metadata for high-conversion landing pages targeting Qatar keywords"""

    @staticmethod
    def get_delivery_companies_qatar_meta():
        """Target: 'delivery companies in qatar' (443 impressions, pos 5.86)"""
        return SEOMetadata.get_page_meta(
            title="Top Delivery Companies in Qatar 2025 | Compare Services",  # 55 chars
            description=(
                "Compare the best delivery companies in Qatar. Find reliable courier services in Doha "
                "with same-day delivery, COD & tracking. Get quotes from top providers."
            ),  # 155 chars
        )

    @staticmethod
    def get_delivery_service_qatar_meta():
        """Target: 'delivery service in qatar' (103 impressions, pos 9.41)"""
        return SEOMetadata.get_page_meta(
            title="Professional Delivery Service Qatar | Reliable Courier",  # 55 chars
            description=(
                "Expert delivery service across Qatar for businesses & individuals. Fast pickup, real-time "
                "tracking, COD available. Serving Doha, Al Wakrah & Lusail."
            ),  # 154 chars
        )

    @staticmethod
    def get_same_day_delivery_qatar_meta():
        """Target: 'same day delivery qatar'"""
        return SEOMetadata.get_page_meta(
            title="Same-Day Delivery Qatar | Express Courier Within Hours",  # 55 chars
            description=(
                "Guaranteed same-day delivery in Qatar. Pickup within 2 hours, deliver by evening. "
                "Perfect for urgent orders across Doha. Track every delivery live."
            ),  # 152 chars
        )

    @staticmethod
    def get_cod_delivery_qatar_meta():
        """Target: 'cod service qatar'"""
        return SEOMetadata.get_page_meta(
            title="COD Delivery Service Qatar | Cash on Delivery Doha",  # 51 chars
            description=(
                "Reliable COD service for Qatar e-commerce & Instagram sellers. Collect payments on "
                "delivery across all Qatar. Fast settlement, low fees, full tracking."
            ),  # 155 chars
        )

    @staticmethod
    def get_ecommerce_delivery_qatar_meta():
        """Target: 'ecommerce delivery qatar'"""
        return SEOMetadata.get_page_meta(
            title="E-commerce Delivery Qatar | Online Store Shipping",  # 50 chars
            description=(
                "Complete e-commerce shipping solutions in Qatar. Shopify & WooCommerce integration, "
                "automated orders, COD & same-day delivery. Join 500+ online stores."
            ),  # 155 chars
        )

    @staticmethod
    def get_instagram_sellers_delivery_meta():
        """Target: Instagram sellers and social commerce"""
        return SEOMetadata.get_page_meta(
            title="Instagram Seller Delivery Qatar | Social Commerce",  # 50 chars
            description=(
                "Perfect delivery partner for Instagram sellers in Qatar. No minimum orders, easy COD, "
                "WhatsApp integration. Affordable rates for small business owners."
            ),  # 154 chars
        )

    @staticmethod
    def get_express_delivery_qatar_meta():
        """Target: 'express delivery qatar'"""
        return SEOMetadata.get_page_meta(
            title="Express Delivery Qatar | Urgent Courier 2-Hour Pickup",  # 54 chars
            description=(
                "Express courier service in Qatar with 2-hour pickup guarantee. Urgent document & "
                "parcel delivery across Doha, Lusail & Al Wakrah. Fully tracked."
            ),  # 150 chars
        )

    @staticmethod
    def get_courier_service_qatar_meta():
        """Target: 'courier service qatar'"""
        return SEOMetadata.get_page_meta(
            title="Courier Service Qatar | Professional Parcel Delivery",  # 53 chars
            description=(
                "Professional courier service in Qatar. Document delivery, parcel shipping & business "
                "logistics across Doha. Affordable rates, real-time tracking, COD."
            ),  # 154 chars
        )

    @staticmethod
    def get_3pl_qatar_meta():
        """Target: '3pl qatar'"""
        return SEOMetadata.get_page_meta(
            title="3PL Services Qatar | Third-Party Logistics Doha",  # 48 chars
            description=(
                "Complete 3PL solutions in Qatar. Warehousing, inventory management, order fulfillment "
                "& distribution. Trusted third-party logistics for e-commerce."
            ),  # 153 chars
        )

    @staticmethod
    def get_last_mile_delivery_qatar_meta():
        """Target: 'last mile delivery qatar'"""
        return SEOMetadata.get_page_meta(
            title="Last-Mile Delivery Qatar | Final-Mile Logistics Doha",  # 53 chars
            description=(
                "Efficient last-mile delivery in Qatar. Optimized routes, same-day options & live "
                "tracking. Final-mile logistics for e-commerce, retail & B2B."
            ),  # 148 chars
        )

    @staticmethod
    def get_logistics_services_qatar_meta():
        """Target: 'logistics services qatar'"""
        return SEOMetadata.get_page_meta(
            title="Logistics Services Qatar | Supply Chain Solutions Doha",  # 54 chars
            description=(
                "Comprehensive logistics services in Qatar. Delivery, warehousing & distribution for "
                "B2B and B2C. Your complete supply chain partner in Doha."
            ),  # 148 chars
        )

    @staticmethod
    def get_online_store_delivery_qatar_meta():
        """Target: 'online store delivery qatar'"""
        return SEOMetadata.get_page_meta(
            title="Online Store Delivery Qatar | E-commerce Shipping",  # 50 chars
            description=(
                "Reliable delivery for online stores in Qatar. Shopify, WooCommerce & custom platforms. "
                "Same-day shipping, COD & automated order sync. Scale your store."
            ),  # 155 chars
        )

    # =========================================================================
    # NEW: Arabic Keyword Pages & Location-Specific Landing Pages
    # =========================================================================

    @staticmethod
    def get_delivery_doha_meta():
        """Target: 'delivery doha', 'doha courier service'"""
        return SEOMetadata.get_page_meta(
            title="Delivery Service Doha | Fast Courier in Doha Qatar",  # 51 chars
            description=(
                "Fast delivery service in Doha, Qatar. Same-day courier across all Doha districts. "
                "West Bay, Pearl, Al Sadd, Old Airport & more. COD, tracking included."
            ),  # 154 chars
        )

    @staticmethod
    def get_business_delivery_qatar_meta():
        """Target: 'business delivery qatar', 'b2b delivery service qatar'"""
        return SEOMetadata.get_page_meta(
            title="Business Delivery Qatar | B2B Courier Service Doha",  # 51 chars
            description=(
                "Professional B2B delivery service in Qatar. Office-to-office courier, document delivery "
                "& corporate logistics. Scheduled pickups, bulk rates, invoicing."
            ),  # 155 chars
        )

    @staticmethod
    def get_package_delivery_qatar_meta():
        """Target: 'package delivery qatar', 'parcel delivery qatar'"""
        return SEOMetadata.get_page_meta(
            title="Package Delivery Qatar | Parcel Courier Service Doha",  # 53 chars
            description=(
                "Secure package delivery across Qatar. All sizes accepted - small parcels to large boxes. "
                "Same-day options, insurance available, real-time tracking."
            ),  # 153 chars
        )

    @staticmethod
    def get_shopify_delivery_qatar_meta():
        """Target: 'shopify delivery qatar', 'shopify fulfillment qatar'"""
        return SEOMetadata.get_page_meta(
            title="Shopify Delivery Qatar | E-commerce Fulfillment",  # 48 chars
            description=(
                "Seamless Shopify integration for Qatar stores. Auto-sync orders, print labels, track "
                "deliveries. COD support, same-day shipping. Connect in 5 minutes."
            ),  # 154 chars
        )

    @staticmethod
    def get_delivery_qatar_arabic_meta():
        """Target: 'توصيل قطر', 'خدمة توصيل قطر' (Arabic: delivery qatar)"""
        return SEOMetadata.get_page_meta(
            title="توصيل قطر | خدمة توصيل سريعة في الدوحة",  # Arabic: Delivery Qatar | Fast Delivery Service in Doha
            description=(
                "أفضل خدمة توصيل في قطر. توصيل سريع في نفس اليوم في الدوحة، الوكرة ولوسيل. "
                "خدمة الدفع عند الاستلام متوفرة. تتبع الطلبات مباشرة."
            ),  # Arabic description
        )

    @staticmethod
    def get_courier_doha_arabic_meta():
        """Target: 'شركة توصيل الدوحة', 'كوريير قطر' (Arabic: courier company doha)"""
        return SEOMetadata.get_page_meta(
            title="شركة توصيل الدوحة | كوريير قطر الموثوق",  # Arabic: Delivery Company Doha | Trusted Qatar Courier
            description=(
                "شركة توصيل موثوقة في الدوحة وجميع أنحاء قطر. توصيل طرود، مستندات وتجارة إلكترونية. "
                "أسعار منافسة وخدمة عملاء ممتازة."
            ),  # Arabic description
        )

    @staticmethod
    def get_food_delivery_partner_qatar_meta():
        """Target: 'food delivery partner qatar', 'restaurant delivery service qatar'"""
        return SEOMetadata.get_page_meta(
            title="Food Delivery Partner Qatar | Restaurant Courier",  # 49 chars
            description=(
                "Reliable food delivery partner for Qatar restaurants. Temperature-controlled delivery, "
                "fast dispatch, branded experience. Join 100+ restaurants using us."
            ),  # 153 chars
        )

    @staticmethod
    def get_al_wakrah_delivery_meta():
        """Target: 'delivery al wakrah', 'al wakrah courier'"""
        return SEOMetadata.get_page_meta(
            title="Delivery Service Al Wakrah | Courier Al Wakrah Qatar",  # 53 chars
            description=(
                "Fast delivery service in Al Wakrah, Qatar. Same-day pickup & delivery. Coverage includes "
                "Al Wakrah City, Ezdan Village & surrounding areas. COD available."
            ),  # 155 chars
        )

    @staticmethod
    def get_lusail_delivery_meta():
        """Target: 'delivery lusail', 'lusail courier service'"""
        return SEOMetadata.get_page_meta(
            title="Delivery Service Lusail | Courier Lusail City Qatar",  # 52 chars
            description=(
                "Premium delivery service in Lusail City, Qatar. Fox Hills, Marina District & Entertainment "
                "City coverage. Same-day express, COD & business accounts."
            ),  # 154 chars
        )
