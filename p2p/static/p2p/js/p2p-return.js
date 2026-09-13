/*
Purpose: Show "what comes back" only once the leg back has actually been asked for
Used by: p2p/book.html, p2p/delivery_edit.html, workforce/forms/p2p_new.html
Notes: Its own file rather than a few lines inside each page's script, because the same block is
       rendered on three forms that share no other JavaScript. Presentation only — the server
       clears the description on an untick either way (p2p.forms.BookingDetailsForm.clean).
*/
(function () {
    'use strict';

    var block = document.getElementById('p2p_return_block');
    if (!block) { return; }

    var tick = block.querySelector('[name="return_trip"]');
    var body = block.querySelector('[data-return-body]');
    if (!tick || !body) { return; }

    function sync() { body.hidden = !tick.checked; }

    tick.addEventListener('change', sync);
    /* A form re-rendered after a validation error already carries the answer. */
    sync();
})();
