// JSON-LD Structured Data for Same Day Delivery Qatar Page
(function() {
    const schema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Same Day Delivery Qatar",
        "provider": {
            "@type": "LocalBusiness",
            "name": "EzzyDelivery"
        },
        "description": "Same day delivery in Qatar with pickup within 2 hours and delivery same day across Doha, Al Wakrah, Lusail.",
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
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
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://ezzydelivery.qa/"},
            {"@type": "ListItem", "position": 2, "name": "Same-Day Delivery Qatar", "item": "https://ezzydelivery.qa/same-day-delivery-qatar/"}
        ]
    };
    const bcScript = document.createElement('script');
    bcScript.type = 'application/ld+json';
    bcScript.textContent = JSON.stringify(breadcrumb);
    document.head.appendChild(bcScript);
})();
