// JSON-LD Structured Data for Logistics Services Qatar Page
(function() {
    // ProfessionalService Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "ProfessionalService",
        "name": "EzzyDelivery Logistics Services Qatar",
        "image": "https://ezzydelivery.qa/static/webpages/img/ezzy-logo.png",
        "url": "https://ezzydelivery.qa/logistics-services-qatar/",
        "telephone": "+974-6645-1589",
        "priceRange": "$$",
        "address": {
            "@type": "PostalAddress",
            "addressCountry": "QA",
            "addressRegion": "Doha"
        },
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        }
    };

    // FAQPage Schema
    const faqSchema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What logistics services do you offer in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We offer comprehensive logistics including transportation & delivery, warehousing, order fulfillment, last-mile delivery, reverse logistics, and supply chain management across Qatar."
                }
            },
            {
                "@type": "Question",
                "name": "Do you provide warehousing facilities?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes! We have secure warehousing facilities in strategic Doha location with inventory management, climate control, and flexible storage options."
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
            {"@type": "ListItem", "position": 2, "name": "Logistics Services Qatar", "item": "https://ezzydelivery.qa/logistics-services-qatar/"}
        ]
    };
    const bcScript = document.createElement('script');
    bcScript.type = 'application/ld+json';
    bcScript.textContent = JSON.stringify(breadcrumb);
    document.head.appendChild(bcScript);
})();
