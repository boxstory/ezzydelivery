var conditional_fields = $("div.shipping_destination");
console.log(conditional_fields);
conditional_fields.hide();

$(".shipping").change(function () {
  if ($(this).prop("checked") === "checked") {
    conditional_fields.show();
  } else {
    conditional_fields.hide();
  }
});
