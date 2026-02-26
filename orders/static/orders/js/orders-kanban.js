/**
 * ORDERS KANBAN BOARD
 * Drag-and-drop order management with status transitions
 */

class OrdersKanban {
  constructor() {
    this.columns = {
      'to_review': document.getElementById('kanban-column-review'),
      'ready_to_pickup': document.getElementById('kanban-column-confirmed'),
      'publish': document.getElementById('kanban-column-published'),
      'cancelled': document.getElementById('kanban-column-cancelled')
    };

    this.draggedCard = null;
    this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

    this.init();
  }

  init() {
    // Make all cards draggable
    document.querySelectorAll('.okb__card').forEach(card => {
      this.makeCardDraggable(card);
    });

    // Make all columns droppable
    Object.values(this.columns).forEach(column => {
      if (column) {
        this.makeColumnDroppable(column);
      }
    });

    // Update column counts
    this.updateAllCounts();

    console.log('OrdersKanban initialized');
  }

  makeCardDraggable(card) {
    card.setAttribute('draggable', 'true');

    card.addEventListener('dragstart', (e) => {
      this.draggedCard = card;
      card.classList.add('okb__card--dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/html', card.innerHTML);
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('okb__card--dragging');
      this.draggedCard = null;
    });
  }

  makeColumnDroppable(column) {
    const cardsContainer = column.querySelector('.okb__cards');
    if (!cardsContainer) return;

    cardsContainer.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';

      const afterElement = this.getDragAfterElement(cardsContainer, e.clientY);
      if (afterElement == null) {
        cardsContainer.appendChild(this.draggedCard);
      } else {
        cardsContainer.insertBefore(this.draggedCard, afterElement);
      }
    });

    cardsContainer.addEventListener('drop', (e) => {
      e.preventDefault();
      const newStatus = column.dataset.status;
      const orderId = this.draggedCard.dataset.orderId;
      const oldStatus = this.draggedCard.dataset.status;

      if (newStatus !== oldStatus) {
        this.updateOrderStatus(orderId, newStatus, oldStatus);
        this.draggedCard.dataset.status = newStatus;
      }

      this.updateAllCounts();
    });
  }

  getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.okb__card:not(.okb__card--dragging)')];

    return draggableElements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;

      if (offset < 0 && offset > closest.offset) {
        return { offset: offset, element: child };
      } else {
        return closest;
      }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  async updateOrderStatus(orderId, newStatus, oldStatus) {
    try {
      // Show loading toast
      this.showToast('Updating order status...', 'info');

      const response = await fetch(window.orderStatusUpdateUrl || '/orders/update-status/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken
        },
        body: JSON.stringify({
          order_id: parseInt(orderId),
          status: newStatus
        })
      });

      const data = await response.json();

      if (data.success) {
        this.showToast('Order status updated!', 'success');
        this.updateCardBadge(this.draggedCard, newStatus);
      } else {
        throw new Error(data.error || 'Update failed');
      }
    } catch (error) {
      console.error('Error updating order status:', error);
      this.showToast('Failed to update order: ' + error.message, 'error');

      // Revert card to old column
      const oldColumn = document.querySelector(`[data-status="${oldStatus}"] .okb__cards`);
      if (oldColumn && this.draggedCard) {
        oldColumn.appendChild(this.draggedCard);
        this.updateAllCounts();
      }
    }
  }

  updateCardBadge(card, status) {
    const badge = card.querySelector('.okb__card-badge');
    if (badge) {
      const statusLabels = {
        'to_review': 'To Review',
        'ready_to_pickup': 'Confirmed',
        'publish': 'Published',
        'cancelled': 'Cancelled'
      };
      badge.textContent = statusLabels[status] || status;
    }
  }

  updateAllCounts() {
    Object.entries(this.columns).forEach(([status, column]) => {
      if (column) {
        const cardsContainer = column.querySelector('.okb__cards');
        const count = cardsContainer ? cardsContainer.querySelectorAll('.okb__card').length : 0;
        const countBadge = column.querySelector('.okb__col-count');
        if (countBadge) {
          countBadge.textContent = count;
        }
      }
    });
  }

  showToast(message, type = 'info') {
    const existingToast = document.querySelector('.okb__toast');
    if (existingToast) {
      existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.className = 'okb__toast okb__toast--' + type;

    const colors = {
      success: 'var(--ez-success)',
      error: 'var(--ez-error)',
      info: 'var(--ez-info)'
    };

    toast.style.cssText = `
      position: fixed;
      bottom: 80px;
      right: 20px;
      background: ${colors[type]};
      color: white;
      padding: var(--ez-space-4) var(--ez-space-6);
      border-radius: var(--ez-radius-lg);
      box-shadow: var(--ez-shadow-xl);
      z-index: var(--ez-z-notification);
      animation: slideInUp 0.3s ease;
      font-size: var(--ez-font-sm);
      font-weight: var(--ez-font-weight-semibold);
      max-width: 300px;
    `;

    const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
    toast.innerHTML = `<span style="margin-right: 8px;">${icon}</span>${message}`;

    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOutDown 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

// Toggle between table and kanban views
class ViewToggle {
  constructor() {
    this.tableView = document.getElementById('orders-table-view');
    this.kanbanView = document.getElementById('orders-kanban-view');
    this.tableBtn = document.getElementById('view-toggle-table');
    this.kanbanBtn = document.getElementById('view-toggle-kanban');

    this.init();
  }

  init() {
    if (!this.tableView || !this.kanbanView) return;

    // Restore saved view preference
    const savedView = localStorage.getItem('ordersViewMode') || 'table';
    this.switchView(savedView);

    // Bind toggle buttons
    if (this.tableBtn) {
      this.tableBtn.addEventListener('click', () => this.switchView('table'));
    }

    if (this.kanbanBtn) {
      this.kanbanBtn.addEventListener('click', () => this.switchView('kanban'));
    }
  }

  switchView(viewMode) {
    if (viewMode === 'kanban') {
      this.tableView?.classList.add('d-none');
      this.kanbanView?.classList.remove('d-none');
      this.tableBtn?.classList.remove('active');
      this.kanbanBtn?.classList.add('active');

      // Initialize kanban if not already done
      if (!window.ordersKanban) {
        window.ordersKanban = new OrdersKanban();
      }
    } else {
      this.tableView?.classList.remove('d-none');
      this.kanbanView?.classList.add('d-none');
      this.tableBtn?.classList.add('active');
      this.kanbanBtn?.classList.remove('active');
    }

    localStorage.setItem('ordersViewMode', viewMode);
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  // Initialize view toggle
  if (document.getElementById('orders-table-view')) {
    window.viewToggle = new ViewToggle();
  }

  // Add toast animations
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideInUp {
      from {
        transform: translateY(100px);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }

    @keyframes slideOutDown {
      from {
        transform: translateY(0);
        opacity: 1;
      }
      to {
        transform: translateY(100px);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);
});
