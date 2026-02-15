/**
 * ORDER WIZARD - Multi-Step Form Controller
 * Professional order creation with step-by-step validation
 */

class OrderWizard {
  constructor(options = {}) {
    this.currentStep = 1;
    this.totalSteps = options.totalSteps || 5;
    this.formData = {};

    // Element references
    this.wizard = document.querySelector('.orders-wizard');
    this.stepsContainer = document.querySelector('.wizard-steps');
    this.panes = document.querySelectorAll('.wizard-pane');
    this.stepElements = document.querySelectorAll('.wizard-step');
    this.prevBtn = document.getElementById('wizard-btn-prev');
    this.nextBtn = document.getElementById('wizard-btn-next');
    this.submitBtn = document.getElementById('wizard-btn-submit');

    this.init();
  }

  init() {
    // Set initial step
    this.goToStep(1);

    // Bind navigation buttons
    if (this.prevBtn) {
      this.prevBtn.addEventListener('click', () => this.previousStep());
    }

    if (this.nextBtn) {
      this.nextBtn.addEventListener('click', () => this.nextStep());
    }

    if (this.submitBtn) {
      this.submitBtn.addEventListener('click', () => this.submitForm());
    }

    // Auto-save on field change
    this.wizard.addEventListener('input', (e) => this.saveFieldData(e));

    // Phone to WhatsApp auto-copy
    const phoneInput = document.getElementById('wizard-customer-phone');
    const waInput = document.getElementById('wizard-customer-whatsapp');
    if (phoneInput && waInput) {
      phoneInput.addEventListener('input', function() {
        if (!waInput.value || waInput.value.startsWith('974')) {
          waInput.value = '974' + this.value;
        }
      });
    }

    // COD amount change handler
    const codAmountInput = document.getElementById('wizard-cod-amount');
    const codStatusInput = document.getElementById('wizard-cod-status');
    if (codAmountInput && codStatusInput) {
      codAmountInput.addEventListener('input', function() {
        const amount = parseFloat(this.value) || 0;
        codStatusInput.value = amount > 0 ? 'include' : 'no_cod';
      });
    }

    console.log('OrderWizard initialized');
  }

  saveFieldData(event) {
    const field = event.target;
    if (field.name) {
      this.formData[field.name] = field.value;
    }
  }

