let userIsViewingPage = true;

setInterval(focusChecker, 500);

function focusChecker() {
  if (document.hasFocus()) {
    if (!userIsViewingPage) {
      location.reload();
      userIsViewingPage = true;
    }
  } else {
    userIsViewingPage = false;
  }
}