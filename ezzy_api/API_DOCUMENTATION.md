# API Documentation

## Overview
This document describes the Driver App API and DMS (Delivery Management System) API endpoints.

## Authentication
All API endpoints (except driver login) require authentication using Token Authentication.

### Getting an Authentication Token
1. Login via `/api/driver/login/` endpoint
2. The response will include a `token` field
3. Include this token in subsequent requests using the `Authorization` header:
   ```
   Authorization: Token <your-token-here>
   ```

---

## Driver App APIs

### 1. Driver Login
**POST** `/api/driver/login/`

Authenticate a driver and receive an authentication token.

**Request Body:**
```json
{
    "username": "driver_username",
    "password": "driver_password"
}
```

**Response:**
```json
{
    "token": "abc123...",
    "driver": {
        "driver_id": 1,
        "driver_code": "DRV001",
        "driver_phone": "+1234567890",
        ...
    }
}
```

---

### 2. Get Driver Profile
**GET** `/api/driver/profile/`

Get the authenticated driver's profile information.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "driver_id": 1,
    "driver_code": "DRV001",
    "driver_phone": "+1234567890",
    "driver_whatsapp": "+1234567890",
    "driver_status": "Approved",
    "driver_rating": 4.5,
    "profile": {...},
    "driver_vehicle": [...],
    "driver_document": [...]
}
```

---

### 3. Get Driver Tasks
**GET** `/api/driver/tasks/`

Get all tasks assigned to the authenticated driver.

**Headers:**
```
Authorization: Token <token>
```

**Query Parameters:**
- `status` (optional): Filter by task status (e.g., `in_transit`, `delivered`, `pending`)
- `date` (optional): Filter by date (format: `YYYY-MM-DD`)

**Response:**
```json
[
    {
        "id": 1,
        "dl_task_number": "TASK001",
        "dl_task_status": "in_transit",
        "order_number": "ORD001",
        "customer_name": "John Doe",
        "customer_phone": "+1234567890",
        "customer_address": "123 Main St",
        "cod_amount": 100,
        "dl_price": 50,
        ...
    }
]
```

---

### 4. Get Task Detail
**GET** `/api/driver/tasks/<task_id>/`

Get detailed information about a specific task.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "id": 1,
    "dl_task_number": "TASK001",
    "order": {...},
    "dl_address_update": {...},
    "driver": {...},
    ...
}
```

---

### 5. Accept Task
**POST** `/api/driver/tasks/<task_id>/accept/`

Accept a task assignment.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "message": "Task accepted successfully",
    "task": {...}
}
```

---

### 6. Reject Task
**POST** `/api/driver/tasks/<task_id>/reject/`

Reject a task assignment.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "message": "Task rejected successfully"
}
```

---

### 7. Update Task Status
**POST** `/api/driver/tasks/<task_id>/status/`

Update the status of a task.

**Headers:**
```
Authorization: Token <token>
```

**Request Body:**
```json
{
    "status": "delivered",
    "dms_status": "2"
}
```

**Response:**
```json
{
    "message": "Task status updated successfully",
    "task": {...}
}
```

---

### 8. Update Location
**POST** `/api/driver/location/`

Update driver's current location.

**Headers:**
```
Authorization: Token <token>
```

**Request Body:**
```json
{
    "latitude": 25.2048,
    "longitude": 55.2708
}
```

**Response:**
```json
{
    "message": "Location updated successfully",
    "latitude": 25.2048,
    "longitude": 55.2708,
    "timestamp": "2024-01-01T12:00:00Z"
}
```

---

### 9. Get Driver Statistics
**GET** `/api/driver/statistics/`

Get driver statistics (completed tasks, earnings, ratings, etc.).

**Headers:**
```
Authorization: Token <token>
```

**Query Parameters:**
- `start_date` (optional): Start date for statistics (format: `YYYY-MM-DD`)
- `end_date` (optional): End date for statistics (format: `YYYY-MM-DD`)

**Response:**
```json
{
    "total_tasks": 100,
    "completed_tasks": 85,
    "in_progress_tasks": 5,
    "pending_tasks": 10,
    "total_earnings": 5000,
    "driver_rating": 4.5,
    "driver_rating_count": 50
}
```

---

## DMS APIs

### 1. Get Orders List
**GET** `/api/dms/orders/`

Get list of all orders.

**Headers:**
```
Authorization: Token <token>
```

**Query Parameters:**
- `status` (optional): Filter by order status
- `business_id` (optional): Filter by business ID
- `date_from` (optional): Filter from date (format: `YYYY-MM-DD`)
- `date_to` (optional): Filter to date (format: `YYYY-MM-DD`)

**Response:**
```json
[
    {
        "id": 1,
        "order_number": "ORD001",
        "client_order_code": "CLT001",
        "business_name": "Business Name",
        "order_status": "publish",
        "customer_name": "John Doe",
        ...
    }
]
```

