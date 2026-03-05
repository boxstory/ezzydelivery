// JSON-LD Structured Data for 3PL Qatar Page
(function() {
    // Service Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Third Party Logistics (3PL)",
        "provider": {
            "@type": "Organization",
            "name": "EzzyDelivery Qatar",
            "url": "https://ezzydelivery.qa"
        },
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        },
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "3PL Services",
            "itemListElement": [
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "name": "Warehousing & Storage"
                    }
                },
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "name": "Order Fulfillment"
                    }
                },
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "name": "Last-Mile Delivery"
                    }
                }
            ]
        }
    };

    // FAQPage Schema
    const faqSchema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What is the minimum order volume for 3PL services?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We work with businesses of all sizes. Whether you have 50 orders per month or 5,000, our 3PL solutions scale to your needs. No minimum order requirements."
                }
            },
            {
                "@type": "Question",
                "name": "How much does 3PL cost in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "3PL pricing includes warehousing (per pallet/month), fulfillment (per order), and delivery fees. Costs vary based on volume and services."
                }
            }
        ]
    };

    // Inject Service Schema
    const serviceScript = document.createElement('script');
    serviceScript.type = 'application/ld+json';
    serviceScript.textContent = JSON.stringify(serviceSchema);
    document.head.appendChild(serviceScript);

    // Inject FAQ Schema
    const faqScript = document.createElement('script');
    faqScript.type = 'application/ld+json';
    faqScript.textContent = JSON.stringify(faqSchema);
    document.head.appendChild(faqScript);

    // BreadcrumbList
    const breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://ezzydelivery.qa/"},
            {"@type": "ListItem", "position": 2, "name": "3PL Services Qatar", "item": "https://ezzydelivery.qa/3pl-qatar/"}
        ]
    };
    const bcScript = document.createElement('script');
    bcScript.type = 'application/ld+json';
    bcScript.textContent = JSON.stringify(breadcrumb);
    document.head.appendChild(bcScript);
})();
