// JSON-LD Structured Data for Delivery Companies Qatar Page
(function() {
    // FAQPage Schema
    const faqSchema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What makes Ezzy Delivery the best delivery company in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Ezzy Delivery stands out with same-day delivery across all Qatar, comprehensive COD services, real-time tracking, seamless e-commerce integration, and dedicated support. We serve 500+ active businesses with 50,000+ monthly deliveries and maintain a 4.8-star rating."
                }
            },
            {
                "@type": "Question",
                "name": "How fast is same-day delivery in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We offer same-day delivery with pickup within 2 hours and delivery on the same day across Doha, Al Wakrah, Lusail, and Al Rayyan. For express services, we can deliver within 4-6 hours depending on the pickup and delivery locations."
                }
            },
            {
                "@type": "Question",
                "name": "Do you provide COD (Cash on Delivery) service in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes! We provide comprehensive COD services perfect for online stores, Instagram sellers, and e-commerce businesses. We collect cash on delivery and provide fast settlement within 3-5 business days."
                }
            },
            {
                "@type": "Question",
                "name": "Can I integrate Ezzy Delivery with my online store?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Absolutely! We offer seamless integration with Shopify, WooCommerce, and custom e-commerce platforms. Our API enables automated order sync, real-time tracking updates, and streamlined delivery management."
                }
            },
            {
                "@type": "Question",
                "name": "What areas in Qatar do you deliver to?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We deliver to all areas in Qatar including Doha, Al Wakrah, Lusail, Al Rayyan, Ain Khaled, Umm Salal, Al Khor, Mesaieed, and Dukhan. Same-day delivery is available for most urban areas."
                }
            }
        ]
    };

    // Service Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Delivery Service",
        "provider": {
            "@type": "LocalBusiness",
            "name": "EzzyDelivery",
            "image": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png",
            "telephone": "+974-XXXX-XXXX",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Doha",
                "addressCountry": "QA"
            }
        },
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        },
        "description": "Professional delivery and courier services in Qatar. Same-day delivery, COD services, e-commerce integration across Doha, Al Wakrah, Lusail.",
        "offers": {
            "@type": "Offer",
            "priceRange": "$$"
        }
    };

    // Breadcrumb Schema
    const breadcrumbSchema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": "https://ezzydelivery.qa/"
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Delivery Companies in Qatar",
                "item": "https://ezzydelivery.qa/delivery-companies-in-qatar/"
            }
        ]
    };

    // Inject FAQ Schema
    const faqScript = document.createElement('script');
    faqScript.type = 'application/ld+json';
    faqScript.textContent = JSON.stringify(faqSchema);
    document.head.appendChild(faqScript);

    // Inject Service Schema
    const serviceScript = document.createElement('script');
    serviceScript.type = 'application/ld+json';
    serviceScript.textContent = JSON.stringify(serviceSchema);
    document.head.appendChild(serviceScript);

    // Inject Breadcrumb Schema
    const breadcrumbScript = document.createElement('script');
    breadcrumbScript.type = 'application/ld+json';
    breadcrumbScript.textContent = JSON.stringify(breadcrumbSchema);
    document.head.appendChild(breadcrumbScript);
})();
