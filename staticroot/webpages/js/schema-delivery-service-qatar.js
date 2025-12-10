// JSON-LD Structured Data for Delivery Service Qatar Page
(function() {
    // FAQPage Schema
    const faqSchema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What is the cost of delivery service in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Our delivery rates in Qatar start from QAR 10-15 for standard deliveries within Doha. Pricing varies based on distance, package size, and service type. We offer significant volume discounts for businesses with regular shipments."
                }
            },
            {
                "@type": "Question",
                "name": "How quickly can you deliver in Qatar?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "We offer same-day delivery across Qatar with pickup within 2 hours of order placement. For express service in Doha, we can deliver within 4-6 hours."
                }
            },
            {
                "@type": "Question",
                "name": "Do you offer COD (Cash on Delivery) service?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes! We provide comprehensive COD service across Qatar with fast settlement. Our COD fee is only 2% with payment settlement within 3-5 business days."
                }
            }
        ]
    };

    // Service Schema
    const serviceSchema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": "Delivery Service in Qatar",
        "provider": {
            "@type": "LocalBusiness",
            "name": "EzzyDelivery",
            "telephone": "+974-XXXX-XXXX"
        },
        "areaServed": {
            "@type": "Country",
            "name": "Qatar"
        },
        "description": "Professional delivery service in Qatar with same-day delivery, COD, and real-time tracking across Doha, Al Wakrah, Lusail.",
        "offers": {
            "@type": "AggregateOffer",
            "lowPrice": "10",
            "highPrice": "50",
            "priceCurrency": "QAR"
        }
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
})();
