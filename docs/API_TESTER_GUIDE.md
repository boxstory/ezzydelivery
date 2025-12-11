# EzzyDelivery API Tester - User Guide

**URL:** `http://localhost:8000/api/tester/` (or your domain + `/api/tester/`)

---

## Overview

The API Tester is a user-friendly web interface that allows clients to test and interact with the EzzyDelivery REST API without using tools like Postman or cURL.

![API Tester Interface](https://via.placeholder.com/800x400?text=API+Tester+Interface)

---

## Features

✅ **Interactive Forms** - Easy-to-use forms for all API operations
✅ **Real-time Testing** - Instant API responses
✅ **Auto-generated cURL** - Copy-paste ready commands
✅ **Visual Feedback** - Color-coded status badges
✅ **Request Details** - See exactly what's being sent
✅ **No Installation** - Browser-based, no software needed

---

## Getting Started

### 1. Access the API Tester

Navigate to: `http://localhost:8000/api/tester/`

> **Note:** You must be logged in to access the API Tester

### 2. Get Your API Token

Before using the API, you need an authentication token:

#### Option A: Use Django Admin
1. Go to `http://localhost:8000/admin/`
2. Navigate to **Authentication and Authorization** → **Tokens**
3. Find or create a token for your user
4. Copy the token key

#### Option B: Use Python Shell
```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

# Get your user
user = User.objects.get(username='your_username')

# Get or create token
token, created = Token.objects.get_or_create(user=user)
print(f"Your token: {token.key}")
```

---

## Using the API Tester

### Tab 1: Create Order

Create new delivery orders for your business.

#### Required Fields:
- **Authentication Token** - Your API token
- **Client ID** - The ID of the Business (customer)
- **Delivery Address** - Full delivery address

#### Optional Fields:
- **Pickup Location ID** - Pickup location for the order

#### Steps:
1. Click on the **"Create Order"** tab
2. Enter your authentication token
3. Fill in the Business ID (e.g., `1`)
4. Enter the delivery address
5. Optionally enter pickup location ID
6. Click **"📦 Create Order"**

#### Example Response:
```json
{
  "message": "Order created successfully",
  "order": {
    "id": 123,
    "order_number": "ORD123",
    "status": "pending"
  }
}
```

---

### Tab 2: List Orders

View and filter your orders.

#### Fields:
- **Authentication Token** - Your API token
- **Order Status** - Filter by status (optional)
- **Search** - Search by order number or Business name (optional)
- **Limit** - Number of results to return (default: 10)

#### Available Status Filters:
- All Statuses
- Pending
- Confirmed
- In Transit
- Delivered
- Cancelled

#### Steps:
1. Click on the **"List Orders"** tab
2. Enter your authentication token
3. Optionally select a status filter
4. Optionally enter search term
5. Set the number of results
6. Click **"📋 List Orders"**

#### Example Response:
```json
{
  "count": 10,
  "orders": [
    {
      "id": 1,
      "order_number": "ORD001",
      "client_name": "John Doe",
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

---

### Tab 3: Create Client

Add new clients (customers) to your business.

#### Required Fields:
- **Authentication Token** - Your API token
- **Client Name** - Full name of the client
- **Phone Number** - Client's phone number

#### Optional Fields:
- **Email** - Client's email address
- **Address** - Client's default address

#### Steps:
1. Click on the **"Create Client"** tab
2. Enter your authentication token
3. Enter Business name
4. Enter phone number (format: +1234567890)
5. Optionally enter email and address
6. Click **"👤 Create Client"**

#### Example Response:
```json
{
  "message": "Client created successfully",
  "client": {
    "id": 5,
    "name": "Jane Smith",
    "phone": "+9876543210"
  }
}
```

---

### Tab 4: Dashboard Stats

View your business statistics and metrics.

#### Fields:
- **Authentication Token** - Your API token
- **Period (Days)** - Number of days to analyze (default: 30)

#### Steps:
1. Click on the **"Dashboard Stats"** tab
2. Enter your authentication token
3. Optionally change the period in days
4. Click **"📊 Get Stats"**

#### Example Response:
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

---

## Understanding the Response

### Response Section

The right panel shows three key sections:

#### 1. HTTP Status Badge
- **Green (200, 201)** - Success
- **Red (400, 401, 403, 404)** - Error

Common Status Codes:
- `200 OK` - Request successful
- `201 Created` - Resource created
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Invalid token
- `404 Not Found` - Resource not found

#### 2. Response Body
Shows the JSON response from the API with syntax highlighting.

#### 3. cURL Command
Ready-to-use cURL command that you can copy and run in terminal:

```bash
curl -X POST "http://localhost:8000/api/business/orders/" \
  -H "Authorization: Token your_token_here" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 1,
    "delivery_address": "123 Main St"
  }'
