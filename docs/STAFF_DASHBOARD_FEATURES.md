# Staff Dashboard - Order & Delivery Card Features Reference

**Document:** Staff Dashboard Interactive Features
**Date Created:** November 14, 2025
**Status:** Active Reference
**Last Updated:** November 14, 2025

---

## 📋 Overview

This document details all interactive features implemented in the staff dashboard order and delivery task cards, including button functionality, AJAX endpoints, and JavaScript handlers.

---

## 🎯 Order Card Features (orders_list_view.html)

### 1. Quick Action Buttons

#### WhatsApp Integration Buttons

**Location:** Quick Actions section of order card

**Button 1: WhatsApp Location**
```html
<a href="https://wa.me/{{ order.customer_phone }}?text=Hello {{ order.customer_name }}, this is regarding your order {{ order.client_order_code }}"
   target="_blank" class="btn btn-success btn-sm w-100">
    <i class="fa-brands fa-whatsapp me-1"></i>WhatsApp Location
</a>
```
- Opens WhatsApp with pre-filled message
- Message includes customer name and order code
- Opens in new tab

**Button 2: WhatsApp Reconfirm Address**
```html
<a href="https://wa.me/{{ order.customer_phone }}?text=Hi {{ order.customer_name }}, please confirm your delivery address for order {{ order.client_order_code }}: {{ order.customer_address }}"
   target="_blank" class="btn btn-outline-success btn-sm w-100">
    <i class="fa-brands fa-whatsapp me-1"></i>Reconfirm
</a>
```
- Opens WhatsApp with address confirmation message
- Includes full customer address in message
- Opens in new tab

---

#### Publish to Delivery Button

**Conditional Display:**
```html
{% if order.order_status == 'publish' %}
    <button class="btn btn-success btn-sm w-100" disabled>
        <i class="fa-solid fa-check-circle me-1"></i>Published
    </button>
{% else %}
    <button class="btn btn-primary btn-sm w-100" onclick="publishToDelivery({{ order.id }})">
        <i class="fa-solid fa-rocket me-1"></i>Publish to Delivery
    </button>
{% endif %}
```

**JavaScript Function:**
```javascript
function publishToDelivery(orderId) {
    if (confirm('Are you sure you want to publish this order to delivery?')) {
        fetch(`/workforce/orders/${orderId}/publish/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ action: 'publish' })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Order published successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Failed to publish order'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while publishing the order');
        });
    }
}
```

**Required Backend Endpoint:**
- URL: `/workforce/orders/<order_id>/publish/`
- Method: POST
- Request Body: `{ "action": "publish" }`
- Response: `{ "success": true/false, "error": "message" }`

---

#### Update Status Dropdown

**HTML Structure:**
```html
<div class="dropdown w-100">
    <button class="btn btn-outline-secondary btn-sm dropdown-toggle w-100" type="button"
            id="statusDropdown{{ order.id }}" data-bs-toggle="dropdown">
        <i class="fa-solid fa-flag me-1"></i>Update Status
    </button>
    <ul class="dropdown-menu" aria-labelledby="statusDropdown{{ order.id }}">
        <li><a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'not_connected')">
            <i class="fa-solid fa-phone-slash me-2 text-danger"></i>Not Connected
        </a></li>
        <li><a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'no_respond')">
            <i class="fa-solid fa-volume-xmark me-2 text-warning"></i>No Response
        </a></li>
        <li><a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'customer_cancelled')">
            <i class="fa-solid fa-ban me-2 text-danger"></i>Customer Cancelled
        </a></li>
        <li><a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'rescheduled')">
            <i class="fa-solid fa-calendar-days me-2 text-info"></i>Rescheduled
        </a></li>
        <li><a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'address_issue')">
            <i class="fa-solid fa-location-crosshairs me-2 text-warning"></i>Address Issue
        </a></li>
    </ul>
