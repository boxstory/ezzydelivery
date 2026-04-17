// Show/hide API form fields based on selected platform type
(function () {
    // Fields grouped by platform with auto-fill URLs
    const FIELD_CONFIG = {
        google_sheet: {
            show: ['site_api_url'],
            labels: { site_api_url: 'Google Sheet URL' },
            placeholders: { site_api_url: 'https://docs.google.com/spreadsheets/d/...' },
            autofill: { site_api_url: '' },
        },
        shopify: {
            show: ['api_access_token', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            labels: { site_api_url: 'Store URL (e.g. mystore.myshopify.com)' },
            autofill: {
                order_api_endpoint: '/admin/api/2024-01/orders.json',
                product_api_endpoint: '/admin/api/2024-01/products.json',
                site_contry: 'Qatar',
            },
        },
        woocommerce: {
            show: ['api_key', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            labels: { site_api_url: 'Store URL (with https://)' },
            autofill: {
                order_api_endpoint: '/wp-json/wc/v3/orders',
                product_api_endpoint: '/wp-json/wc/v3/products',
                site_contry: 'Qatar',
            },
        },
        tiktokshop: {
            show: ['api_key', 'api_secret', 'api_access_token', 'api_version', 'tiktok_shop_id', 'tiktok_shop_cipher', 'tiktok_refresh_token'],
            autofill: { api_version: '202309' },
        },
        magento: {
            show: ['api_access_token', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            autofill: {
                order_api_endpoint: '/rest/V1/orders',
                product_api_endpoint: '/rest/V1/products',
                site_contry: 'Qatar',
            },
        },
        opencart: {
            show: ['api_key', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            autofill: {
                order_api_endpoint: '/index.php?route=api/order',
                product_api_endpoint: '/index.php?route=api/product',
                site_contry: 'Qatar',
            },
        },
        prestashop: {
            show: ['api_key', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            autofill: {
                order_api_endpoint: '/api/orders',
                product_api_endpoint: '/api/products',
                site_contry: 'Qatar',
            },
        },
        bigcommerce: {
            show: ['api_key', 'api_access_token', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            autofill: {
                order_api_endpoint: '/stores/api/v3/orders',
                product_api_endpoint: '/stores/api/v3/catalog/products',
                site_contry: 'Qatar',
            },
        },
        custom: {
            show: ['api_key', 'api_secret', 'api_access_token', 'api_version', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            autofill: { site_contry: 'Qatar' },
        },
    };

    const ALL_FIELDS = ['api_key', 'api_secret', 'api_access_token', 'api_version',
                        'site_api_url', 'order_api_endpoint', 'product_api_endpoint',
                        'site_contry', 'tiktok_shop_id', 'tiktok_shop_cipher', 'tiktok_refresh_token'];

    // Default labels from the form
    const DEFAULT_LABELS = {
        site_api_url: 'Site URL (with https://)',
    };

    function getWrapper(fieldName) {
        return document.getElementById('div_id_' + fieldName);
    }

    function getLabelEl(fieldName) {
        const wrapper = getWrapper(fieldName);
        return wrapper ? wrapper.querySelector('label') : null;
    }

    function applyFieldVisibility(apiType) {
        const config = FIELD_CONFIG[apiType] || FIELD_CONFIG['custom'];
        const showFields = config.show || [];
        const labelOverrides = config.labels || {};
        const autofillValues = config.autofill || {};

        ALL_FIELDS.forEach(function (field) {
            const wrapper = getWrapper(field);
            if (!wrapper) return;
            if (showFields.includes(field)) {
                wrapper.style.display = '';
                // Restore/override label
                const label = getLabelEl(field);
                if (label) {
                    label.textContent = labelOverrides[field] || DEFAULT_LABELS[field] || label.dataset.defaultLabel || label.textContent;
                    if (!label.dataset.defaultLabel) {
                        label.dataset.defaultLabel = label.textContent;
                    }
                }
                // Auto-fill known endpoints (only if empty)
                const input = wrapper.querySelector('input');
                if (input && autofillValues[field] && !input.value) {
                    input.value = autofillValues[field];
                }
            } else {
                wrapper.style.display = 'none';
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        const select = document.getElementById('api_type_select');
        if (!select) return;

        // Store default labels
        ALL_FIELDS.forEach(function (field) {
            const label = getLabelEl(field);
            if (label && !label.dataset.defaultLabel) {
                label.dataset.defaultLabel = label.textContent;
            }
        });

        // Apply on load
        applyFieldVisibility(select.value);

        // Apply on change
        select.addEventListener('change', function () {
            applyFieldVisibility(this.value);
        });
    });
})();