  goToStep(stepNumber) {
    if (stepNumber < 1 || stepNumber > this.totalSteps) return;

    this.currentStep = stepNumber;

    // Update step indicators
    this.stepElements.forEach((step, index) => {
      const stepNum = index + 1;
      step.classList.remove('active', 'completed');

      if (stepNum < this.currentStep) {
        step.classList.add('completed');
      } else if (stepNum === this.currentStep) {
        step.classList.add('active');
      }
    });

    // Update progress bar
    if (this.stepsContainer) {
      this.stepsContainer.setAttribute('data-current', this.currentStep);
    }

    // Update panes
    this.panes.forEach((pane, index) => {
      pane.classList.remove('active');
      if (index + 1 === this.currentStep) {
        pane.classList.add('active');
      }
    });

    // Update navigation buttons
    this.updateNavigationButtons();

    // Scroll to top
    if (this.wizard) {
      this.wizard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  updateNavigationButtons() {
    // Previous button
    if (this.prevBtn) {
      this.prevBtn.disabled = this.currentStep === 1;
    }

    // Next/Submit button visibility
    if (this.currentStep === this.totalSteps) {
      if (this.nextBtn) this.nextBtn.style.display = 'none';
      if (this.submitBtn) this.submitBtn.style.display = 'inline-flex';
    } else {
      if (this.nextBtn) this.nextBtn.style.display = 'inline-flex';
      if (this.submitBtn) this.submitBtn.style.display = 'none';
    }
  }

  validateStep(stepNumber) {
    const pane = this.panes[stepNumber - 1];
    if (!pane) return true;

    const requiredFields = pane.querySelectorAll('[required]');
    let isValid = true;

    requiredFields.forEach(field => {
      if (!field.value || field.value.trim() === '') {
        isValid = false;
        this.showFieldError(field, 'This field is required');
      } else {
        this.clearFieldError(field);
      }
    });

    // Additional validation for step 2 (customer details)
    if (stepNumber === 2) {
      const phoneInput = document.getElementById('wizard-customer-phone');
      if (phoneInput && phoneInput.value) {
        const phonePattern = /^\d{8}$/;
        if (!phonePattern.test(phoneInput.value)) {
          this.showFieldError(phoneInput, 'Phone must be 8 digits');
          isValid = false;
        }
      }
    }

    return isValid;
  }

  showFieldError(field, message) {
    field.classList.add('is-invalid');
    field.style.borderColor = 'var(--ez-error)';

    let errorDiv = field.parentElement.querySelector('.wizard-field-error');
    if (!errorDiv) {
      errorDiv = document.createElement('div');
      errorDiv.className = 'wizard-field-error';
      errorDiv.style.color = 'var(--ez-error)';
      errorDiv.style.fontSize = 'var(--ez-font-xs)';
      errorDiv.style.marginTop = 'var(--ez-space-1)';
      field.parentElement.appendChild(errorDiv);
    }
    errorDiv.textContent = message;
  }

  clearFieldError(field) {
    field.classList.remove('is-invalid');
    field.style.borderColor = '';

    const errorDiv = field.parentElement.querySelector('.wizard-field-error');
    if (errorDiv) {
      errorDiv.remove();
    }
  }

  nextStep() {
    if (this.validateStep(this.currentStep)) {
      if (this.currentStep === 4) {
        // Update preview before moving to step 5
        this.updatePreview();
      }
      this.goToStep(this.currentStep + 1);
    } else {
      this.showToast('Please fill in all required fields', 'error');
    }
  }

  previousStep() {
    this.goToStep(this.currentStep - 1);
  }

  updatePreview() {
    // Update preview values from form data
    const previewMap = {
      'preview-customer-name': 'customer_name',
      'preview-customer-phone': 'customer_phone',
      'preview-customer-address': 'customer_address',
      'preview-dl-zone': 'dl_zone',
      'preview-dl-street': 'dl_street',
      'preview-dl-building': 'dl_building',
      'preview-cod-amount': 'cod_amount',
      'preview-pickup-location': 'pickup_location',
      'preview-order-notes': 'order_notes'
    };

    Object.entries(previewMap).forEach(([elementId, fieldName]) => {
      const element = document.getElementById(elementId);
      const input = document.querySelector(`[name="${fieldName}"]`);

      if (element && input) {
        let value = input.value || '-';

        // Format specific fields
        if (fieldName === 'customer_phone' && value !== '-') {
          value = '+974 ' + value;
        } else if (fieldName === 'cod_amount' && value !== '-') {
          value = 'QAR ' + parseFloat(value).toFixed(2);
        } else if (fieldName === 'pickup_location' && input.selectedOptions[0]) {
          value = input.selectedOptions[0].text;
        }

        element.textContent = value;
      }
    });
  }

  submitForm() {
    // Final validation
    if (!this.validateStep(this.currentStep)) {
      this.showToast('Please review your order details', 'error');
      return;
    }

    // Show loading state
    if (this.submitBtn) {
      this.submitBtn.disabled = true;
      this.submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating Order...';
    }

    // Get the actual form element and submit it
    const form = document.getElementById('wizard-order-form');
    if (form) {
      form.submit();
    } else {
      console.error('Form not found');
      this.showToast('Error submitting form', 'error');
      if (this.submitBtn) {
        this.submitBtn.disabled = false;
        this.submitBtn.innerHTML = '<i class="fas fa-check-circle"></i> Create Order';
      }
    }
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'wizard-toast wizard-toast--' + type;
    toast.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      background: ${type === 'error' ? 'var(--ez-error)' : 'var(--ez-success)'};
      color: white;
      padding: var(--ez-space-4) var(--ez-space-6);
      border-radius: var(--ez-radius-lg);
      box-shadow: var(--ez-shadow-xl);
      z-index: var(--ez-z-notification);
      animation: slideInRight 0.3s ease;
      font-size: var(--ez-font-sm);
      font-weight: var(--ez-font-weight-semibold);
    `;
    toast.textContent = message;

    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOutRight 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

// Initialize wizard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  const wizardElement = document.querySelector('.orders-wizard');
  if (wizardElement) {
    window.orderWizard = new OrderWizard({
      totalSteps: 5
    });
  }
});

// Toast animations
const style = document.createElement('style');
style.textContent = `
  @keyframes slideInRight {
    from {
      transform: translateX(400px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  @keyframes slideOutRight {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(400px);
      opacity: 0;
    }
  }
`;
document.head.appendChild(style);
