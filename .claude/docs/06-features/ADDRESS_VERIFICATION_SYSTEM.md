# Address Verification System - Complete Guide

## Overview

The Address Verification System allows customers to verify their delivery location via WhatsApp link when a new order is created. This system integrates with n8n webhooks, Google Maps API, and provides a smooth verification workflow.

## Features

✅ Automatic WhatsApp verification link sent on order creation
✅ Interactive Google Maps interface for location confirmation
✅ Secure token-based verification (valid for 7 days)
✅ Phone number validation and sanitization
✅ HMAC signature security for webhooks
✅ HTTPS enforcement in production
✅ Customer and staff verification workflow
✅ Automatic delivery task creation after staff approval

---

## System Architecture

### Workflow

```
Order Created
    ↓
Generate Verification Token
    ↓
Send WhatsApp Link via n8n
    ↓
Customer Clicks Link
    ↓
Interactive Map Opens
    ↓
Customer Confirms Location
    ↓
Status: address_verified
    ↓
Staff Reviews in Admin
    ↓
Staff Approves (Status: verified)
    ↓
Delivery Task Created Automatically
```

---

## Model Changes

### AddressVerification Model

**New Fields Added:**

```python
verification_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
token_expires_at = models.DateTimeField(blank=True, null=True)
customer_verified_at = models.DateTimeField(blank=True, null=True)
```

**New Verification Statuses:**

- `pending` - Initial state
- `address_verified` - Customer has verified location
- `verified` - Staff has approved (triggers delivery task creation)
- `invalid` - Location needs correction
- `needs_update` - Customer must re-verify

**Methods:**

```python
def is_token_expired(self):
    """Check if verification token has expired (7 days)"""

def generate_token(self):
    """Generate cryptographically secure token"""
```

---

## Implementation Details

### 1. Order Signal (orders/signals.py)

When a new order is created:

```python
# Generate verification token
token = address_verification.generate_token()
address_verification.save()

# Validate phone number
is_valid, sanitized_phone, error_msg = validate_input_phone(instance.customer_phone)

# Send WhatsApp verification link
result = send_location_verification_whatsapp(
    order=instance,
    verification_token=token,
    phone_number=sanitized_phone
)
```

### 2. WhatsApp Function (core/whatsapp_utils.py)

**Function:** `send_location_verification_whatsapp(order, verification_token, phone_number)`

**WhatsApp Message Template:**

```
📍 *EZZY Delivery - Address Verification Required*

Hello {customer_name},

Your order *{order_number}* is ready for delivery!

*Delivery Details:*
📦 Items: {item_count} item(s)
💰 COD: {amount} QR
📍 Address: {current_address}

*🔴 ACTION REQUIRED:*
Please verify your delivery location by clicking the link below:

{verification_url}

This will open a map where you can:
✅ Confirm your exact location
✅ Update address details if needed
✅ Add delivery instructions

⏰ This link will expire in 7 days.
```

**Payload Sent to n8n:**

```json
{
  "phone": "97466451589",
  "message": "Full formatted message...",
  "type": "location_verification",
  "order_id": 123,
  "order_number": "ABC123",
  "verification_token": "unique_token_here",
  "verification_url": "https://your-domain.com/orders/verify-location/token",
  "timestamp": "2025-01-13T12:00:00+00:00"
}
```

### 3. Verification View (orders/views.py)

**URL:** `/orders/verify-location/<token>/`

**Features:**

- Token validation and expiration check
- Interactive Google Maps with draggable marker
- Geocoding and reverse geocoding
- Address details form (zone, street, building)
- Delivery instructions textarea
- Location coordinates capture

**POST Data:**

```python
{
    'latitude': 25.2854,
    'longitude': 51.5310,
    'verified_address': 'Updated address string',
    'zone_number': 52,
    'street_number': 850,
    'building_number': 12,
    'notes': 'Ring doorbell twice, apartment on 2nd floor'
}
```

### 4. Verification Templates

#### verify_location.html
- Interactive Google Maps interface
- Draggable marker
- Click-to-place marker
- Auto-geocoding of original address
- Current location detection
- Address form with zone/street/building fields
- Delivery instructions

#### verification_success.html
- Success confirmation
- Order reference
- Next steps information
- WhatsApp support button

#### verification_expired.html
- Expired link message
- Order reference
- Support contact option

#### verification_error.html
- Error message display
- Support contact option

---

## Configuration

### Required Settings

Add to `settings.py`:

```python
# Base URL for generating verification links
BASE_URL = 'https://your-domain.com'

# Google Maps API Key (for interactive map)
GOOGLE_MAPS_API_KEY = 'your_google_maps_api_key'

# n8n Webhook URLs
N8N_WHATSAPP_WEBHOOK_URL = 'https://your-n8n-instance.com/webhook/whatsapp-verification'
N8N_WEBHOOK_SECRET_KEY = 'your-secure-secret-key'
```

