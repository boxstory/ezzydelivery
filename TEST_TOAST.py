"""
TEMPORARY FILE - Test Toast Notifications

To test the toast system, add this to your urls.py:

from . import TEST_TOAST

urlpatterns = [
    # ... your existing urls ...
    path('test-toast/', TEST_TOAST.test_toast_view, name='test_toast'),
]

Then visit: http://localhost:8000/test-toast/

DELETE THIS FILE AFTER TESTING!
"""

from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponse

def test_toast_view(request):
    """Test view to demonstrate toast notifications"""

    if request.method == 'POST':
        toast_type = request.POST.get('type', 'info')

        if toast_type == 'success':
            messages.success(request, 'This is a success message! Order #12345 created successfully.')
        elif toast_type == 'error':
            messages.error(request, 'This is an error message! Failed to process payment.')
        elif toast_type == 'warning':
            messages.warning(request, 'This is a warning message! Your session will expire in 5 minutes.')
        elif toast_type == 'info':
            messages.info(request, 'This is an info message! New features are now available.')

        return redirect('test_toast')

    html = """
    {% load static %}
    <!DOCTYPE html>
    <html>
    <head>
        <title>Toast Test</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        {% include "includes/toast_notifications.html" %}

        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card shadow">
                        <div class="card-header bg-primary text-white">
                            <h4 class="mb-0"><i class="fas fa-flask"></i> Toast Notification Test</h4>
                        </div>
                        <div class="card-body">
                            <h5>Test Django Messages (Server-Side)</h5>
                            <p class="text-muted">Click buttons below to test different message types:</p>

                            <form method="POST" class="mb-4">
                                {% csrf_token %}
                                <div class="d-grid gap-2">
                                    <button type="submit" name="type" value="success" class="btn btn-success">
                                        <i class="fas fa-check-circle"></i> Test Success Toast
                                    </button>
                                    <button type="submit" name="type" value="error" class="btn btn-danger">
                                        <i class="fas fa-exclamation-circle"></i> Test Error Toast
                                    </button>
                                    <button type="submit" name="type" value="warning" class="btn btn-warning">
                                        <i class="fas fa-exclamation-triangle"></i> Test Warning Toast
                                    </button>
                                    <button type="submit" name="type" value="info" class="btn btn-info">
                                        <i class="fas fa-info-circle"></i> Test Info Toast
                                    </button>
                                </div>
                            </form>

                            <hr>

                            <h5>Test JavaScript (Client-Side)</h5>
                            <p class="text-muted">Click buttons below to test JavaScript toast functions:</p>

                            <div class="d-grid gap-2">
                                <button onclick="showSuccessToast('JavaScript success toast works!')" class="btn btn-outline-success">
                                    <i class="fas fa-code"></i> showSuccessToast()
                                </button>
                                <button onclick="showErrorToast('JavaScript error toast works!')" class="btn btn-outline-danger">
                                    <i class="fas fa-code"></i> showErrorToast()
                                </button>
                                <button onclick="showWarningToast('JavaScript warning toast works!')" class="btn btn-outline-warning">
                                    <i class="fas fa-code"></i> showWarningToast()
                                </button>
                                <button onclick="showInfoToast('JavaScript info toast works!')" class="btn btn-outline-info">
                                    <i class="fas fa-code"></i> showInfoToast()
                                </button>
                                <button onclick="showToast({message: 'Custom toast with 10 second duration', type: 'primary', duration: 10000})" class="btn btn-outline-primary">
                                    <i class="fas fa-code"></i> Custom Toast
                                </button>
                            </div>
                        </div>
                        <div class="card-footer text-center">
                            <small class="text-muted">
                                <i class="fas fa-info-circle"></i>
                                Toasts appear in the top-right corner
                            </small>
                        </div>
                    </div>

                    <div class="alert alert-warning mt-4" role="alert">
                        <i class="fas fa-exclamation-triangle"></i>
                        <strong>Note:</strong> Delete TEST_TOAST.py and remove this URL after testing!
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """

    from django.template import Template, Context
    template = Template(html)
    context = Context({'messages': messages.get_messages(request)})
    return HttpResponse(template.render(context))
