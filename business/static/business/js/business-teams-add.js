// Purpose: Live user lookup for the add-team-member form — auto-fills the
//          display name/email and shows a status tick when a user is matched.
// Used by: business/templates/business/parts/business_teams_add.html

(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.getElementById("client_teams_add_form_main");
        if (!form) return;

        var lookupUrl = form.dataset.lookupUrl;
        var idInput = document.getElementById("id_user_identifier");
        var nameInput = document.getElementById("id_team_name");
        var emailInput = document.getElementById("id_team_email");
        if (!lookupUrl || !idInput) return;

        // Status indicator shown beside the identifier field.
        var status = document.createElement("div");
        status.className = "bta__lookup-status";
        idInput.insertAdjacentElement("afterend", status);

        // Remove any server-rendered validation errors (from a failed submit)
        // for the identifier field once the user starts editing it again.
        var idWrap = idInput.closest(".mb-3");
        function clearServerErrors() {
            if (!idWrap) return;
            idWrap.querySelectorAll(".text-danger").forEach(function (el) {
                el.remove();
            });
        }

        // Track auto-filled values so we don't clobber what the user typed.
        var lastAutoName = "";
        var lastAutoEmail = "";
        if (nameInput) {
            nameInput.addEventListener("input", function () {
                if (nameInput.value !== lastAutoName) lastAutoName = null;
            });
        }

        function setStatus(state, text) {
            status.className = "bta__lookup-status bta__lookup-status--" + state;
            var icon = {
                loading: "fa-spinner fa-spin",
                ok: "fa-circle-check",
                warn: "fa-triangle-exclamation",
                error: "fa-circle-xmark"
            }[state] || "";
            status.innerHTML = icon
                ? '<i class="fa-solid ' + icon + '"></i><span>' + text + "</span>"
                : "";
        }

        function applyFill(data) {
            if (nameInput && data.name && (!nameInput.value || nameInput.value === lastAutoName)) {
                nameInput.value = data.name;
                lastAutoName = data.name;
            }
            if (emailInput && data.email && (!emailInput.value || emailInput.value === lastAutoEmail)) {
                emailInput.value = data.email;
                lastAutoEmail = data.email;
            }
        }

        // Clear values we previously auto-filled (leave anything the user typed).
        function clearFill() {
            if (nameInput && lastAutoName && nameInput.value === lastAutoName) {
                nameInput.value = "";
                lastAutoName = "";
            }
            if (emailInput && lastAutoEmail && emailInput.value === lastAutoEmail) {
                emailInput.value = "";
                lastAutoEmail = "";
            }
        }

        var timer = null;
        var controller = null;

        function lookup() {
            var value = idInput.value.trim();
            if (value.length < 3) {
                clearFill();
                setStatus("", "");
                return;
            }
            setStatus("loading", "Checking…");

            if (controller) controller.abort();
            controller = new AbortController();

            fetch(lookupUrl + "?identifier=" + encodeURIComponent(value), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                signal: controller.signal
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.found) {
                        clearFill();
                        setStatus("error", data.error || "No matching user found.");
                        return;
                    }
                    applyFill(data);
                    if (data.can_add) {
                        setStatus("ok", "Found: " + data.name);
                    } else {
                        setStatus("warn", (data.name ? data.name + " — " : "") + (data.reason || "Cannot be added."));
                    }
                })
                .catch(function (err) {
                    if (err.name !== "AbortError") setStatus("error", "Lookup failed. Try again.");
                });
        }

        idInput.addEventListener("input", function () {
            clearServerErrors();
            clearTimeout(timer);
            timer = setTimeout(lookup, 450);
        });

        // Run once on load if pre-filled (e.g. coming from a join request).
        if (idInput.value.trim()) lookup();

        // --- Role → default permissions auto-tick ---------------------------
        var roleSelect = document.getElementById("id_team_role");
        var rolePermsEl = document.getElementById("role-permissions-data");
        if (roleSelect && rolePermsEl) {
            var rolePerms = {};
            try {
                rolePerms = JSON.parse(rolePermsEl.textContent) || {};
            } catch (e) {
                rolePerms = {};
            }

            // Defaults applied for the currently selected role, so switching
            // roles removes the old role's defaults but keeps manual extras.
            var prevDefaults = [];

            function applyRoleDefaults() {
                var defaults = rolePerms[roleSelect.value] || [];
                // Uncheck the previous role's defaults that aren't in the new set.
                prevDefaults.forEach(function (code) {
                    if (defaults.indexOf(code) === -1) {
                        var box = document.getElementById("perm_" + code);
                        if (box) box.checked = false;
                    }
                });
                // Check the new role's defaults.
                defaults.forEach(function (code) {
                    var box = document.getElementById("perm_" + code);
                    if (box) box.checked = true;
                });
                prevDefaults = defaults.slice();
            }

            roleSelect.addEventListener("change", applyRoleDefaults);
            // Seed on load so the initial role's permissions are reflected.
            applyRoleDefaults();
        }
    });
})();
