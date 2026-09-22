// Purpose: Show only the fields the selected integration platform actually uses.
// Used by: business_settings_api_add.html / business_settings_api_update.html.
// Notes: The platform -> field map is NOT defined here. It is rendered by
//        business.integration_fields into #api-field-config, so this file and the
//        staff modal cannot drift from each other or from the form.
(function () {
    var CONFIG = (function () {
        var el = document.getElementById('api-field-config');
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    })();

    if (!CONFIG) return;

    var PLATFORMS = CONFIG.platforms || {};
    var ALL_FIELDS = CONFIG.all_fields || [];
    var CONDITIONAL = CONFIG.conditional || {};

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

    // A field can depend on another field's value (the header/parameter name is
    // meaningless for Bearer, Basic and None). The rule lives in the server map.
    function applyConditionalFields(visibleFields) {
        Object.keys(CONDITIONAL).forEach(function (field) {
            var wrapper = getWrapper(field);
            if (!wrapper || visibleFields.indexOf(field) === -1) return;
            var rule = CONDITIONAL[field];
            var driver = document.getElementById('id_' + rule.field);
            if (!driver) return;
            var show = (rule.values || []).indexOf(driver.value) !== -1;
            wrapper.style.display = show ? '' : 'none';
        });
    }

    function resolveConfigKey(apiType) {
        // Shopify is the one platform whose field set depends on a second choice.
        if (apiType === 'shopify' && getShopifyMode() === 'custom_app') {
            return 'shopify_custom_app';
        }
        return apiType;
    }

    function applyFieldVisibility(apiType) {
        var isShopify = (apiType === 'shopify');
        var mode = isShopify ? getShopifyMode() : null;

        var spec = PLATFORMS[resolveConfigKey(apiType)] || PLATFORMS['custom'] || {};
        var showFields = spec.fields || [];
        var labelOverrides = spec.labels || {};
        var autofillValues = spec.autofill || {};

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
                var label = getLabelEl(field);
                if (label) {
                    if (!label.dataset.defaultLabel) {
                        label.dataset.defaultLabel = label.textContent;
                    }
                    label.textContent = labelOverrides[field] || label.dataset.defaultLabel;
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

        applyConditionalFields(showFields);
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

        applyFieldVisibility(select.value);

        select.addEventListener('change', function () {
            applyFieldVisibility(this.value);
        });

        // Any field another field depends on re-runs the conditional pass.
        Object.keys(CONDITIONAL).forEach(function (field) {
            var driver = document.getElementById('id_' + CONDITIONAL[field].field);
            if (driver) {
                driver.addEventListener('change', function () {
                    applyFieldVisibility(select.value);
                });
            }
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
