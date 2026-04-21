/**
 * ORDER WIZARD - Multi-Step Form Controller
 * Professional order creation with step-by-step validation
 */

function OrderWizard(options) {
  options = options || {};
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

OrderWizard.prototype.init = function() {
  var self = this;
  // Set initial step
  this.goToStep(1);

  // Bind navigation buttons
  if (this.prevBtn) {
    this.prevBtn.addEventListener('click', function() { self.previousStep(); });
  }

  if (this.nextBtn) {
    this.nextBtn.addEventListener('click', function() { self.nextStep(); });
  }

  if (this.submitBtn) {
    this.submitBtn.addEventListener('click', function() { self.submitForm(); });
  }

  // Auto-save on field change
  if (this.wizard) {
    this.wizard.addEventListener('input', function(e) { self.saveFieldData(e); });
  }

  // Phone to WhatsApp auto-copy
  var phoneInput = document.getElementById('wizard-customer-phone');
  var waInput = document.getElementById('wizard-customer-whatsapp');
  if (phoneInput && waInput) {
    phoneInput.addEventListener('input', function() {
      if (!waInput.value || waInput.value.indexOf('974') === 0) {
        waInput.value = '974' + this.value;
      }
    });
  }

  // COD amount change handler
  var codAmountInput = document.getElementById('wizard-cod-amount');
  var codStatusInput = document.getElementById('wizard-cod-status');
  if (codAmountInput && codStatusInput) {
    codAmountInput.addEventListener('input', function() {
      var amount = parseFloat(this.value) || 0;
      codStatusInput.value = amount > 0 ? 'include' : 'no_cod';
    });
  }

  console.log('OrderWizard initialized');
};

OrderWizard.prototype.saveFieldData = function(event) {
  var field = event.target;
  if (field.name) {
    this.formData[field.name] = field.value;
  }
};

OrderWizard.prototype.goToStep = function(stepNumber) {
  var self = this;
  if (stepNumber < 1 || stepNumber > this.totalSteps) return;

  this.currentStep = stepNumber;

  // Update step indicators
  this.stepElements.forEach(function(step, index) {
    var stepNum = index + 1;
    step.classList.remove('active', 'completed');

    if (stepNum < self.currentStep) {
      step.classList.add('completed');
    } else if (stepNum === self.currentStep) {
      step.classList.add('active');
    }
  });

  // Update progress bar
  if (this.stepsContainer) {
    this.stepsContainer.setAttribute('data-current', this.currentStep);
  }

  // Update panes
  this.panes.forEach(function(pane, index) {
    pane.classList.remove('active');
    if (index + 1 === self.currentStep) {
      pane.classList.add('active');
    }
  });

  // Update navigation buttons
  this.updateNavigationButtons();

  // Scroll to top
  if (this.wizard) {
    this.wizard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};

OrderWizard.prototype.updateNavigationButtons = function() {
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
};

OrderWizard.prototype.validateStep = function(stepNumber) {
  var self = this;
  var pane = this.panes[stepNumber - 1];
  if (!pane) return true;

  var requiredFields = pane.querySelectorAll('[required]');
  var isValid = true;

  requiredFields.forEach(function(field) {
    if (!field.value || field.value.trim() === '') {
      isValid = false;
      self.showFieldError(field, 'This field is required');
    } else {
      self.clearFieldError(field);
    }
  });

  // Additional validation for step 2 (customer details)
  if (stepNumber === 2) {
    var phoneInput = document.getElementById('wizard-customer-phone');
    if (phoneInput && phoneInput.value) {
      var phonePattern = /^\d{8}$/;
      if (!phonePattern.test(phoneInput.value)) {
        this.showFieldError(phoneInput, 'Phone must be 8 digits');
        isValid = false;
      }
    }
  }

  return isValid;
};

OrderWizard.prototype.showFieldError = function(field, message) {
  field.classList.add('is-invalid');
  field.style.borderColor = 'var(--ez-error)';

  var errorDiv = field.parentElement.querySelector('.wizard-field-error');
  if (!errorDiv) {
    errorDiv = document.createElement('div');
    errorDiv.className = 'wizard-field-error';
    errorDiv.style.color = 'var(--ez-error)';
    errorDiv.style.fontSize = 'var(--ez-font-xs)';
    errorDiv.style.marginTop = 'var(--ez-space-1)';
    field.parentElement.appendChild(errorDiv);
  }
  errorDiv.textContent = message;
};

OrderWizard.prototype.clearFieldError = function(field) {
  field.classList.remove('is-invalid');
  field.style.borderColor = '';

  var errorDiv = field.parentElement.querySelector('.wizard-field-error');
  if (errorDiv) {
    errorDiv.remove();
  }
};

OrderWizard.prototype.nextStep = function() {
  if (this.validateStep(this.currentStep)) {
    if (this.currentStep === 4) {
      // Update preview before moving to step 5
      this.updatePreview();
    }
    this.goToStep(this.currentStep + 1);
  } else {
    this.showToast('Please fill in all required fields', 'error');
  }
};

OrderWizard.prototype.previousStep = function() {
  this.goToStep(this.currentStep - 1);
};

OrderWizard.prototype.updatePreview = function() {
  var previewMap = {
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

  Object.keys(previewMap).forEach(function(elementId) {
    var fieldName = previewMap[elementId];
    var element = document.getElementById(elementId);
    var input = document.querySelector('[name="' + fieldName + '"]');

    if (element && input) {
      var value = input.value || '-';

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
};

OrderWizard.prototype.submitForm = function() {
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
  var form = document.getElementById('wizard-order-form');
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
};

OrderWizard.prototype.showToast = function(message, type) {
  type = type || 'info';
  var toast = document.createElement('div');
  toast.className = 'wizard-toast wizard-toast--' + type;
  var bgColor = type === 'error' ? 'var(--ez-error)' : 'var(--ez-success)';
  toast.style.cssText = 'position: fixed; top: 80px; right: 20px; background: ' + bgColor + '; color: white; padding: var(--ez-space-4) var(--ez-space-6); border-radius: var(--ez-radius-lg); box-shadow: var(--ez-shadow-xl); z-index: var(--ez-z-notification); animation: slideInRight 0.3s ease; font-size: var(--ez-font-sm); font-weight: var(--ez-font-weight-semibold);';
  toast.textContent = message;

  document.body.appendChild(toast);

  setTimeout(function() {
    toast.style.animation = 'slideOutRight 0.3s ease';
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
};

// Initialize wizard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  var wizardElement = document.querySelector('.orders-wizard');
  if (wizardElement) {
    window.orderWizard = new OrderWizard({
      totalSteps: 5
    });
  }
});

// Toast animations
var style = document.createElement('style');
style.textContent = '@keyframes slideInRight { from { transform: translateX(400px); opacity: 0; } to { transform: translateX(0); opacity: 1; } } @keyframes slideOutRight { from { transform: translateX(0); opacity: 1; } to { transform: translateX(400px); opacity: 0; } }';
document.head.appendChild(style);
