// JSON-LD Structured Data for Global SEO (Local Business + Organization)
(function() {
    // Local Business Schema
    const localBusinessSchema = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": "EzzyDelivery",
        "image": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png",
        "@id": "https://ezzydelivery.qa",
        "url": "https://ezzydelivery.qa",
        "telephone": "+974-XXXX-XXXX",
        "priceRange": "$$",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Doha",
            "addressLocality": "Doha",
            "addressRegion": "Doha",
            "addressCountry": "QA"
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 25.286106,
            "longitude": 51.534817
        },
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                "opens": "08:00",
                "closes": "22:00"
            }
        ],
        "sameAs": [
            "https://facebook.com/ezzydeliveryqa",
            "https://instagram.com/ezzydeliveryqa",
            "https://twitter.com/ezzydeliveryqa"
        ],
        "areaServed": [
            {
                "@type": "City",
                "name": "Doha"
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
        "slogan": "Qatar's Trusted Delivery Partner",
        "description": "Professional delivery and courier services across Qatar. Specializing in same day delivery, e-commerce fulfillment, and COD services for businesses in Doha and nationwide."
    };

    // Organization Schema
    const organizationSchema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "EzzyDelivery",
        "alternateName": "Ezzy Delivery Qatar",
        "url": "https://ezzydelivery.qa",
        "logo": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png",
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": "+974-XXXX-XXXX",
            "contactType": "Customer Service",
            "email": "info@ezzydelivery.qa",
            "areaServed": "QA",
            "availableLanguage": ["English", "Arabic"]
        },
        "sameAs": [
            "https://facebook.com/ezzydeliveryqa",
            "https://instagram.com/ezzydeliveryqa"
        ]
    };

    // Create and inject Local Business schema
    const scriptLB = document.createElement('script');
    scriptLB.type = 'application/ld+json';
    scriptLB.textContent = JSON.stringify(localBusinessSchema);
    document.head.appendChild(scriptLB);

    // Create and inject Organization schema
    const scriptOrg = document.createElement('script');
    scriptOrg.type = 'application/ld+json';
    scriptOrg.textContent = JSON.stringify(organizationSchema);
    document.head.appendChild(scriptOrg);
})();
