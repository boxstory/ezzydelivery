// JSON-LD Structured Data for Online Store Delivery Qatar Page
(function() {
    // Service Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Online Store Delivery Service",
        "provider": {
            "@type": "Organization",
            "name": "EzzyDelivery Qatar",
            "url": "https://ezzydelivery.qa"
        },
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        },
        "offers": {
            "@type": "Offer",
            "priceSpecification": {
                "@type": "PriceSpecification",
                "price": "8",
                "priceCurrency": "QAR"
            }
        }
    };

    // FAQPage Schema
    const faqSchema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "How do I start using delivery services for my online store?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Sign up for free on our platform, complete your business verification, and connect your online store via API or manually add orders. You can start shipping within 24 hours."
                }
            },
            {
                "@type": "Question",
                "name": "How does COD collection work?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Our drivers collect cash from customers upon delivery. We remit collected amounts to your bank account daily (next business day)."
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