---

### 2. Get Order Detail
**GET** `/api/dms/orders/<order_id>/`

Get detailed information about a specific order.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "id": 1,
    "order_number": "ORD001",
    "business": {...},
    "customer_name": "John Doe",
    ...
}
```

---

### 3. Get Tasks List
**GET** `/api/dms/tasks/`

Get list of all delivery tasks.

**Headers:**
```
Authorization: Token <token>
```

**Query Parameters:**
- `status` (optional): Filter by task status
- `driver_id` (optional): Filter by driver ID
- `date_from` (optional): Filter from date (format: `YYYY-MM-DD`)
- `date_to` (optional): Filter to date (format: `YYYY-MM-DD`)

**Response:**
```json
[
    {
        "id": 1,
        "dl_task_number": "TASK001",
        "dl_task_status": "in_transit",
        "order": {...},
        "driver": {...},
        ...
    }
]
```

---

### 4. Get Task Detail
**GET** `/api/dms/tasks/<task_id>/`

Get detailed information about a specific task.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "id": 1,
    "dl_task_number": "TASK001",
    "order": {...},
    "driver": {...},
    ...
}
```

---

### 5. Assign Task
**POST** `/api/dms/tasks/assign/`

Assign a task to a driver.

**Headers:**
```
Authorization: Token <token>
```

**Request Body:**
```json
{
    "task_id": 1,
    "driver_id": 1
}
```

**Response:**
```json
{
    "message": "Task assigned successfully",
    "task": {...}
}
```

---

### 6. Update Task Status
**POST** `/api/dms/tasks/status/`

Update task status from DMS.

**Headers:**
```
Authorization: Token <token>
```

**Request Body:**
```json
{
    "task_id": 1,
    "status": "delivered",
    "dms_status": "2",
    "notes": "Optional notes"
}
```

**Response:**
```json
{
    "message": "Task status updated successfully",
    "task": {...}
}
```

---

### 7. Get Drivers List
**GET** `/api/dms/drivers/`

Get list of all drivers.

**Headers:**
```
Authorization: Token <token>
```

**Query Parameters:**
- `status` (optional): Filter by driver status (e.g., `Approved`, `Pending on Review`)

**Response:**
```json
[
    {
        "driver_id": 1,
        "driver_code": "DRV001",
        "driver_phone": "+1234567890",
        "driver_status": "Approved",
        "driver_rating": 4.5,
        "driver_name": "John Doe",
        "vehicle_type": "car"
    }
]
```

---

### 8. Get Driver Detail
**GET** `/api/dms/drivers/<driver_id>/`

Get detailed information about a specific driver.

**Headers:**
```
Authorization: Token <token>
```

**Response:**
```json
{
    "driver_id": 1,
    "driver_code": "DRV001",
    "profile": {...},
    "driver_vehicle": [...],
    "driver_document": [...],
    ...
}
```

---

### 9. Get Analytics
**GET** `/api/dms/analytics/`

Get analytics data for DMS dashboard.

**Headers:**
```
Authorization: Token <token>
```

**Query Parameters:**
- `start_date` (optional): Start date for analytics (format: `YYYY-MM-DD`, defaults to 30 days ago)
- `end_date` (optional): End date for analytics (format: `YYYY-MM-DD`, defaults to today)

**Response:**
```json
{
    "date_range": {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31"
    },
    "orders": {
        "total": 100,
        "completed": 85,
        "pending": 15
    },
    "tasks": {
        "total": 100,
        "completed": 80,
        "in_progress": 10,
        "pending": 10
    },
    "revenue": {
        "total": 50000
    },
    "drivers": {
        "active": 20,
        "with_tasks": 15
    }
}
```

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
    "error": "Error message here"
}
```

### 401 Unauthorized
```json
{
    "error": "Invalid credentials"
}
```

### 403 Forbidden
```json
{
    "error": "Driver account not approved"
}
```

### 404 Not Found
```json
{
    "error": "Resource not found"
}
```

---

## Setup Instructions

1. **Install dependencies:**
   ```bash
   pip install djangorestframework
   ```

2. **Run migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

3. **Create tokens for existing users (optional):**
   ```bash
   python manage.py shell
   >>> from rest_framework.authtoken.models import Token
   >>> from django.contrib.auth import get_user_model
   >>> User = get_user_model()
   >>> for user in User.objects.all():
   ...     Token.objects.get_or_create(user=user)
   ```

4. **Test the API:**
   - Use tools like Postman, curl, or any HTTP client
   - Make sure to include the `Authorization: Token <token>` header for authenticated endpoints

---

## Notes

- All timestamps are in UTC format
- Date formats should be `YYYY-MM-DD`
- All monetary values are in the base currency unit
- Task status values should match the choices defined in the DeliveryTask model
- DMS status values are numeric strings: '0' (Assigned), '1' (Started), '2' (Successful), etc.


