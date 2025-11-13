"""
Password Reset Views with WhatsApp Verification
"""
from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.views.decorators.http import require_http_methods
from .whatsapp_utils import (
    create_verification,
    verify_code,
    send_password_reset_completion_notification,
    validate_input_phone
)
from .models import Profile

User = get_user_model()


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    """
    Password reset request - user can choose email or WhatsApp
    """
    if request.method == 'POST':
        reset_method = request.POST.get('reset_method')  # 'email' or 'whatsapp'
        identifier = request.POST.get('identifier')  # email or phone number

        if reset_method == 'whatsapp':
            # Handle WhatsApp reset
            try:
                # Validate and sanitize phone number input
                is_valid, sanitized_phone, error_msg = validate_input_phone(identifier)

                if not is_valid:
                    messages.error(request, f'Invalid phone number: {error_msg}')
                    return render(request, 'accounts/password_reset_request.html')

                # Find user by phone number
                profile = Profile.objects.filter(whatsapp=sanitized_phone).first()

                if not profile:
                    messages.error(request, 'No account found with this phone number')
                    return render(request, 'accounts/password_reset_request.html')

                # Create and send verification code
                result = create_verification(
                    user=profile.user,
                    phone_number=str(profile.whatsapp),
                    verification_type='password_reset'
                )

                if result['send_result']['success']:
                    # Store phone in session for verification step
                    request.session['reset_phone'] = str(profile.whatsapp)
                    messages.success(request, 'Verification code sent to your WhatsApp')
                    return redirect('core:password_reset_verify')
                else:
                    messages.error(request, f"Failed to send code: {result['send_result'].get('error', 'Unknown error')}")

            except Exception as e:
                messages.error(request, f'Error processing request: {str(e)}')

        elif reset_method == 'email':
            # Handle email reset (existing allauth functionality)
            # Redirect to allauth's password reset
            return redirect('account_reset_password')

    return render(request, 'accounts/password_reset_request.html')


@require_http_methods(["GET", "POST"])
def password_reset_verify(request):
    """
    Verify WhatsApp code for password reset
    """
    phone_number = request.session.get('reset_phone')

    if not phone_number:
        messages.error(request, 'Session expired. Please start over.')
        return redirect('core:password_reset_request')

    if request.method == 'POST':
        verification_code = request.POST.get('verification_code')

        # Verify the code
        result = verify_code(phone_number, verification_code, 'password_reset')

        if result['success']:
            # Store verification ID in session for password change step
            request.session['verified_reset'] = result['verification'].id
            messages.success(request, 'Code verified! Please enter your new password.')
            return redirect('core:password_reset_confirm')
        else:
            messages.error(request, result.get('error', 'Invalid verification code'))

    context = {
        'phone_number': phone_number
    }
    return render(request, 'accounts/password_reset_verify.html', context)


@require_http_methods(["GET", "POST"])
def password_reset_confirm(request):
    """
    Confirm new password after WhatsApp verification
    """
    verification_id = request.session.get('verified_reset')

    if not verification_id:
        messages.error(request, 'Please verify your code first.')
        return redirect('core:password_reset_request')

    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'accounts/password_reset_confirm.html')

        if len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters')
            return render(request, 'accounts/password_reset_confirm.html')

        try:
            # Get verification to find user
            from .models import WhatsAppVerification
            verification = WhatsAppVerification.objects.get(id=verification_id, is_verified=True)

            if verification.user:
                # Update password
                verification.user.password = make_password(password1)
                verification.user.save()

                # Send completion notification via WhatsApp
                send_password_reset_completion_notification(
                    user=verification.user,
                    phone_number=verification.phone_number
                )

                # Clear session
                request.session.pop('reset_phone', None)
                request.session.pop('verified_reset', None)

                messages.success(request, 'Password reset successfully! You can now login.')
                return redirect('account_login')
            else:
                messages.error(request, 'User not found')

        except Exception as e:
            messages.error(request, f'Error resetting password: {str(e)}')

    return render(request, 'accounts/password_reset_confirm.html')