### Google Maps API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable **Maps JavaScript API** and **Geocoding API**
3. Create API credentials
4. Add API key to settings

---

## n8n Webhook Configuration

### Webhook Node Setup

**Method:** POST
**Path:** `/webhook/whatsapp-verification`
**Authentication:** Header Auth (recommended)

### Workflow Steps

#### 1. Webhook Trigger
Receives the verification link payload

#### 2. Signature Validation (Code Node)

```javascript
// Validate HMAC signature
const incomingSignature = $node["Webhook"].json["headers"]["x-webhook-signature"];
const payload = $node["Webhook"].json["body"];
const secretKey = "YOUR_SECRET_KEY";

const crypto = require('crypto');
const message = JSON.stringify(payload, Object.keys(payload).sort());
const expectedSignature = crypto
  .createHmac('sha256', secretKey)
  .update(message)
  .digest('hex');

if (incomingSignature !== expectedSignature) {
  throw new Error('Invalid signature');
}

return { valid: true, payload };
```

#### 3. Extract Data (Code Node)

```javascript
const phone = $node["Webhook"].json["body"]["phone"];
const message = $node["Webhook"].json["body"]["message"];
const verificationUrl = $node["Webhook"].json["body"]["verification_url"];
const orderNumber = $node["Webhook"].json["body"]["order_number"];

return {
  phone,
  message,
  verificationUrl,
  orderNumber
};
```

#### 4. Send via Evolution API (HTTP Request)

**URL:** `https://your-evolution-api.com/message/sendText/your-instance`

**Headers:**
```json
{
  "Content-Type": "application/json",
  "apikey": "YOUR_EVOLUTION_API_KEY"
}
```

**Body:**
```json
{
  "number": "{{$json.phone}}",
  "text": "{{$json.message}}"
}
```

#### 5. Log Result (Set Node)

```javascript
return {
  success: true,
  phone: $json.phone,
  order_number: $json.orderNumber,
  timestamp: new Date().toISOString()
};
```

---

## Staff Workflow

### Admin Panel Process

1. **Navigate to Orders → Address Verifications**

2. **Filter by Status:**
   - `pending` - Awaiting customer verification
   - `address_verified` - Customer verified, needs staff review
   - `verified` - Staff approved, delivery task created

3. **Review Customer Verification:**
   - View verified location coordinates
   - Check updated address details
   - Read delivery instructions
   - Verify location on map (lat/lng provided)

4. **Approve Verification:**
   - Change `verification_result` from `address_verified` to `verified`
   - This triggers automatic delivery task creation
   - Delivery task appears in delivery system

### Automatic Delivery Task Creation

When staff changes status to `verified`:

```python
# orders/signals.py - order_post_save_receiver
if instance.verification_status == 'verified' and not instance.task_created:
    _create_delivery_task_from_order(instance)
```

**Created Objects:**

1. **DlAddressUpdate** - With verified coordinates
2. **DeliveryTask** - Linked to order and address
3. **Order Status Update** - task_created=True

---

## Security Features

### 1. Token Security

- **Cryptographically Secure:** Uses `secrets.token_urlsafe(32)`
- **Unique Constraint:** Database enforces token uniqueness
- **Expiration:** 7-day validity period
- **One-Time Use:** Token becomes inactive after verification

### 2. Webhook Security

- **HMAC-SHA256 Signature:** Payload integrity verification
- **HTTPS Enforcement:** Production requires SSL
- **Header Authentication:** X-Webhook-Signature validation

### 3. Input Validation

- **Phone Number Sanitization:** Removes special characters
- **Qatar Format Validation:** Ensures 974 country code
- **Length Checks:** 8-15 digit validation
- **SQL Injection Prevention:** Django ORM escaping

---

## Customer Experience

### Mobile-Optimized Interface

- Responsive design for all screen sizes
- Touch-friendly map controls
- Large, tappable buttons
- Clear instructions
- Auto-location detection

### Map Features

- **Draggable Marker:** Touch and drag to exact location
- **Click-to-Place:** Tap map to move marker
- **Current Location:** Auto-detect GPS position
- **Geocoding:** Auto-fill address from coordinates
- **Reverse Geocoding:** Get address from map click

---

## Testing

### Test Verification Flow

```python
from orders.models import Order, AddressVerification
from core.whatsapp_utils import send_location_verification_whatsapp

# Get a test order
order = Order.objects.first()

# Get or create address verification
addr_verification = AddressVerification.objects.get_or_create(
    order=order,
    defaults={'original_address': order.customer_address}
)[0]

# Generate token
token = addr_verification.generate_token()
addr_verification.save()

# Send WhatsApp link (test mode)
result = send_location_verification_whatsapp(
    order=order,
    verification_token=token,
    phone_number='97466451589'
)

print(f"Verification URL: {result['verification_url']}")
print(f"Success: {result['success']}")
```

### Test URL Pattern

