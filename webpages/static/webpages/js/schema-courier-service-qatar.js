// JSON-LD Structured Data for Courier Service Qatar Page
(function() {
    // LocalBusiness Schema
    const businessSchema = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": "EzzyDelivery Qatar Courier Service",
        "image": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png",
        "@id": "https://ezzydelivery.qa/courier-service-qatar/",
        "url": "https://ezzydelivery.qa/courier-service-qatar/",
        "telephone": "+974-6660-9347",
        "priceRange": "QAR 8 - QAR 15",
        "address": {
            "@type": "PostalAddress",
            "addressCountry": "QA",
            "addressRegion": "Doha"
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 25.2854,
            "longitude": 51.5310
        },
        "openingHoursSpecification": {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "opens": "00:00",
            "closes": "23:59"
        },
        "sameAs": [
            "https://www.instagram.com/ezzydelivery.qa"
        ]
    };

    // FAQPage Schema
    const faqSchema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What courier services do you offer in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We offer complete courier solutions including express delivery, standard parcel service, document courier, e-commerce logistics, scheduled pickups, and B2B courier services across all Qatar."
                }
            },
            {
                "@type": "Question",
                "name": "How much does courier service cost in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Standard courier service starts from QAR 8 per delivery within Doha. Express same-day courier is QAR 15. Final pricing depends on package size, weight, and delivery distance."
                }
            }
        ]
    };

    // Inject LocalBusiness Schema
    const businessScript = document.createElement('script');
    businessScript.type = 'application/ld+json';
    businessScript.textContent = JSON.stringify(businessSchema);
    document.head.appendChild(businessScript);

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
            {"@type": "ListItem", "position": 2, "name": "Courier Service Qatar", "item": "https://ezzydelivery.qa/courier-service-qatar/"}
        ]
    };
    const bcScript = document.createElement('script');
    bcScript.type = 'application/ld+json';
    bcScript.textContent = JSON.stringify(breadcrumb);
    document.head.appendChild(bcScript);
})();
