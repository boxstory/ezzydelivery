/*
 * Purpose: Real-time password strength meter, requirements checklist, submit gating and show/hide toggles.
 * Used by: templates/account/password_change.html, templates/account/signup.html,
 *          templates/account/password_reset_from_key.html, core/templates/accounts/password_reset_confirm.html
 *          (markup + styles: account/css/password-strength.css)
 * Notes: Client-side feedback only — Django's validators stay authoritative and the gate fails open,
 *        so a script error can never lock someone out of setting a password.
 *
 * Widget attributes:
 *   data-pwd-strength                 marks the block
 *   data-pwd-input="<input id>"       the password field it watches
 *   data-pwd-gate="<button id>"       optional: button held disabled until every rule passes
 *   data-pwd-match="<input id>"       optional: adds a "passwords match" rule against a confirm field
 *   data-pwd-attrs="a|b|c"            personal info for the similarity rule (rendered server-side)
 *   data-pwd-watch="id1,id2"          optional: live form fields that also feed the similarity rule
 *
 * Checklist attributes:
 *   data-pwd-rule="<name>"            the rule the row reflects
 *   data-pwd-when="fail"              row stays hidden until the typed password breaks that rule
 *   data-pwd-when="confirm"           row stays hidden until the confirm field has a value
 */
