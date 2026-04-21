/**
 * ORDERS KANBAN BOARD
 * Drag-and-drop order management with status transitions
 */

function OrdersKanban() {
  this.columns = {
    'to_review': document.getElementById('kanban-column-review'),
    'ready_to_pickup': document.getElementById('kanban-column-confirmed'),
    'publish': document.getElementById('kanban-column-published'),
    'cancelled': document.getElementById('kanban-column-cancelled')
  };

  var csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
  this.draggedCard = null;
  this.csrfToken = csrfEl ? csrfEl.value : null;

  this.init();
}

OrdersKanban.prototype.init = function() {
  var self = this;
  // Make all cards draggable
  document.querySelectorAll('.okb__card').forEach(function(card) {
    self.makeCardDraggable(card);
  });

  // Make all columns droppable
  Object.keys(this.columns).forEach(function(key) {
    var column = self.columns[key];
    if (column) {
      self.makeColumnDroppable(column);
    }
  });

  // Update column counts
  this.updateAllCounts();

  console.log('OrdersKanban initialized');
};

OrdersKanban.prototype.makeCardDraggable = function(card) {
  var self = this;
  card.setAttribute('draggable', 'true');

  card.addEventListener('dragstart', function(e) {
    self.draggedCard = card;
    card.classList.add('okb__card--dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', card.innerHTML);
  });

  card.addEventListener('dragend', function() {
    card.classList.remove('okb__card--dragging');
    self.draggedCard = null;
  });
};

OrdersKanban.prototype.makeColumnDroppable = function(column) {
  var self = this;
  var cardsContainer = column.querySelector('.okb__cards');
  if (!cardsContainer) return;

  cardsContainer.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    var afterElement = self.getDragAfterElement(cardsContainer, e.clientY);
    if (afterElement === null) {
      cardsContainer.appendChild(self.draggedCard);
    } else {
      cardsContainer.insertBefore(self.draggedCard, afterElement);
    }
  });

  cardsContainer.addEventListener('drop', function(e) {
    e.preventDefault();
    var newStatus = column.dataset.status;
    var orderId = self.draggedCard.dataset.orderId;
    var oldStatus = self.draggedCard.dataset.status;

    if (newStatus !== oldStatus) {
      self.updateOrderStatus(orderId, newStatus, oldStatus);
      self.draggedCard.dataset.status = newStatus;
    }

    self.updateAllCounts();
  });
};

OrdersKanban.prototype.getDragAfterElement = function(container, y) {
  var draggableElements = Array.prototype.slice.call(container.querySelectorAll('.okb__card:not(.okb__card--dragging)'));

  return draggableElements.reduce(function(closest, child) {
    var box = child.getBoundingClientRect();
    var offset = y - box.top - box.height / 2;

    if (offset < 0 && offset > closest.offset) {
      return { offset: offset, element: child };
    } else {
      return closest;
    }
  }, { offset: Number.NEGATIVE_INFINITY }).element;
};

OrdersKanban.prototype.updateOrderStatus = function(orderId, newStatus, oldStatus) {
  var self = this;
  try {
    // Show loading toast
    this.showToast('Updating order status...', 'info');

    fetch(window.orderStatusUpdateUrl || '/orders/update-status/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.csrfToken
      },
      body: JSON.stringify({
        order_id: parseInt(orderId),
        status: newStatus
      })
    }).then(function(response) {
      return response.json();
    }).then(function(data) {
      if (data.success) {
        self.showToast('Order status updated!', 'success');
        self.updateCardBadge(self.draggedCard, newStatus);
      } else {
        throw new Error(data.error || 'Update failed');
      }
    }).catch(function(error) {
      console.error('Error updating order status:', error);
      self.showToast('Failed to update order: ' + error.message, 'error');

      // Revert card to old column
      var oldColumn = document.querySelector('[data-status="' + oldStatus + '"] .okb__cards');
      if (oldColumn && self.draggedCard) {
        oldColumn.appendChild(self.draggedCard);
        self.updateAllCounts();
      }
    });
  } catch (error) {
    console.error('Error updating order status:', error);
    this.showToast('Failed to update order: ' + error.message, 'error');

    // Revert card to old column
    var oldColumn = document.querySelector('[data-status="' + oldStatus + '"] .okb__cards');
    if (oldColumn && this.draggedCard) {
      oldColumn.appendChild(this.draggedCard);
      this.updateAllCounts();
    }
  }
};

