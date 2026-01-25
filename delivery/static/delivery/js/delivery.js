/* ============================================
   DELIVERY APP - MERGED JAVASCRIPT
   ============================================ */

/* ---------- FLEET ---------- */
/* Note: This code is for legacy all_delivery_tasks.html template.
   The newer tasks_all.html uses Bootstrap collapse instead. */
$(document).ready(function () {
  // Only run on pages with the legacy delivery task cards (expandable rows)
  // Specifically target cards in rows with colspan (detail rows), not regular table content
  var $legacyDetailCards = $("table tr td[colspan] > .card");

  if ($legacyDetailCards.length > 0) {
    // Hide the detail cards initially
    $legacyDetailCards.hide();

    // Toggle on row click (only for the data row, not the detail row)
    $("table tr:not(:has(td[colspan]))").click(function (event) {
      event.stopPropagation();
      $(this).next("tr").find(".card").slideToggle();
    });
  }
});