</div>
```

**Status Options:**
1. `not_connected` - Customer not reachable by phone
2. `no_respond` - Customer not responding
3. `customer_cancelled` - Customer cancelled the order
4. `rescheduled` - Delivery rescheduled
5. `address_issue` - Problem with delivery address

**JavaScript Function:**
```javascript
function updateOrderStatus(orderId, status) {
    event.preventDefault();
    if (confirm(`Update order status to "${status.replace('_', ' ')}"?`)) {
        fetch(`/workforce/orders/${orderId}/update-status/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ status: status })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Status updated successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Failed to update status'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while updating status');
        });
    }
}
```

**Required Backend Endpoint:**
- URL: `/workforce/orders/<order_id>/update-status/`
- Method: POST
- Request Body: `{ "status": "status_value" }`
- Response: `{ "success": true/false, "error": "message" }`

---

### 2. Comments Section

**HTML Structure:**
```html
<div class="comments-preview mt-3">
    <button class="btn btn-outline-info btn-sm position-relative"
            data-bs-toggle="collapse" data-bs-target="#comments{{ order.id }}">
        <i class="fa-solid fa-comments me-1"></i>Comments
        {% if order.unread_comments_count %}
        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">
            {{ order.unread_comments_count }}
            <span class="visually-hidden">unread comments</span>
        </span>
        {% endif %}
    </button>
    <div class="collapse mt-2" id="comments{{ order.id }}">
        <div class="card card-body bg-light">
            <div class="comments-list" style="max-height: 200px; overflow-y: auto;">
                {% if order.order_comments.all %}
                {% for comment in order.order_comments.all %}
                <div class="comment-item mb-2 p-2 bg-white rounded">
                    <small class="text-muted d-block">
                        <strong>{{ comment.name }}</strong> - {{ comment.created_at|date:"M d, Y H:i" }}
                    </small>
                    <p class="mb-0 small">{{ comment.body }}</p>
                </div>
                {% endfor %}
                {% else %}
                <p class="text-muted small mb-0">No comments yet</p>
                {% endif %}
            </div>
            <div class="mt-2">
                <form onsubmit="addComment(event, {{ order.id }})">
                    <div class="input-group input-group-sm">
                        <input type="text" class="form-control" placeholder="Add a comment..."
                               id="commentInput{{ order.id }}" required>
                        <button class="btn btn-primary" type="submit">
                            <i class="fa-solid fa-paper-plane"></i>
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
```

**Features:**
- Collapsible comments section
- Badge showing unread comment count
- Scrollable comment list (max-height: 200px)
- Add new comment form

**JavaScript Function:**
```javascript
function addComment(event, orderId) {
    event.preventDefault();
    const commentInput = document.getElementById(`commentInput${orderId}`);
    const comment = commentInput.value.trim();

    if (!comment) return;

    fetch(`/workforce/orders/${orderId}/add-comment/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        },
        body: JSON.stringify({ comment: comment })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            commentInput.value = '';
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Failed to add comment'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while adding comment');
    });
}
```

**Required Backend Endpoint:**
- URL: `/workforce/orders/<order_id>/add-comment/`
- Method: POST
- Request Body: `{ "comment": "comment text" }`
- Response: `{ "success": true/false, "error": "message" }`

---

### 3. Submit Task Button

**HTML Structure:**
```html
<div class="action-section">
    {% if order.task_created %}
    <button class="btn btn-outline-success" disabled>
        <i class="fa-solid fa-check-circle me-2"></i>Task Created
    </button>
    {% else %}
    <a class="btn btn-dark" hx-confirm="Are you sure you wish to Submit?"
       href="{% url 'workforce:submit_to_task' order.id %}">
        <i class="fa-solid fa-paper-plane me-2"></i>Submit Task
    </a>
    {% endif %}
</div>
```

**Features:**
- Conditional display based on `task_created` status
- HTMX confirmation dialog
- Creates delivery task from order

**Required Backend:**
- URL Name: `workforce:submit_to_task`
- URL Pattern: `/workforce/submit-task/<order_id>/`
- Method: GET or POST
- Redirects or returns success response

---

## 🚚 Delivery Task Card Features (dl_list_all.html)

### Current Implementation

**View Details Button:**
```html
<div class="action-section">
    <a href="#" class="btn btn-dark">
        <i class="fa-solid fa-eye me-2"></i>View Details
    </a>
