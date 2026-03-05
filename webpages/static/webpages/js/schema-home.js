// JSON-LD Structured Data for Home Page SEO
(function() {
    const schema = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": "EzzyDelivery",
        "description": "Qatar's leading delivery and courier service providing same day delivery in Doha, Al Wakrah, Lusail. E-commerce fulfillment, COD services, and real-time tracking.",
        "url": "https://ezzydelivery.qa",
        "telephone": "+974-6645-1589",
        "priceRange": "$$",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Doha",
            "addressRegion": "Doha",
            "addressCountry": "QA"
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 25.286106,
            "longitude": 51.534817
        },
        "areaServed": [
            {"@type": "City", "name": "Doha"},
            {"@type": "City", "name": "Al Wakrah"},
            {"@type": "City", "name": "Al Rayyan"},
            {"@type": "City", "name": "Lusail"}
        ],
        "serviceType": [
            "Delivery Service Qatar",
            "Courier Service Doha",
            "Same Day Delivery",
            "Express Delivery Qatar",
            "COD Service",
            "E-commerce Fulfillment",
            "Last Mile Delivery Qatar"
        ],
        "openingHoursSpecification": {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "opens": "08:00",
            "closes": "22:00"
        }
    };

    // Create and inject script tag
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(schema);
    document.head.appendChild(script);

    // BreadcrumbList
    const breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://ezzydelivery.qa/"}
        ]
    };
    const bcScript = document.createElement('script');
    bcScript.type = 'application/ld+json';
    bcScript.textContent = JSON.stringify(breadcrumb);
    document.head.appendChild(bcScript);
})();
