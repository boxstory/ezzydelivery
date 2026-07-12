/* Purpose: Behaviour for the reusable multi-select checkbox filter (.msf).
   Used by: workforce/parts/components/_multiselect_filter.html across staff lists.
   Notes: Fully event-delegated so it survives HTMX content swaps. */
(function () {
    function refresh(root) {
        var boxes = root.querySelectorAll('input[type="checkbox"]');
        var checked = 0;
        boxes.forEach(function (cb) { if (cb.checked) checked++; });
        var text = root.querySelector('.msf__toggle-text');
        var pill = root.querySelector('.msf__count');
        var toggle = root.querySelector('.msf__toggle');
        var allText = (toggle && toggle.getAttribute('data-msf-all')) || 'All';
        if (text) text.textContent = checked ? checked + ' selected' : allText;
        if (pill) {
            pill.textContent = checked;
            pill.hidden = checked === 0;
        }
    }

    document.addEventListener('change', function (e) {
        if (e.target && e.target.matches('.msf input[type="checkbox"]')) {
            var root = e.target.closest('[data-msf]');
            if (root) refresh(root);
        }
    });

    document.addEventListener('click', function (e) {
        var clear = e.target.closest && e.target.closest('[data-msf-clear]');
        if (clear) {
            e.preventDefault();
            var root = clear.closest('[data-msf]');
            if (root) {
                root.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = false; });
                refresh(root);
            }
        }
    });
})();