OrdersKanban.prototype.updateCardBadge = function(card, status) {
  var badge = card.querySelector('.okb__card-badge');
  if (badge) {
    var statusLabels = {
      'to_review': 'To Review',
      'ready_to_pickup': 'Confirmed',
      'publish': 'Published',
      'cancelled': 'Cancelled'
    };
    badge.textContent = statusLabels[status] || status;
  }
};

OrdersKanban.prototype.updateAllCounts = function() {
  var self = this;
  Object.keys(this.columns).forEach(function(status) {
    var column = self.columns[status];
    if (column) {
      var cardsContainer = column.querySelector('.okb__cards');
      var count = cardsContainer ? cardsContainer.querySelectorAll('.okb__card').length : 0;
      var countBadge = column.querySelector('.okb__col-count');
      if (countBadge) {
        countBadge.textContent = count;
      }
    }
  });
};

OrdersKanban.prototype.showToast = function(message, type) {
  type = type || 'info';
  var existingToast = document.querySelector('.okb__toast');
  if (existingToast) {
    existingToast.remove();
  }

  var toast = document.createElement('div');
  toast.className = 'okb__toast okb__toast--' + type;

  var colors = {
    success: 'var(--ez-success)',
    error: 'var(--ez-error)',
    info: 'var(--ez-info)'
  };

  var bgColor = colors[type];
  toast.style.cssText = 'position: fixed; bottom: 80px; right: 20px; background: ' + bgColor + '; color: white; padding: var(--ez-space-4) var(--ez-space-6); border-radius: var(--ez-radius-lg); box-shadow: var(--ez-shadow-xl); z-index: var(--ez-z-notification); animation: slideInUp 0.3s ease; font-size: var(--ez-font-sm); font-weight: var(--ez-font-weight-semibold); max-width: 300px;';

  var icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
  toast.innerHTML = '<span style="margin-right: 8px;">' + icon + '</span>' + message;

  document.body.appendChild(toast);

  setTimeout(function() {
    toast.style.animation = 'slideOutDown 0.3s ease';
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
};

// Toggle between table and kanban views
function ViewToggle() {
  this.tableView = document.getElementById('orders-table-view');
  this.kanbanView = document.getElementById('orders-kanban-view');
  this.tableBtn = document.getElementById('view-toggle-table');
  this.kanbanBtn = document.getElementById('view-toggle-kanban');

  this.init();
}

ViewToggle.prototype.init = function() {
  var self = this;
  if (!this.tableView || !this.kanbanView) return;

  // Restore saved view preference
  var savedView = localStorage.getItem('ordersViewMode') || 'table';
  this.switchView(savedView);

  // Bind toggle buttons
  if (this.tableBtn) {
    this.tableBtn.addEventListener('click', function() { self.switchView('table'); });
  }

  if (this.kanbanBtn) {
    this.kanbanBtn.addEventListener('click', function() { self.switchView('kanban'); });
  }
};

ViewToggle.prototype.switchView = function(viewMode) {
  if (viewMode === 'kanban') {
    if (this.tableView) this.tableView.classList.add('d-none');
    if (this.kanbanView) this.kanbanView.classList.remove('d-none');
    if (this.tableBtn) this.tableBtn.classList.remove('active');
    if (this.kanbanBtn) this.kanbanBtn.classList.add('active');

    // Initialize kanban if not already done
    if (!window.ordersKanban) {
      window.ordersKanban = new OrdersKanban();
    }
  } else {
    if (this.tableView) this.tableView.classList.remove('d-none');
    if (this.kanbanView) this.kanbanView.classList.add('d-none');
    if (this.tableBtn) this.tableBtn.classList.add('active');
    if (this.kanbanBtn) this.kanbanBtn.classList.remove('active');
  }

  localStorage.setItem('ordersViewMode', viewMode);
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  // Initialize view toggle
  if (document.getElementById('orders-table-view')) {
    window.viewToggle = new ViewToggle();
  }

  // Add toast animations
  var style = document.createElement('style');
  style.textContent = '@keyframes slideInUp { from { transform: translateY(100px); opacity: 0; } to { transform: translateY(0); opacity: 1; } } @keyframes slideOutDown { from { transform: translateY(0); opacity: 1; } to { transform: translateY(100px); opacity: 0; } }';
  document.head.appendChild(style);
});
