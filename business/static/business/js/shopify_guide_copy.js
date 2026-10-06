// Purpose: Wire the Copy buttons inside the Shopify setup guide (App URL, redirect URI, scopes).
// Used by: business/parts/_shopify_setup_guide.html, which loads it on the API list / add / update pages.
// Notes: Lives apart from api_form_fields.js on purpose — that file early-returns when the add/update
//        form is absent, which left these buttons dead on the API list page.
(function () {
    // Each button reads the <code> block it is paired with, so the merchant
    // copies the exact string Shopify compares character for character.
    var PAIRS = [
        ['client_api_shopify_copy_redirect', 'client_api_shopify_redirect_uri'],
        ['client_api_shopify_copy_app_url', 'client_api_shopify_app_url'],
        ['client_api_shopify_copy_scopes', 'client_api_shopify_scopes'],
    ];

    document.addEventListener('DOMContentLoaded', function () {
        PAIRS.forEach(function (pair) {
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