```python
from django.urls import reverse

token = 'test_token_here'
url = reverse('orders:verify_location', kwargs={'token': token})
print(f"URL: {url}")
# Output: /orders/verify-location/test_token_here/
```

---

## Troubleshooting

### Issue: Verification link not sent

**Check:**
1. `N8N_WHATSAPP_WEBHOOK_URL` configured in settings
2. n8n webhook is active and accessible
3. Phone number is valid Qatar format
4. Check Django logs for errors

### Issue: Token expired

**Solution:**
- Contact support to generate new token
- Or manually update `token_expires_at` in admin

### Issue: Map not loading

**Check:**
1. `GOOGLE_MAPS_API_KEY` configured
2. Maps JavaScript API enabled in Google Cloud
3. Billing enabled on Google Cloud account
4. API key restrictions (if any) allow your domain

### Issue: Location not saving

**Check:**
1. Latitude and longitude fields populated
2. Form validation passing
3. JavaScript console for errors
4. Network requests in browser dev tools

---

## URL Patterns

```python
# Public verification URL (no login required)
path('verify-location/<str:token>/', orders_views.verify_location, name='verify_location')
```

**Example URL:**
```
https://your-domain.com/orders/verify-location/Xy9sK3mPqR8tN2vL6wA1cZ4bF7hJ0dG5/
```

---

## Database Schema

### AddressVerification Fields

| Field | Type | Description |
|-------|------|-------------|
| order | ForeignKey | Related order |
| verification_token | CharField(64) | Unique verification token |
| token_expires_at | DateTimeField | Token expiration timestamp |
| original_address | CharField(500) | Initial address from order |
| verified_address | CharField(500) | Customer-verified address |
| verification_result | CharField(50) | Status enum |
| verified_by | ForeignKey(User) | Staff who approved |
| verified_at | DateTimeField | Staff approval timestamp |
| customer_verified_at | DateTimeField | Customer verification timestamp |
| latitude | DecimalField(19,15) | GPS latitude |
| longitude | DecimalField(19,15) | GPS longitude |
| zone_number | PositiveIntegerField | Qatar zone |
| street_number | PositiveIntegerField | Street number |
| building_number | PositiveIntegerField | Building number |
| notes | TextField | Delivery instructions |

---

## Environment Variables

```bash
# .env file
BASE_URL=https://your-domain.com
GOOGLE_MAPS_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXX
N8N_WHATSAPP_WEBHOOK_URL=https://your-n8n.com/webhook/whatsapp-verification
N8N_WEBHOOK_SECRET_KEY=your-secret-key-here
```

---

## Production Checklist

- [ ] `BASE_URL` configured with production domain
- [ ] `GOOGLE_MAPS_API_KEY` configured and active
- [ ] Maps JavaScript API enabled
- [ ] Geocoding API enabled
- [ ] n8n webhook URL configured (HTTPS)
- [ ] n8n webhook secret key set
- [ ] HMAC signature validation enabled in n8n
- [ ] Evolution API credentials configured
- [ ] Test verification flow end-to-end
- [ ] Test with actual WhatsApp number
- [ ] Verify map loads correctly
- [ ] Test location submission
- [ ] Verify staff approval workflow
- [ ] Test delivery task creation
- [ ] Check error pages render correctly
- [ ] Verify expired link handling

---

## Support & Maintenance

### Monitoring

Monitor these metrics:
- Verification link send success rate
- Customer verification completion rate
- Token expiration rate
- Staff approval time
- Delivery task creation success

### Logs

Key log locations:
```python
# orders/signals.py
logger.info("Location verification link sent for order {order_number}")
logger.error("Error sending location verification: {error}")

# orders/views.py
logger.error("Error in location verification: {error}")
```

---

## Future Enhancements

Potential improvements:
- SMS fallback if WhatsApp fails
- Multiple verification attempts
- Location history tracking
- Automated address validation against Qatar postal system
- Driver app integration for real-time location updates
- Customer notification on staff approval
- Bulk verification link resend
- Analytics dashboard for verification metrics

---

## Changelog

### Version 1.0 (2025-01-13)
- Initial implementation
- WhatsApp verification link integration
- Google Maps interactive verification
- Token-based security
- Staff approval workflow
- Automatic delivery task creation

---

## Related Documentation

- [n8n Webhook Setup Guide](./N8N_WEBHOOK_SETUP.md)
- [WhatsApp Integration Security](./N8N_WEBHOOK_SETUP.md#security-best-practices)
- Order Management System Documentation
- Delivery Task System Documentation

---

## Contact

For issues or questions:
- Django Code: Check [orders/views.py](../orders/views.py) - `verify_location` function
- WhatsApp Utils: Check [core/whatsapp_utils.py](../core/whatsapp_utils.py) - `send_location_verification_whatsapp`
- Signal Handler: Check [orders/signals.py](../orders/signals.py) - `order_post_save_receiver`
