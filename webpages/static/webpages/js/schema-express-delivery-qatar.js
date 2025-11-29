// JSON-LD Structured Data for Express Delivery Qatar Page
(function() {
    // Service Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Express Delivery Service",
        "provider": {
            "@type": "Organization",
            "name": "EzzyDelivery Qatar",
            "url": "https://ezzydelivery.qa",
            "logo": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png",
            "contactPoint": {
                "@type": "ContactPoint",
                "telephone": "+974-6660-9347",
                "contactType": "Customer Service",
                "areaServed": "QA",
                "availableLanguage": ["English", "Arabic"]
            }
        },
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        },
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "Express Delivery Services",
            "itemListElement": [
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "name": "2-Hour Express Pickup",
                        "description": "Guaranteed pickup within 2 hours"
                    }
                },
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "name": "Same-Day Delivery",
                        "description": "Express delivery within the same business day"
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
                "name": "What is the pickup time for express delivery?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We guarantee pickup within 2 hours of placing your order. This is our express commitment - if you book before 4 PM, your package will be picked up the same day within 2 hours."
                }
            },
            {
                "@type": "Question",
                "name": "How fast is same-day express delivery?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Same-day express delivery means your parcel is picked up and delivered within the same business day. Typical delivery time is 4-6 hours from pickup for Doha area, and 6-8 hours for other areas in Qatar."
                }
            },
            {
                "@type": "Question",
                "name": "Can I track my express delivery?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes! All express deliveries include real-time GPS tracking. You receive a tracking link immediately after pickup, allowing you to monitor your parcel's exact location throughout the delivery journey."
                }
            }
        ]
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
                "name": "Express Delivery Qatar",
                "item": "https://ezzydelivery.qa/express-delivery-qatar/"
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

    // Inject Breadcrumb Schema
    const breadcrumbScript = document.createElement('script');
    breadcrumbScript.type = 'application/ld+json';
    breadcrumbScript.textContent = JSON.stringify(breadcrumbSchema);
    document.head.appendChild(breadcrumbScript);
})();
