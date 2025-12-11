# EzzyDelivery REST API Documentation

**Version:** 1.0
**Base URL:** `/api/`
**Authentication:** Token-based authentication required for all endpoints

---

## Table of Contents

1. [Authentication](#authentication)
2. [Driver APIs](#driver-apis)
3. [DMS (Delivery Management System) APIs](#dms-apis)
4. [Business APIs](#business-apis)
5. [E-commerce Integration APIs](#e-commerce-integration-apis)
6. [Webhook APIs](#webhook-apis)
7. [Common Response Formats](#common-response-formats)

---

## Authentication

All API endpoints require authentication using Token-based authentication.

### Get Authentication Token

**Endpoint:** `POST /api/driver/login/`

**Request Body:**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**Response:**
```json
{
  "token": "your_auth_token_here",
  "user_id": 123,
  "username": "your_username"
}
```

### Using the Token

Include the token in the Authorization header for all subsequent requests:

```
Authorization: Token your_auth_token_here
```

---

## Driver APIs

APIs for driver mobile applications.

### 1. Get Driver Profile

**Endpoint:** `GET /api/driver/profile/`

**Response:**
```json
{
  "driver_id": "DRV001",
  "driver_name": "John Doe",
  "driver_phone": "+1234567890",
  "driver_email": "john@example.com",
  "status": "active"
}
```

### 2. Get Driver Tasks

**Endpoint:** `GET /api/driver/tasks/`

**Query Parameters:**
- `status` (optional): Filter by task status (`pending`, `in_transit`, `delivered`)
- `date` (optional): Filter by date (format: `YYYY-MM-DD`)

**Response:**
```json
[
  {
    "id": 1,
    "task_number": "TSK001",
    "order_number": "ORD001",
    "client_name": "Customer Name",
    "delivery_address": "123 Main St",
    "status": "pending",
    "task_date": "2025-11-13",
    "created_at": "2025-11-13T10:00:00Z"
  }
]
```

### 3. Get Task Details

**Endpoint:** `GET /api/driver/tasks/{task_id}/`

**Response:**
```json
{
  "id": 1,
  "task_number": "TSK001",
  "order": {
    "order_number": "ORD001",
    "client": {
      "name": "Customer Name",
      "phone": "+1234567890"
    }
  },
  "delivery_address": "123 Main St",
  "status": "pending",
  "notes": "Handle with care"
}
```

### 4. Accept Task

**Endpoint:** `POST /api/driver/tasks/{task_id}/accept/`

**Response:**
```json
{
  "message": "Task accepted successfully",
  "task": {
    "id": 1,
    "task_number": "TSK001",
    "status": "in_transit"
  }
}
```

### 5. Update Task Status

**Endpoint:** `POST /api/driver/tasks/{task_id}/status/`

**Request Body:**
```json
{
  "status": "delivered",
  "notes": "Delivered successfully"
}
```

**Response:**
```json
{
  "message": "Task status updated successfully",
  "task_id": 1,
  "new_status": "delivered"
}
```

### 6. Update Driver Location

**Endpoint:** `POST /api/driver/location/`

**Request Body:**
```json
{
  "latitude": 25.2048,
  "longitude": 55.2708,
  "accuracy": 10
}
```

**Response:**
```json
{
  "message": "Location updated successfully"
}
```

### 7. Get Driver Statistics

**Endpoint:** `GET /api/driver/statistics/`

**Response:**
```json
{
  "total_tasks": 150,
  "completed_tasks": 145,
  "pending_tasks": 5,
  "completion_rate": 96.67
}
```

---

## DMS (Delivery Management System) APIs

APIs for delivery management system operations.

### 1. Get Orders List

**Endpoint:** `GET /api/dms/orders/`

**Query Parameters:**
- `status` (optional): Filter by order status
- `business_id` (optional): Filter by business
- `date_from` (optional): Filter from date (format: `YYYY-MM-DD`)
- `date_to` (optional): Filter to date (format: `YYYY-MM-DD`)

**Response:**
```json
[
  {
    "id": 1,
    "order_number": "ORD001",
    "business": {
      "id": 1,
      "name": "Business Name"
    },
    "client": {
      "name": "Customer Name",
      "phone": "+1234567890"
    },
    "order_status": "pending",
    "created_at": "2025-11-13T10:00:00Z"
  }
]
```

### 2. Get Order Details

**Endpoint:** `GET /api/dms/orders/{order_id}/`

**Response:**
```json
{
  "id": 1,
  "order_number": "ORD001",
  "business": {
    "id": 1,
    "name": "Business Name"
  },
  "client": {
    "id": 1,
    "name": "Customer Name",
    "phone": "+1234567890",
    "email": "customer@example.com"
  },
  "delivery_address": "123 Main St",
  "order_status": "pending",
  "created_at": "2025-11-13T10:00:00Z"
}
```

### 3. Get Tasks List

**Endpoint:** `GET /api/dms/tasks/`

**Query Parameters:**
- `status` (optional): Filter by task status
- `driver_id` (optional): Filter by driver
- `date_from` (optional): Filter from date
- `date_to` (optional): Filter to date

**Response:**
```json
[
  {
    "id": 1,
    "task_number": "TSK001",
    "order_number": "ORD001",
    "driver": {
      "driver_id": "DRV001",
      "name": "John Doe"
    },
    "status": "in_transit",
    "task_date": "2025-11-13"
  }
]
```

### 4. Get Drivers List

**Endpoint:** `GET /api/dms/drivers/`

**Response:**
```json
[
  {
    "driver_id": "DRV001",
    "driver_name": "John Doe",
    "driver_phone": "+1234567890",
    "status": "active",
    "current_location": {
      "latitude": 25.2048,
      "longitude": 55.2708
    }
  }
]
```

### 5. Assign Task

**Endpoint:** `POST /api/dms/tasks/assign/`

**Request Body:**
```json
{
  "task_id": 1,
  "driver_id": "DRV001"
}
```

**Response:**
```json
{
  "message": "Task assigned successfully",
  "task_id": 1,
  "driver_id": "DRV001"
}
```

---

## Business APIs

APIs for business operations and management.

### 1. Get Dashboard Statistics

**Endpoint:** `GET /api/business/dashboard/`

**Query Parameters:**
- `days` (optional): Number of days for recent statistics (default: 30)

**Response:**
```json
{
  "business_id": 1,
  "business_name": "My Business",
  "period_days": 30,
  "orders": {
    "total": 500,
    "pending": 25,
    "completed": 450,
    "cancelled": 25,
    "recent": 100
  },
  "tasks": {
    "total": 500,
    "active": 30,
    "completed": 470
  },
  "clients": {
    "total": 250
  }
}
```

### 2. List/Create Orders

**Endpoint:** `GET /api/business/orders/` or `POST /api/business/orders/`

#### GET - List Orders

**Query Parameters:**
- `status` (optional): Filter by order status
- `search` (optional): Search by order number or Business name
- `limit` (optional): Number of results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "count": 50,
  "orders": [
    {
      "id": 1,
      "order_number": "ORD001",
      "client_name": "Customer Name",
      "client_phone": "+1234567890",
      "delivery_address": "123 Main St",
      "order_status": "pending",
      "order_date": "2025-11-13",
      "created_at": "2025-11-13T10:00:00Z",
      "total_amount": "150.00"
    }
  ]
}
```

#### POST - Create Order

**Request Body:**
```json
{
  "client_id": 1,
  "delivery_address": "123 Main St",
  "pickup_location_id": 1
}
```

**Response:**
```json
{
  "message": "Order created successfully",
  "order": {
    "id": 1,
    "order_number": "ORD001",
    "status": "pending"
  }
}
```

### 3. Get/Update/Delete Order

**Endpoint:** `GET/PUT/DELETE /api/business/orders/{order_id}/`

#### GET - Get Order Details

**Response:**
```json
{
  "id": 1,
  "order_number": "ORD001",
  "client": {
    "id": 1,
    "name": "Customer Name",
    "phone": "+1234567890",
    "email": "customer@example.com"
  },
  "delivery_address": "123 Main St",
  "pickup_location": {
    "id": 1,
    "name": "Store Location"
  },
  "order_status": "pending",
  "order_date": "2025-11-13",
  "created_at": "2025-11-13T10:00:00Z",
  "notes": "Handle with care"
}
```

#### PUT - Update Order

**Request Body:**
```json
{
  "delivery_address": "456 New St",
  "order_status": "confirmed",
  "order_notes": "Updated instructions"
}
```

**Response:**
```json
{
  "message": "Order updated successfully",
  "order_id": 1
}
```

#### DELETE - Delete Order

**Response:**
```json
{
  "message": "Order deleted successfully"
}
```

### 4. List/Create Clients

**Endpoint:** `GET /api/business/clients/` or `POST /api/business/clients/`

#### GET - List Clients

**Query Parameters:**
- `search` (optional): Search by name, phone, or email
- `limit` (optional): Number of results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "count": 50,
  "clients": [
    {
      "id": 1,
      "name": "Customer Name",
      "phone": "+1234567890",
      "email": "customer@example.com",
      "address": "123 Main St",
      "created_at": "2025-11-13T10:00:00Z"
    }
  ]
}
```

#### POST - Create Client

**Request Body:**
```json
{
  "name": "Customer Name",
  "phone": "+1234567890",
  "email": "customer@example.com",
  "address": "123 Main St"
}
```

**Response:**
```json
{
  "message": "Client created successfully",
  "client": {
    "id": 1,
    "name": "Customer Name",
    "phone": "+1234567890"
  }
}
```

### 5. Get Business Tasks

**Endpoint:** `GET /api/business/tasks/`

**Query Parameters:**
- `status` (optional): Filter by task status
- `driver_id` (optional): Filter by driver
- `limit` (optional): Number of results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "count": 50,
  "tasks": [
    {
      "id": 1,
      "task_number": "TSK001",
      "order_number": "ORD001",
      "client_name": "Customer Name",
      "delivery_address": "123 Main St",
      "status": "in_transit",
      "driver": {
        "id": "DRV001",
        "name": "John Doe"
      },
      "task_date": "2025-11-13",
      "created_at": "2025-11-13T10:00:00Z"
    }
  ]
}
```

### 6. Get Pickup Locations

**Endpoint:** `GET /api/business/pickup-locations/`

**Response:**
```json
{
  "count": 5,
  "locations": [
    {
      "id": 1,
      "name": "Main Store",
      "address": "123 Store St",
      "zone": "Zone A",
      "latitude": 25.2048,
      "longitude": 55.2708
    }
  ]
}
```

---

## E-commerce Integration APIs

### 1. Import Shopify Orders

**Endpoint:** `POST /api/integrations/shopify/import/`

**Request Body:**
```json
{
  "store_url": "your-store.myshopify.com",
  "api_key": "your_api_key",
  "access_token": "your_access_token"
}
```

**Response:**
```json
{
  "message": "Orders imported successfully",
  "imported_count": 25,
  "failed_count": 0
}
```

### 2. Import WooCommerce Orders

**Endpoint:** `POST /api/integrations/woocommerce/import/`

**Request Body:**
```json
{
  "store_url": "https://your-store.com",
  "consumer_key": "ck_xxxxxx",
  "consumer_secret": "cs_xxxxxx"
}
```

**Response:**
```json
{
  "message": "Orders imported successfully",
  "imported_count": 30,
  "failed_count": 2
}
```

---

## Webhook APIs

### 1. Create Webhook Endpoint

**Endpoint:** `POST /api/webhooks/endpoints/create/`

**Request Body:**
```json
{
  "url": "https://your-domain.com/webhook",
  "events": ["task.completed", "task.status_updated"],
  "active": true
}
```

**Response:**
```json
{
  "message": "Webhook endpoint created successfully",
  "webhook_id": 1,
  "secret": "whsec_xxxxxx"
}
```

### 2. List Webhook Endpoints

**Endpoint:** `GET /api/webhooks/endpoints/`

**Response:**
```json
[
  {
    "id": 1,
    "url": "https://your-domain.com/webhook",
    "events": ["task.completed", "task.status_updated"],
    "active": true,
    "created_at": "2025-11-13T10:00:00Z"
  }
]
```

---

## Common Response Formats

### Success Response

```json
{
  "message": "Operation successful",
  "data": {}
}
```

### Error Response

```json
{
  "error": "Error message description",
  "code": "ERROR_CODE"
}
```

### HTTP Status Codes

- `200 OK` - Request successful
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

---

## Rate Limiting

API requests are limited to:
- **100 requests per minute** per user
- **1000 requests per hour** per user

Exceeding these limits will result in a `429 Too Many Requests` response.

---

## Best Practices

1. **Always use HTTPS** for API requests
2. **Store authentication tokens securely** - never expose in client-side code
3. **Use pagination** for large datasets (`limit` and `offset` parameters)
4. **Implement proper error handling** for all API calls
5. **Use webhook events** instead of polling for real-time updates
6. **Cache responses** when appropriate to reduce API calls
7. **Validate input** before making API requests

---

## Support

For API support or questions:
- **Documentation:** See `/docs/` directory
- **Issues:** Report issues in the project repository

---

**Last Updated:** November 13, 2025
**API Version:** 1.0
