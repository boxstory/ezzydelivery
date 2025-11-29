// JSON-LD Structured Data for Last Mile Delivery Qatar Page
(function() {
    // Service Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Last Mile Delivery Service",
        "provider": {
            "@type": "Organization",
            "name": "EzzyDelivery Qatar",
            "url": "https://ezzydelivery.qa"
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
                "name": "What is last mile delivery?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Last mile delivery is the final leg of shipping - from distribution center to customer's door. It's the most visible and critical part of the delivery experience."
                }
            },
            {
                "@type": "Question",
                "name": "How fast is your last mile delivery?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We offer same-day last mile delivery for orders placed before 2 PM in Doha area. Other areas in Qatar receive next-day delivery."
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
})();
