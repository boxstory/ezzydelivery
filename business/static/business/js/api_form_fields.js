// Show/hide API form fields based on selected platform type
(function () {
    // Fields grouped by platform
    const FIELD_CONFIG = {
        google_sheet: {
            show: ['site_api_url'],
            labels: { site_api_url: 'Google Sheet URL' },
            placeholders: { site_api_url: 'https://docs.google.com/spreadsheets/d/...' },
        },
        shopify: {
            show: ['api_access_token', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            labels: { site_api_url: 'Store URL (e.g. mystore.myshopify.com)' },
        },
        woocommerce: {
            show: ['api_key', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            labels: { site_api_url: 'Store URL (with https://)' },
        },
        tiktokshop: {
            show: ['api_key', 'api_secret', 'api_access_token', 'api_version', 'tiktok_shop_id', 'tiktok_shop_cipher', 'tiktok_refresh_token'],
        },
        magento: {
            show: ['api_access_token', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
        },
        opencart: {
            show: ['api_key', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
        },
        prestashop: {
            show: ['api_key', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
        },
        bigcommerce: {
            show: ['api_key', 'api_access_token', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
        },
        custom: {
            show: ['api_key', 'api_secret', 'api_access_token', 'api_version', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
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
