/**
 * Business Registration Form Validation
 * Provides real-time validation for phone numbers and social media fields
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get form elements
    const phoneInput = document.querySelector('input[name="business_phone"]');
    const whatsappInput = document.querySelector('input[name="business_whatsapp"]');
    const facebookInput = document.querySelector('input[name="business_facebook_page"]');
    const instagramInput = document.querySelector('input[name="business_instagram"]');
    const form = document.querySelector('#core_business_register_form_main');

    /**
     * Validate phone/WhatsApp numbers - only digits allowed
     */
    function validatePhoneNumber(input) {
        if (!input) return;

        const value = input.value.trim();
        const errorDiv = getOrCreateErrorDiv(input);

        if (value === '') {
            clearError(input, errorDiv);
            return true;
        }

        // Remove common separators for checking
        const cleanedValue = value.replace(/[\s\-\(\)\+]/g, '');

        if (!/^\d+$/.test(cleanedValue)) {
            showError(input, errorDiv, 'Only numbers are allowed (0-9)');
            return false;
        } else {
            clearError(input, errorDiv);
            return true;
        }
    }

    /**
     * Validate social media usernames - no slashes or spaces
     */
    function validateSocialMedia(input) {
        if (!input) return;

        const value = input.value.trim();
        const errorDiv = getOrCreateErrorDiv(input);

        if (value === '') {
            clearError(input, errorDiv);
            return true;
        }

        // Check for slashes or spaces
        if (value.includes('/') || value.includes(' ')) {
            showError(input, errorDiv, 'Enter username only - no slashes (/) or spaces');
            return false;
        }

        // Warn if it looks like a URL
        if (value.includes('http://') || value.includes('https://') ||
            value.includes('facebook.com') || value.includes('instagram.com') ||
            value.includes('www.')) {
            showWarning(input, errorDiv, 'Please enter username only, not the full URL');
            return false;
        }

        clearError(input, errorDiv);
        return true;
    }

    /**
     * Get or create error div for input field
     */
    function getOrCreateErrorDiv(input) {
        let errorDiv = input.parentElement.querySelector('.validation-feedback');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'validation-feedback';
            errorDiv.style.fontSize = '0.875rem';
            errorDiv.style.marginTop = '0.25rem';
            input.parentElement.appendChild(errorDiv);
        }
        return errorDiv;
    }

    /**
     * Show error message
     */
    function showError(input, errorDiv, message) {
        input.classList.add('is-invalid');
        input.classList.remove('is-valid');
        errorDiv.textContent = message;
        errorDiv.style.color = '#dc3545';
        errorDiv.style.display = 'block';
    }

    /**
     * Show warning message
     */
    function showWarning(input, errorDiv, message) {
        input.classList.remove('is-invalid', 'is-valid');
        errorDiv.textContent = message;
        errorDiv.style.color = '#ffc107';
        errorDiv.style.display = 'block';
    }

    /**
     * Clear error/warning message
     */
    function clearError(input, errorDiv) {
        input.classList.remove('is-invalid');
        if (input.value.trim() !== '') {
            input.classList.add('is-valid');
        } else {
            input.classList.remove('is-valid');
        }
        errorDiv.textContent = '';
        errorDiv.style.display = 'none';
    }

    // Add real-time validation listeners
    if (phoneInput) {
        phoneInput.addEventListener('input', function() {
            validatePhoneNumber(this);
        });
        phoneInput.addEventListener('blur', function() {
            validatePhoneNumber(this);
        });
    }

    if (whatsappInput) {
        whatsappInput.addEventListener('input', function() {
            validatePhoneNumber(this);
        });
        whatsappInput.addEventListener('blur', function() {
            validatePhoneNumber(this);
        });
    }

    if (facebookInput) {
        facebookInput.addEventListener('input', function() {
            validateSocialMedia(this);
        });
        facebookInput.addEventListener('blur', function() {
            validateSocialMedia(this);
        });
    }

    if (instagramInput) {
        instagramInput.addEventListener('input', function() {
            validateSocialMedia(this);
        });
        instagramInput.addEventListener('blur', function() {
            validateSocialMedia(this);
        });
    }

    // Form submit validation
    if (form) {
        form.addEventListener('submit', function(e) {
            let isValid = true;

            // Validate all fields before submit
            if (phoneInput && !validatePhoneNumber(phoneInput)) {
                isValid = false;
            }
            if (whatsappInput && !validatePhoneNumber(whatsappInput)) {
                isValid = false;
            }
            if (facebookInput && !validateSocialMedia(facebookInput)) {
                isValid = false;
            }
            if (instagramInput && !validateSocialMedia(instagramInput)) {
                isValid = false;
            }

            // If validation fails, prevent form submission
            if (!isValid) {
                e.preventDefault();

                // Show error message at the top
                const existingAlert = document.querySelector('.validation-alert');
                if (existingAlert) {
                    existingAlert.remove();
                }

                const alertDiv = document.createElement('div');
                alertDiv.className = 'validation-alert alert alert-danger';
                alertDiv.style.marginBottom = '1rem';
                // Use DOM methods instead of innerHTML for XSS safety
                const icon = document.createElement('i');
                icon.className = 'fa-solid fa-exclamation-circle me-2';
                icon.setAttribute('aria-hidden', 'true');
                alertDiv.appendChild(icon);
                alertDiv.appendChild(document.createTextNode('Please fix the errors in the form before submitting.'));

                form.insertBefore(alertDiv, form.firstChild);

                // Scroll to first error
                const firstError = form.querySelector('.is-invalid');
                if (firstError) {
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }

                // Remove alert after 5 seconds
                setTimeout(() => {
                    alertDiv.remove();
                }, 5000);
            }
        });
    }

    // Add helpful placeholder text
    if (phoneInput) {
        phoneInput.placeholder = 'e.g., 97412345678';
        phoneInput.setAttribute('title', 'Enter numbers only');
    }
    if (whatsappInput) {
        whatsappInput.placeholder = 'e.g., 97412345678';
        whatsappInput.setAttribute('title', 'Enter numbers only');
    }
    if (facebookInput) {
        facebookInput.placeholder = 'e.g., yourbusinessname';
        facebookInput.setAttribute('title', 'Enter username only, without slashes or spaces');
    }
    if (instagramInput) {
        instagramInput.placeholder = 'e.g., yourbusinessname';
        instagramInput.setAttribute('title', 'Enter username only, without slashes or spaces');
    }
});