</div>
```

**Status:** Currently placeholder - needs implementation

**Suggested Enhancement:**
Update to link to task detail page:
```html
<a href="{% url 'workforce:task_detail' dl.id %}" class="btn btn-dark">
    <i class="fa-solid fa-eye me-2"></i>View Details
</a>
```

---

## 📡 Required Backend Endpoints Summary

### 1. Publish Order to Delivery
- **URL:** `/workforce/orders/<order_id>/publish/`
- **Method:** POST
- **Request:** `{ "action": "publish" }`
- **Response:** `{ "success": boolean, "error": "string" }`

### 2. Update Order Status
- **URL:** `/workforce/orders/<order_id>/update-status/`
- **Method:** POST
- **Request:** `{ "status": "status_value" }`
- **Response:** `{ "success": boolean, "error": "string" }`

### 3. Add Comment
- **URL:** `/workforce/orders/<order_id>/add-comment/`
- **Method:** POST
- **Request:** `{ "comment": "comment text" }`
- **Response:** `{ "success": boolean, "error": "string" }`

### 4. Submit to Task
- **URL:** `/workforce/submit-task/<order_id>/`
- **Method:** GET/POST
- **URL Name:** `workforce:submit_to_task`

---

## 🔧 CSRF Token Helper

**Required in all pages with AJAX:**
```javascript
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrftoken = getCookie('csrftoken');
```

---

## 🎨 CSS Classes Reference

### Status Badge Colors
```css
.status-to_review { background: #fff3cd; color: #856404; }
.status-ready_to_pickup { background: #d1ecf1; color: #0c5460; }
.status-publish { background: #d4edda; color: #155724; }
.status-cancelled { background: #f8d7da; color: #721c24; }
.status-published { background: #cfe2ff; color: #084298; }
.status-assigned { background: #e7f3ff; color: #004085; }
.status-in_transit { background: #fff3cd; color: #856404; }
.status-delivered { background: #d1e7dd; color: #0f5132; }
.status-failed { background: #f8d7da; color: #842029; }
```

### Card Styles
```css
.task-card, .order-card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    transition: all 0.3s ease;
}

.task-card:hover, .order-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
    transform: translateY(-2px);
}
```

---

## 📝 Implementation Checklist

### For Order Cards ✅
- [x] WhatsApp integration buttons
- [x] Publish to delivery button with AJAX
- [x] Update status dropdown with AJAX
- [x] Comments section with add/view functionality
- [x] Submit task button
- [x] Status badges
- [x] Card hover effects
- [x] Responsive design

### For Delivery Task Cards 🔄
- [x] Basic card layout
- [x] Status badges
- [x] Location display
- [ ] View details link (needs backend URL)
- [ ] Quick action buttons (if needed)
- [ ] Update task status functionality
- [ ] Driver assignment dropdown

---

## 🔗 Related Files

- **Templates:**
  - `workforce/templates/workforce/parts/lists/orders_list_view.html`
  - `workforce/templates/workforce/parts/lists/dl_list_all.html`

- **Documentation:**
  - `docs/updates.md`
  - `docs/CSS_JS_ARCHITECTURE.md`

- **Static Files:**
  - `static/orders/js/orders_main.js`
  - `static/orders/css/orders_main.css`

---

## 📞 Notes for Implementation

1. **Always use CSRF token** for POST requests
2. **Provide user feedback** via alerts or toasts
3. **Reload page** after successful operations to show updated data
4. **Handle errors gracefully** with meaningful messages
5. **Test on mobile** - all buttons should be touch-friendly
6. **Use confirmation dialogs** for destructive actions

---

**Last Updated:** November 14, 2025
**Maintained By:** Development Team
