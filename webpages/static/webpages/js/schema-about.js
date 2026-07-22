/**
 * Schema.org Organization Markup for About Page
 * Provides structured data about EzzyDelivery business for search engines
 */

const organizationSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "EzzyDelivery",
  "legalName": "EzzyDelivery Qatar",
  "url": "https://ezzydelivery.qa",
  "logo": "https://ezzydelivery.qa/static/webpages/img/logo.png",
  "foundingDate": "2017",
  "description": "Professional delivery and logistics services in Qatar. Same-day delivery, courier services, e-commerce fulfillment, and 3PL solutions across Doha, Al Wakrah, Lusail, and all Qatar.",

  "address": {
    "@type": "PostalAddress",
    "addressLocality": "Doha",
    "addressCountry": "QA",
    "addressRegion": "Doha"
  },

  "contactPoint": [{
    "@type": "ContactPoint",
    "telephone": "+974-66451589",
    "contactType": "customer service",
    "areaServed": "QA",
    "availableLanguage": ["en", "ar"]
  }, {
    "@type": "ContactPoint",
    "telephone": "+974-66451589",
    "contactType": "sales",
    "areaServed": "QA",
    "availableLanguage": ["en", "ar"]
  }],

  "sameAs": [
    "https://www.facebook.com/ezzydeliveryqa",
    "https://www.instagram.com/ezzydeliveryqa",
    "https://www.linkedin.com/company/ezzydelivery",
    "https://twitter.com/ezzydeliveryqa"
  ],

  "areaServed": {
    "@type": "Country",
    "name": "Qatar"
  },

  "serviceType": [
    "Delivery Service",
    "Courier Service",
    "Same Day Delivery",
    "Express Delivery",
    "E-commerce Fulfillment",
    "Last Mile Delivery",
    "3PL Services",
    "Logistics Services",
    "COD Service",
    "Warehousing"
  ],

  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.8",
    "reviewCount": "500",
    "bestRating": "5",
    "worstRating": "1"
  },

  "numberOfEmployees": {
    "@type": "QuantitativeValue",
    "value": "50"
  }
};

// LocalBusiness schema for enhanced local SEO
const localBusinessSchema = {
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "EzzyDelivery",
  "image": "https://ezzydelivery.qa/static/webpages/img/logo.png",
  "url": "https://ezzydelivery.qa",
  "@id": "https://ezzydelivery.qa",
  "telephone": "+974-66451589",
  "priceRange": "QAR 8 - QAR 50",

  "address": {
    "@type": "PostalAddress",
    "streetAddress": "",
    "addressLocality": "Doha",
    "addressRegion": "Doha",
    "addressCountry": "QA"
  },

  "geo": {
    "@type": "GeoCoordinates",
    "latitude": 25.2854,
    "longitude": 51.5310
  },

  "openingHoursSpecification": [{
    "@type": "OpeningHoursSpecification",
    "dayOfWeek": [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday"
    ],
    "opens": "08:00",
    "closes": "22:00"
  }],

  "sameAs": [
    "https://www.facebook.com/ezzydeliveryqa",
    "https://www.instagram.com/ezzydeliveryqa"
  ]
};

// Inject schemas into page
function injectSchemas() {
  // Organization schema
  const orgScript = document.createElement('script');
  orgScript.type = 'application/ld+json';
  orgScript.text = JSON.stringify(organizationSchema);
  document.head.appendChild(orgScript);

  // LocalBusiness schema
  const localScript = document.createElement('script');
  localScript.type = 'application/ld+json';
  localScript.text = JSON.stringify(localBusinessSchema);
  document.head.appendChild(localScript);

  // BreadcrumbList
  const breadcrumb = {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      "itemListElement": [
          {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://ezzydelivery.qa/"},
          {"@type": "ListItem", "position": 2, "name": "About Us", "item": "https://ezzydelivery.qa/about/"}
      ]
  };
  const bcScript = document.createElement('script');
  bcScript.type = 'application/ld+json';
  bcScript.text = JSON.stringify(breadcrumb);
  document.head.appendChild(bcScript);
}

// Run on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectSchemas);
} else {
  injectSchemas();
}
