// Show/hide API form fields based on selected platform type
(function () {
    // Fields grouped by platform with auto-fill URLs
    var FIELD_CONFIG = {
        google_sheet: {
            show: ['site_api_url'],
            labels: { site_api_url: 'Google Sheet URL' },
            placeholders: { site_api_url: 'https://docs.google.com/spreadsheets/d/...' },
            autofill: { site_api_url: '' },
        },
        // Shopify has two mutually-exclusive setup paths. Showing all three
        // credential boxes at once is what let merchants save a Client ID +
        // Secret, never run OAuth, and get a 401 with no token. Each mode now
        // shows only the fields that mode actually needs.
        shopify: {
            show: ['api_key', 'api_secret', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            labels: {
                api_key: 'Client ID (Shopify Custom App API key)',
                api_secret: 'Client Secret (Shopify Custom App API secret key)',
                api_access_token: 'Admin API Access Token (starts with shpat_)',
                site_api_url: 'Store URL (e.g. mystore.myshopify.com)',
            },
            autofill: {
                order_api_endpoint: '/admin/api/2024-01/orders.json',
                product_api_endpoint: '/admin/api/2024-01/products.json',
                site_contry: 'Qatar',
            },
        },
        shopify_custom_app: {
            show: ['api_access_token', 'site_api_url', 'order_api_endpoint', 'product_api_endpoint', 'site_contry'],
            labels: {
                api_access_token: 'Admin API Access Token (starts with shpat_)',
                site_api_url: 'Store URL (e.g. mystore.myshopify.com)',
            },
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

    var ALL_FIELDS = ['api_key', 'api_secret', 'api_access_token', 'api_version',
                        'site_api_url', 'order_api_endpoint', 'product_api_endpoint',
                        'site_contry', 'tiktok_shop_id', 'tiktok_shop_cipher', 'tiktok_refresh_token'];

    // Default labels from the form
    var DEFAULT_LABELS = {
        site_api_url: 'Site URL (with https://)',
    };

    function getWrapper(fieldName) {
        return document.getElementById('div_id_' + fieldName);
    }

    function getLabelEl(fieldName) {
        var wrapper = getWrapper(fieldName);
        return wrapper ? wrapper.querySelector('label') : null;
    }

    function getShopifyMode() {
        var checked = document.querySelector('input[name="shopify_setup_mode"]:checked');
        return checked ? checked.value : 'oauth';
    }

    function setDisplay(id, visible) {
        var el = document.getElementById(id);
        if (el) el.style.display = visible ? '' : 'none';
    }

    // Marks which of the two always-visible guide blocks matches the selected
    // setup mode, so the other reads as reference rather than instruction.
    function setGuideActive(id, active) {
        var el = document.getElementById(id);
        if (!el) return;
        el.classList.toggle('bapi__guide--active', !!active);
        el.classList.toggle('bapi__guide--muted', !active);
    }

    function applyFieldVisibility(apiType) {
        var isShopify = (apiType === 'shopify');
        var mode = isShopify ? getShopifyMode() : null;

        // Shopify resolves to a per-mode field set; every other platform keys
        // straight off apiType.
        var configKey = apiType;
        if (isShopify && mode === 'custom_app') {
            configKey = 'shopify_custom_app';
        }

        var config = FIELD_CONFIG[configKey] || FIELD_CONFIG['custom'];
        var showFields = config.show || [];
        var labelOverrides = config.labels || {};
        var autofillValues = config.autofill || {};

        // The mode radio itself is Shopify-only.
        var modeWrapper = getWrapper('shopify_setup_mode');
        if (modeWrapper) modeWrapper.style.display = isShopify ? '' : 'none';

        setDisplay('client_api_shopify_setup_help', isShopify);
        // Both paths stay documented whichever mode is selected — a merchant
        // cannot choose between Custom App and OAuth if only the mode they are
        // already on is described. The selected one is marked as active.
        setDisplay('client_api_shopify_guide_oauth', isShopify);
        setDisplay('client_api_shopify_guide_custom_app', isShopify);
        setGuideActive('client_api_shopify_guide_oauth', isShopify && mode === 'oauth');
        setGuideActive('client_api_shopify_guide_custom_app', isShopify && mode === 'custom_app');

        // OAuth is the only path with a second step, so the connect affordances
        // (submit label on add, button on edit) only make sense in that mode.
        setDisplay('client_api_shopify_oauth_connect', isShopify && mode === 'oauth');
        var submitLabel = document.getElementById('client_api_submit_label');
        if (submitLabel && submitLabel.dataset.defaultText) {
            submitLabel.textContent = (isShopify && mode === 'oauth')
                ? 'Save & Connect to Shopify'
                : submitLabel.dataset.defaultText;
        }

        ALL_FIELDS.forEach(function (field) {
            var wrapper = getWrapper(field);
            if (!wrapper) return;
            if (showFields.indexOf(field) !== -1) {
                wrapper.style.display = '';
                // Restore/override label
                var label = getLabelEl(field);
                if (label) {
                    label.textContent = labelOverrides[field] || DEFAULT_LABELS[field] || label.dataset.defaultLabel || label.textContent;
                    if (!label.dataset.defaultLabel) {
                        label.dataset.defaultLabel = label.textContent;
                    }
                }
                // Auto-fill known endpoints (only if empty)
                var input = wrapper.querySelector('input');
                if (input && autofillValues[field] && !input.value) {
                    input.value = autofillValues[field];
                }
            } else {
                wrapper.style.display = 'none';
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var select = document.getElementById('api_type_select');
        if (!select) return;

        // Store default labels
        ALL_FIELDS.forEach(function (field) {
            var label = getLabelEl(field);
            if (label && !label.dataset.defaultLabel) {
                label.dataset.defaultLabel = label.textContent;
            }
        });

        // Remember the submit button's own wording so leaving Shopify OAuth
        // mode restores it instead of stranding "Save & Connect to Shopify".
        var submitLabel = document.getElementById('client_api_submit_label');
        if (submitLabel && !submitLabel.dataset.defaultText) {
            submitLabel.dataset.defaultText = submitLabel.textContent.trim();
        }

        // Apply on load
        applyFieldVisibility(select.value);

        // Apply on change
        select.addEventListener('change', function () {
            applyFieldVisibility(this.value);
        });

        // Switching setup mode re-resolves the Shopify field set.
        Array.prototype.forEach.call(
            document.querySelectorAll('input[name="shopify_setup_mode"]'),
            function (radio) {
                radio.addEventListener('change', function () {
                    applyFieldVisibility(select.value);
                });
            }
        );

        // Copy-to-clipboard for the redirect URL merchants must whitelist in
        // Shopify. It has to match byte-for-byte, so typing it is the failure mode.
        // Each copy button reads the <code> block it is paired with.
        [
            ['client_api_shopify_copy_redirect', 'client_api_shopify_redirect_uri'],
            ['client_api_shopify_copy_app_url', 'client_api_shopify_app_url'],
        ].forEach(function (pair) {
            var copyBtn = document.getElementById(pair[0]);
            if (!copyBtn) return;
            copyBtn.addEventListener('click', function () {
                var target = document.getElementById(pair[1]);
                if (!target) return;
                var text = target.textContent.trim();
                var done = function () {
                    var original = copyBtn.textContent;
                    copyBtn.textContent = 'Copied';
                    setTimeout(function () { copyBtn.textContent = original; }, 1500);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(done, function () {});
                }
            });
        });
    });
})();