```

#### 4. Request Details
Shows what was sent to the API:
- HTTP Method (GET, POST, PUT, DELETE)
- Full URL
- Headers
- Request body (if applicable)

---

## Common Errors and Solutions

### Error: "401 Unauthorized"
**Cause:** Invalid or missing authentication token

**Solution:**
1. Check that your token is correct
2. Ensure there are no extra spaces
3. Generate a new token if needed

### Error: "404 Not Found"
**Cause:** Resource doesn't exist or wrong ID

**Solution:**
1. Verify the Business ID exists
2. Check the order ID is correct
3. Ensure the resource belongs to your business

### Error: "400 Bad Request"
**Cause:** Invalid input data

**Solution:**
1. Check required fields are filled
2. Verify data format (e.g., phone number format)
3. Read the error message in the response

### Error: "Business not found"
**Cause:** Your user account is not associated with a business

**Solution:**
1. Contact admin to associate your account with a business
2. Ensure you're logged in with the correct account

---

## Tips and Best Practices

### 1. Save Your Token
Store your API token in a secure location. You'll use it for all API requests.

### 2. Test with Small Data First
When testing, start with one or two orders before bulk operations.

### 3. Use the cURL Commands
Copy the generated cURL commands to automate tasks or integrate with scripts.

### 4. Check Response Status
Always check the HTTP status code before assuming success.

### 5. Search Before Creating
Use the "List Orders" feature to check if an order already exists.

### 6. Create Clients First
Before creating orders, ensure clients are created in the system.

---

## Integration Examples

### Example 1: Automated Order Creation Script

```bash
#!/bin/bash
TOKEN="your_token_here"
CLIENT_ID=1

curl -X POST "http://localhost:8000/api/business/orders/" \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": $CLIENT_ID,
    \"delivery_address\": \"123 Main St\",
    \"pickup_location_id\": 1
  }"
```

### Example 2: Python Integration

```python
import requests

TOKEN = "your_token_here"
BASE_URL = "http://localhost:8000/api"

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}

# Create order
data = {
    "client_id": 1,
    "delivery_address": "123 Main St",
    "pickup_location_id": 1
}

response = requests.post(
    f"{BASE_URL}/business/orders/",
    headers=headers,
    json=data
)

print(response.json())
```

### Example 3: JavaScript/Node.js Integration

```javascript
const axios = require('axios');

const TOKEN = 'your_token_here';
const BASE_URL = 'http://localhost:8000/api';

const createOrder = async () => {
  try {
    const response = await axios.post(
      `${BASE_URL}/business/orders/`,
      {
        client_id: 1,
        delivery_address: '123 Main St',
        pickup_location_id: 1
      },
      {
        headers: {
          'Authorization': `Token ${TOKEN}`,
          'Content-Type': 'application/json'
        }
      }
    );

    console.log(response.data);
  } catch (error) {
    console.error('Error:', error.response.data);
  }
};

createOrder();
```

---

## Advanced Features

### Pagination

When listing orders, use `limit` and `offset` for pagination:

```bash
# Page 1 (first 10 orders)
GET /api/business/orders/?limit=10&offset=0

# Page 2 (next 10 orders)
GET /api/business/orders/?limit=10&offset=10

# Page 3 (next 10 orders)
GET /api/business/orders/?limit=10&offset=20
```

### Combined Filters

Combine multiple filters for precise results:

```bash
# Pending orders for a specific client
GET /api/business/orders/?status=pending&search=john

# Last 5 delivered orders
GET /api/business/orders/?status=delivered&limit=5
```

---

## Keyboard Shortcuts

- **Tab** - Navigate between fields
- **Enter** - Submit form (when in form field)
- **Ctrl+A** - Select all (in response box)
- **Ctrl+C** - Copy selected text

---

## Mobile Usage

The API Tester is fully responsive and works on:
- ✅ Desktop browsers
- ✅ Tablets
- ✅ Mobile phones

On mobile devices:
1. Forms stack vertically for easier input
2. Response boxes scroll horizontally for long JSON
3. Buttons are touch-friendly

---

## Troubleshooting

### Issue: Page won't load
**Solution:**
- Check that you're logged in
- Clear browser cache
- Try a different browser

### Issue: Forms not submitting
**Solution:**
- Check browser console for JavaScript errors
- Ensure all required fields are filled
- Verify your internet connection

### Issue: Response not showing
**Solution:**
- Check browser console for errors
- Verify the API endpoint is running
- Test with a simple GET request first

---

## Security Notes

⚠️ **Important Security Guidelines:**

1. **Never share your API token** - It's like a password
2. **Use HTTPS in production** - Encrypt all traffic
3. **Regenerate tokens periodically** - Better security
4. **Don't commit tokens to git** - Keep them secret
5. **Use environment variables** - For production deployments

---

## Support

Need help? Check these resources:

1. **API Documentation** - See [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
2. **API Improvements** - See [API_IMPROVEMENTS_SUMMARY.md](API_IMPROVEMENTS_SUMMARY.md)
3. **Contact Support** - Check the main documentation

---

## Changelog

### Version 1.0 (November 13, 2025)
- ✅ Initial release
- ✅ Create Order functionality
- ✅ List Orders with filters
- ✅ Create Business functionality
- ✅ Dashboard Statistics
- ✅ Real-time API testing
- ✅ Auto-generated cURL commands

---

**Happy Testing!** 🚀

For more information, visit the complete [API Documentation](API_DOCUMENTATION.md).
