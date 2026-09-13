/*
Purpose: Keep the booking form honest about which end of the job the booker is standing at
Used by: p2p/templates/p2p/book.html, p2p/templates/p2p/delivery_edit.html
Notes: Moves the profile prefill between the two address blocks, marks the block that is "you",
       and follows the role with the fee payer until the customer sets that one themselves.
       Prefill only ever moves values it put there — anything typed by hand is left alone.
       A third-party booker ("other") stands on neither leg: nothing is theirs, nothing is locked.
       The verified-number lock here is presentation only; the form's clean() is the real gate.
*/
(function () {
    'use strict';

    var form = document.getElementById('p2p_book_form_details')
        || document.getElementById('p2p_edit_form_details');
    if (!form) { return; }

    var meName = form.dataset.meName || '';
    var mePhone = form.dataset.mePhone || '';

    function field(name) { return form.querySelector('[name="' + name + '"]'); }
    function roleInputs() { return form.querySelectorAll('[name="booker_role"]'); }
    function role() {
        var checked = form.querySelector('[name="booker_role"]:checked');
        return checked ? checked.value : 'sender';
    }

    var senderSide = { name: field('sender_name'), phone: field('sender_phone') };
    var receiverSide = {
        name: field('customer_name'),
        phone: field('customer_phone'),
        whatsapp: field('customer_whatsapp')
    };

    /* Only clear what we put there. A value the customer typed is theirs. */
    function clearIfOurs(input, mine) {
        if (input && input.value.trim() === mine.trim()) { input.value = ''; }
    }
    function fillIfEmpty(input, mine) {
        if (input && !input.value.trim()) { input.value = mine; }
    }

    function clearOurs(side) {
        clearIfOurs(side.name, meName);
        clearIfOurs(side.phone, mePhone);
        if (side.whatsapp) { clearIfOurs(side.whatsapp, mePhone); }
    }

    function movePrefill(current) {
        if (!meName && !mePhone) { return; }

        /* Booking for two other people: neither block is theirs, so take our prefill
         * back out of both rather than leaving the booker's name on a stranger's leg. */
        if (current === 'other') {
            clearOurs(senderSide);
            clearOurs(receiverSide);
            return;
        }

        var mine = current === 'receiver' ? receiverSide : senderSide;
        clearOurs(current === 'receiver' ? senderSide : receiverSide);

        fillIfEmpty(mine.name, meName);
        fillIfEmpty(mine.phone, mePhone);
        if (mine.whatsapp) { fillIfEmpty(mine.whatsapp, mePhone); }
    }

    /* The verified number is not theirs to retype: it is where the confirm link goes.
     * The locked field always shows it, because the server will store it either way. */
    function moveLock(current) {
        form.querySelectorAll('[data-verified-lock]').forEach(function (input) {
            var locked = mePhone && input.dataset.verifiedLock === current;
            input.readOnly = !!locked;
            if (locked) { input.value = mePhone; }
        });
        form.querySelectorAll('[data-lock-for]').forEach(function (hint) {
            hint.hidden = !mePhone || hint.dataset.lockFor !== current;
        });
    }

    function markYou(current) {
        form.querySelectorAll('[data-you-for]').forEach(function (badge) {
            badge.hidden = badge.dataset.youFor !== current;
        });
    }

    /* The booker expects to be the one paying. Stop following the role the moment
     * they say otherwise — that click is a decision, not a default. */
    var feePayerTouched = false;
    form.querySelectorAll('[name="fee_payer"]').forEach(function (input) {
        input.addEventListener('change', function () { feePayerTouched = true; });
    });

    function followFeePayer(current) {
        if (feePayerTouched) { return; }
        /* A third-party booker pays for neither end, so there is no default to follow
         * — whatever is already selected stands until they choose. */
        var match = form.querySelector('[name="fee_payer"][value="' + current + '"]');
        if (match) { match.checked = true; }
    }

    function apply(moveValues) {
        var current = role();
        markYou(current);
        if (moveValues) {
            movePrefill(current);
            followFeePayer(current);
        }
        moveLock(current);
    }

    roleInputs().forEach(function (input) {
        input.addEventListener('change', function () { apply(true); });
    });

    /* On load only the badge is set: a re-rendered form after a validation error, and
     * the edit form, both already hold real answers that must not be shuffled. */
    apply(false);

})();