(function () {
    'use strict';

    var LEVELS = ['', 'Weak', 'Fair', 'Good', 'Strong'];
    var LEVEL_MODIFIERS = [
        '',
        'auth__pwd-strength--weak',
        'auth__pwd-strength--fair',
        'auth__pwd-strength--good',
        'auth__pwd-strength--strong'
    ];

    /* The rules shown in the checklist — all of them must pass before submit is allowed. */
    var GATE_RULES = ['length', 'repeats', 'predictable', 'similarity', 'case', 'number', 'symbol'];

    /* Three or more identical characters in a row: aaa, 111, !!! */
    var RUN_OF_THREE = /(.)\1{2,}/;
    /* A 2-4 character unit repeated back to back: abab, 1212, Ab12Ab12 */
    var REPEATED_UNIT = /(.{2,4})\1+/;

    /* Shortlist only — django.contrib.auth's 20k list is the real gate on the server. */
    var COMMON_PASSWORDS = [
        'password', 'password1', 'password123', 'passw0rd', '123456', '1234567',
        '12345678', '123456789', '1234567890', 'qwerty', 'qwerty123', 'abc123',
        'monkey', 'letmein', 'trustno1', 'dragon', 'baseball', 'football',
        'iloveyou', 'master', 'sunshine', 'shadow', 'superman', 'qazwsx',
        'michael', 'welcome', 'welcome1', 'jesus', 'admin', 'admin123',
        'login', 'starwars', 'whatever', 'freedom', 'princess', 'ninja',
        'qatar123', 'changeme', 'secret', 'test1234'
    ];

    /*
     * Word stems that make a password guessable once you strip the decoration people add
     * around them — a capital at the front, a year and a "!" at the end. "Qatar2026!" ticks
     * every composition box and is still one of the first guesses any cracker makes.
     */
    var BASE_WORDS = COMMON_PASSWORDS.concat([
        /* local + brand vocabulary */
        'qatar', 'doha', 'lusail', 'wakrah', 'wakra', 'alkhor', 'khor', 'rayyan', 'mesaieed',
        'dukhan', 'msheireb', 'katara', 'corniche', 'souq', 'waqif', 'pearl', 'aspire',
        'sealine', 'zubarah', 'ummsalal', 'sadd', 'thumama', 'ezzy', 'ezzydelivery',
        'delivery', 'deliver', 'courier', 'driver', 'logistics', 'shipping', 'cargo',
        'company', 'business', 'office', 'account', 'user', 'test', 'demo', 'guest',
        /* dates + seasons */
        'january', 'february', 'march', 'april', 'june', 'july', 'august', 'september',
        'october', 'november', 'december', 'summer', 'winter', 'spring', 'autumn',
        /* names that show up constantly */
        'mohammed', 'muhammed', 'mohamed', 'ahmed', 'ahmad', 'hassan', 'hussain', 'khalid',
        'abdullah', 'abdulla', 'ibrahim', 'yousef', 'yusuf', 'omar', 'ali', 'saeed', 'salem',
        'fatima', 'maryam', 'aisha', 'noor', 'sara', 'layla', 'john', 'david', 'sarah',
        /* everyday filler */
        'hello', 'love', 'money', 'happy', 'family', 'home', 'god', 'allah', 'star',
        'football', 'cricket', 'soccer', 'liverpool', 'barcelona', 'chelsea', 'arsenal'
    ]);

    var KEYBOARD_ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm', '1234567890'];

    /*
     * Starts as the curated list above so the rules work with no network at all, then grows
     * by ~9k stems once Django's own common-password list loads (see loadWordList).
     */
    var WORDS = {};
    for (var seed = 0; seed < BASE_WORDS.length; seed++) {
        WORDS[BASE_WORDS[seed]] = true;
    }

    /* Undo the usual letter-for-symbol swaps so "P@ssw0rd" reads as "password". */
    function normalizeLeet(value) {
        return value.toLowerCase()
            .replace(/[@4]/g, 'a')
            .replace(/0/g, 'o')
            .replace(/[1!|]/g, 'i')
            .replace(/3/g, 'e')
            .replace(/[$5]/g, 's')
            .replace(/7/g, 't')
            .replace(/8/g, 'b');
    }

    /* Four or more steps along the alphabet, the number line, or a keyboard row. */
    function hasSequence(password) {
        var lower = password.toLowerCase();

        var run = 1;
        var direction = 0;
        for (var i = 1; i < lower.length; i++) {
            var step = lower.charCodeAt(i) - lower.charCodeAt(i - 1);
            if (step === 1 || step === -1) {
                run = (step === direction) ? run + 1 : 2;
                direction = step;
                if (run >= 4) { return true; }
            } else {
                run = 1;
                direction = 0;
            }
        }

        for (var r = 0; r < KEYBOARD_ROWS.length; r++) {
            var row = KEYBOARD_ROWS[r];
            var reversed = row.split('').reverse().join('');
            for (var s = 0; s + 4 <= row.length; s++) {
                if (lower.indexOf(row.substr(s, 4)) > -1) { return true; }
                if (lower.indexOf(reversed.substr(s, 4)) > -1) { return true; }
            }
        }
        return false;
    }

    /*
     * True when the password is a known word wearing a costume: strip the digits and symbols
     * and what's left is a base word, give or take a couple of characters.
     */
    function isPredictable(password) {
        if (!password) { return false; }
        if (hasSequence(password)) { return true; }

        var cores = [
            password.toLowerCase().replace(/[^a-z]/g, ''),
            normalizeLeet(password).replace(/[^a-z]/g, '')
        ];

        for (var c = 0; c < cores.length; c++) {
            if (isKnownWord(cores[c])) { return true; }
        }
        return false;
    }

    /*
     * A word with at most a couple of letters bolted on is still that word. Trimming the
     * core and looking it up beats scanning the list — it stays O(1) as the list grows to 9k.
     */
    function isKnownWord(core) {
        for (var trim = 0; trim <= 2; trim++) {
            var candidate = trim ? core.slice(0, -trim) : core;
            if (candidate.length >= 3 && WORDS[candidate]) { return true; }
        }
        return false;
    }

    function bigrams(value) {
        var out = [];
        for (var i = 0; i < value.length - 1; i++) {
            out.push(value.substr(i, 2));
        }
        return out;
    }

    /* Dice coefficient — stand-in for difflib.SequenceMatcher used by Django's similarity validator. */
    function similarity(a, b) {
        if (a === b) { return 1; }
        if (a.length < 2 || b.length < 2) { return 0; }

        var left = bigrams(a);
        var right = bigrams(b);
        var pool = right.slice();
        var hits = 0;

        for (var i = 0; i < left.length; i++) {
            var found = pool.indexOf(left[i]);
            if (found > -1) {
                hits++;
                pool.splice(found, 1);
            }
        }
        return (2 * hits) / (left.length + right.length);
    }

    function isSimilarToUser(password, attributes) {
        var value = password.toLowerCase();
        if (!value) { return false; }

        for (var i = 0; i < attributes.length; i++) {
            var raw = (attributes[i] || '').toLowerCase().trim();
            if (!raw) { continue; }

            var candidates = [raw].concat(raw.split(/[^\w]+/));
            for (var j = 0; j < candidates.length; j++) {
                var candidate = candidates[j];
                if (candidate.length < 3) { continue; }
                if (value.indexOf(candidate) > -1 || candidate.indexOf(value) > -1) { return true; }
                if (similarity(value, candidate) >= 0.7) { return true; }
            }
        }
        return false;
    }

    function isCommon(password) {
        return COMMON_PASSWORDS.indexOf(password.toLowerCase()) > -1;
    }

    function evaluate(password, attributes, confirmValue) {
        var hasLower = /[a-z]/.test(password);
        var hasUpper = /[A-Z]/.test(password);
        var hasNumber = /\d/.test(password);
        var hasSymbol = /[^A-Za-z0-9]/.test(password);

        var rules = {
            /* Enforced by Django's AUTH_PASSWORD_VALIDATORS */
            length: password.length >= 8,
            similarity: password.length > 0 && !isSimilarToUser(password, attributes),
            common: password.length > 0 && !isCommon(password),
            numeric: password.length > 0 && !/^\d+$/.test(password),
            /* House rules — enforced here, not by the server */
            predictable: password.length > 0 && !isPredictable(password),
            repeats: password.length > 0
                && !RUN_OF_THREE.test(password)
                && !REPEATED_UNIT.test(password),
            case: hasLower && hasUpper,
            number: hasNumber,
            symbol: hasSymbol
        };

        var gate = GATE_RULES.slice();
        if (confirmValue !== null) {
            rules.match = password.length > 0 && password === confirmValue;
            gate.push('match');
        }

        var unmet = [];
        for (var g = 0; g < gate.length; g++) {
            if (!rules[gate[g]]) { unmet.push(gate[g]); }
        }

        /*
         * The meter climbs in steps as the three composition rules land. Good is only
         * reachable once all three hold — so a password with no symbol never reads "Good".
         */
        var composition = (rules['case'] ? 1 : 0) + (rules.number ? 1 : 0) + (rules.symbol ? 1 : 0);
        var base = rules.length && rules.similarity;

        var score = 0;
        if (password.length) {
            if (!rules.repeats || !rules.predictable) {
                /* Padding with aaa/abab, or dressing up a dictionary word, adds no real strength. */
                score = 1;
            } else if (!base || composition <= 1) {
                score = 1;
            } else if (composition === 2) {
                score = 2;
            } else {
                score = password.length >= 12 ? 4 : 3;
            }

            /* Anything the server would reject outright can never read above Weak. */
            if (!rules.common || !rules.numeric) { score = 1; }
        }

        return { score: score, rules: rules, unmet: unmet };
    }

    /* Static personal info from the server, plus any live form fields worth watching. */
    function attributesFor(config) {
        var attributes = (config.widget.getAttribute('data-pwd-attrs') || '').split('|');
        for (var i = 0; i < config.watched.length; i++) {
            attributes.push(config.watched[i].value);
        }
        return attributes;
    }

    function render(config) {
        var widget = config.widget;
        var password = config.input.value;
        var result = evaluate(
            password,
            attributesFor(config),
            config.confirm ? config.confirm.value : null
        );

        for (var i = 0; i < LEVEL_MODIFIERS.length; i++) {
            if (LEVEL_MODIFIERS[i]) { widget.classList.remove(LEVEL_MODIFIERS[i]); }
        }
        if (LEVEL_MODIFIERS[result.score]) { widget.classList.add(LEVEL_MODIFIERS[result.score]); }

        var segments = widget.querySelectorAll('.auth__pwd-seg');
        for (var s = 0; s < segments.length; s++) {
            segments[s].classList.toggle('auth__pwd-seg--on', s < result.score);
        }

        var meter = widget.querySelector('.auth__pwd-meter');
        if (meter) {
            meter.setAttribute('aria-valuenow', String(result.score));
            meter.setAttribute(
                'aria-valuetext',
                result.score ? LEVELS[result.score] + ' password' : 'No password entered'
            );
        }

        var level = widget.querySelector('[data-pwd-level]');
        if (level) {
            level.textContent = result.score ? LEVELS[result.score] : '—';
        }

        var checks = widget.querySelectorAll('[data-pwd-rule]');
        for (var c = 0; c < checks.length; c++) {
            var met = !!result.rules[checks[c].getAttribute('data-pwd-rule')];
            checks[c].classList.toggle('auth__pwd-check--met', met);
            var note = checks[c].querySelector('[data-pwd-note]');
            if (note) {
                note.textContent = met ? 'met' : 'not met';
            }

            /*
             * The four composition rules are the standing list. The rest are quality checks
             * nobody needs read out in advance — they appear only once the typed password
             * trips them ("fail"), or once the confirm field has something in it ("confirm").
             */
            var when = checks[c].getAttribute('data-pwd-when');
            if (when === 'fail') {
                checks[c].hidden = met || !password.length;
            } else if (when === 'confirm') {
                /*
                 * Revealed as soon as either field has something in it — otherwise a filled,
                 * fully-ticked password sits behind a disabled button with nothing on screen
                 * saying the confirm field is what's still missing.
                 */
                checks[c].hidden = !(password.length || (config.confirm && config.confirm.value.length));
            }
        }

        gate(config, password, result.unmet);
    }

    /* Blocks submit until every checklist rule passes; the server still validates on POST. */
    function gate(config, password, unmet) {
        var blocked = unmet.length > 0;

        if (config.button) {
            config.button.disabled = blocked;
            config.button.setAttribute('aria-disabled', blocked ? 'true' : 'false');
        }

        var hint = config.widget.querySelector('[data-pwd-blocked]');
        if (hint) {
            hint.hidden = !(blocked && password.length > 0);
        }
    }

    /*
     * Pulls in Django's common-password stems after the page is interactive. The gzipped copy
     * is a third of the size; DecompressionStream handles it in every current browser, and
     * anything older falls back to the plain file. If both fail the curated list still stands.
     */
    function loadWordList(url, onReady) {
        if (!url || typeof fetch !== 'function') { return; }

        var absorb = function (text) {
            var words = text.split('\n');
            for (var i = 0; i < words.length; i++) {
                if (words[i]) { WORDS[words[i]] = true; }
            }
            onReady();
        };

        var plain = function () {
            fetch(url).then(function (response) {
                return response.ok ? response.text() : Promise.reject();
            }).then(absorb).catch(function () {});
        };

        if (typeof DecompressionStream !== 'function') { return plain(); }

        /* The cache-buster is a query string, so .gz has to go before it, not after. */
        var parts = url.split('?');
        var gzUrl = parts[0] + '.gz' + (parts[1] ? '?' + parts[1] : '');

        fetch(gzUrl).then(function (response) {
            if (!response.ok) { return Promise.reject(); }
            return new Response(
                response.body.pipeThrough(new DecompressionStream('gzip'))
            ).text();
        }).then(absorb).catch(plain);
    }

    function initStrength() {
        var widgets = document.querySelectorAll('[data-pwd-strength]');
        var configs = [];

        for (var i = 0; i < widgets.length; i++) {
            (function (widget) {
                var input = document.getElementById(widget.getAttribute('data-pwd-input'));
                if (!input) { return; }

                var watched = [];
                var ids = (widget.getAttribute('data-pwd-watch') || '').split(',');
                for (var w = 0; w < ids.length; w++) {
                    var field = document.getElementById(ids[w].replace(/^\s+|\s+$/g, ''));
                    if (field) { watched.push(field); }
                }

                var config = {
                    widget: widget,
                    input: input,
                    watched: watched,
                    confirm: document.getElementById(widget.getAttribute('data-pwd-match') || ''),
                    button: document.getElementById(widget.getAttribute('data-pwd-gate') || '')
                };

                var update = function () { render(config); };
                input.addEventListener('input', update);
                if (config.confirm) { config.confirm.addEventListener('input', update); }
                for (var v = 0; v < watched.length; v++) {
                    watched[v].addEventListener('input', update);
                }
                update();
                configs.push(config);
            })(widgets[i]);
        }

        if (!configs.length) { return; }

        /* Re-check whatever is already typed once the bigger list arrives. */
        loadWordList(configs[0].widget.getAttribute('data-pwd-wordlist'), function () {
            for (var c = 0; c < configs.length; c++) { render(configs[c]); }
        });
    }

    /* Handles both markup shapes: a <button> wrapping an icon, and a bare <i role="button">. */
    function initToggles() {
        var buttons = document.querySelectorAll('.auth__password-toggle, .cprc__password-toggle');

        for (var i = 0; i < buttons.length; i++) {
            buttons[i].addEventListener('click', function (event) {
                event.preventDefault();

                var input = document.getElementById(this.getAttribute('data-target'));
                if (!input) { return; }

                var revealed = input.type === 'password';
                input.type = revealed ? 'text' : 'password';
                this.setAttribute('aria-pressed', revealed ? 'true' : 'false');
                this.setAttribute('aria-label', revealed ? 'Hide password' : 'Show password');

                var icon = this.tagName === 'I' ? this : this.querySelector('i');
                if (icon) {
                    icon.classList.toggle('fa-eye', !revealed);
                    icon.classList.toggle('fa-eye-slash', revealed);
                }
            });

            buttons[i].addEventListener('keydown', function (event) {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this.click();
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        initStrength();
        initToggles();
    });
})();
