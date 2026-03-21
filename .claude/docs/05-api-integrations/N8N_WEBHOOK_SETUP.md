# n8n WhatsApp Webhook Integration - Setup Guide

## Overview

This document outlines the setup and configuration for secure WhatsApp verification using n8n webhooks with the EZZY Delivery platform.

## Security Features Implemented

### 1. HMAC Signature Verification
All webhook requests include an HMAC-SHA256 signature for payload integrity verification.

### 2. HTTPS Enforcement
Production environments require HTTPS for all webhook communications.

### 3. Input Validation
Phone numbers are validated and sanitized before processing.

### 4. Token Expiry
Verification codes expire after 10 minutes.

### 5. Rate Limiting
Maximum 3 verification attempts per code.

---

## Django Settings Configuration

Add the following to your `settings.py`:

```python
# n8n WhatsApp Webhook Configuration
N8N_WHATSAPP_WEBHOOK_URL = 'https://your-n8n-instance.com/webhook/whatsapp-verification'
N8N_PASSWORD_RESET_COMPLETE_WEBHOOK_URL = 'https://your-n8n-instance.com/webhook/password-reset-complete'
N8N_WEBHOOK_SECRET_KEY = 'your-secure-secret-key-here'  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Generating Secure Secret Keys

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## n8n Workflow Setup

### Webhook 1: WhatsApp Verification Code Sender

#### Step 1: Create Webhook Node
- **Method**: POST
- **Path**: `/webhook/whatsapp-verification`
- **Authentication**: Header Auth (recommended)

#### Step 2: Validate HMAC Signature (Security Node)

Add a **Code** node to validate the webhook signature:

```javascript
// Get the incoming payload and signature
const incomingSignature = $node["Webhook"].json["headers"]["x-webhook-signature"];
const payload = $node["Webhook"].json["body"];
const secretKey = "YOUR_SECRET_KEY_HERE"; // Store in environment variables

// Calculate expected signature
const crypto = require('crypto');
const message = JSON.stringify(payload, Object.keys(payload).sort());
const expectedSignature = crypto
  .createHmac('sha256', secretKey)
  .update(message)
  .digest('hex');

// Validate
if (incomingSignature !== expectedSignature) {
  throw new Error('Invalid signature - request rejected');
}

return { valid: true, payload };
```

#### Step 3: Extract Payload Data

```javascript
// Extract verification data
const phone = $node["Webhook"].json["body"]["phone"];
const message = $node["Webhook"].json["body"]["message"];
const code = $node["Webhook"].json["body"]["code"];
const type = $node["Webhook"].json["body"]["type"];
const timestamp = $node["Webhook"].json["body"]["timestamp"];

return {
  phone,
  message,
  code,
  type,
  timestamp
};
```

#### Step 4: Send via Evolution API (HTTP Request Node)

**URL**: `https://your-evolution-api.com/message/sendText/your-instance-name`

**Method**: POST

**Headers**:
```json
{
  "Content-Type": "application/json",
  "apikey": "YOUR_EVOLUTION_API_KEY"
}
```

**Body**:
```json
{
  "number": "{{$json.phone}}",
  "text": "{{$json.message}}"
}
```

#### Step 5: Log Success/Failure

Add a **Set** node to log the result:

```javascript
return {
  success: true,
  phone: $json.phone,
  type: $json.type,
  timestamp: new Date().toISOString(),
  evolution_response: $json
};
```

---

### Webhook 2: Password Reset Completion Notification

#### Step 1: Create Webhook Node
- **Method**: POST
- **Path**: `/webhook/password-reset-complete`
- **Authentication**: Header Auth

#### Step 2: Validate HMAC Signature
(Same as Webhook 1 Step 2)

#### Step 3: Extract Payload

```javascript
const phone = $node["Webhook"].json["body"]["phone"];
const message = $node["Webhook"].json["body"]["message"];
const userId = $node["Webhook"].json["body"]["user_id"];
const username = $node["Webhook"].json["body"]["username"];
const timestamp = $node["Webhook"].json["body"]["timestamp"];

return {
  phone,
  message,
  userId,
  username,
  timestamp
};
```

#### Step 4: Send Notification via Evolution API
(Same configuration as Webhook 1 Step 4)

#### Step 5: Optional - Log to Database

Add an **HTTP Request** or **Database** node to log password reset events:

```javascript
return {
  event: 'password_reset_complete',
  user_id: $json.userId,
  username: $json.username,
  timestamp: $json.timestamp,
  phone: $json.phone
};
```

---

## Webhook Payload Formats

### Verification Code Request

```json
{
  "phone": "97466451589",
  "message": "🔐 *EZZY Delivery - Password Reset*\n\nYour password reset verification code is:\n\n*123456*\n\nThis code will expire in 10 minutes.\n\nIf you didn't request this, please ignore this message.",
  "code": "123456",
  "type": "password_reset",
  "timestamp": "2025-01-13T10:30:00+00:00"
}
```

### Password Reset Completion

```json
{
  "phone": "97466451589",
  "message": "✅ *EZZY Delivery - Password Reset Successful*\n\nYour password has been successfully reset.\n\nUsername: john_doe\nTime: 2025-01-13 10:35:00\n\nIf you did not perform this action, please contact support immediately.",
  "type": "password_reset_complete",
  "user_id": 42,
  "username": "john_doe",
  "timestamp": "2025-01-13T10:35:00+00:00"
}
```

---

## Evolution API Configuration

### Required Settings

1. **Instance Name**: Your Evolution API instance identifier
2. **API Key**: Authentication token for Evolution API
3. **Base URL**: Your Evolution API endpoint

### Example Evolution API Request

```bash
curl -X POST https://your-evolution-api.com/message/sendText/your-instance-name \
  -H "Content-Type: application/json" \
  -H "apikey: YOUR_API_KEY" \
  -d '{
    "number": "97466451589",
    "text": "Your verification code is: 123456"
  }'
```

---

## Security Best Practices

### 1. Environment Variables
Store all sensitive credentials in environment variables:

```python
# In settings.py
import os

N8N_WHATSAPP_WEBHOOK_URL = os.getenv('N8N_WHATSAPP_WEBHOOK_URL')
N8N_PASSWORD_RESET_COMPLETE_WEBHOOK_URL = os.getenv('N8N_PASSWORD_RESET_COMPLETE_WEBHOOK_URL')
N8N_WEBHOOK_SECRET_KEY = os.getenv('N8N_WEBHOOK_SECRET_KEY')
```

### 2. HTTPS Only
Never use HTTP in production. All webhooks must use HTTPS.

### 3. Firewall Rules
Restrict webhook access to your Django server's IP address in n8n.

### 4. Rate Limiting
Implement rate limiting in n8n to prevent abuse:
- Max 5 requests per minute per phone number
- Max 20 requests per hour per IP

### 5. Webhook Authentication
Use n8n's built-in Header Auth:
- Header Name: `X-Auth-Token`
- Header Value: Your secure token

### 6. Monitoring & Alerts
Set up monitoring for:
- Failed webhook requests
- Invalid signature attempts
- Unusual request patterns

---

## Testing

### Test Verification Code Sending

```python
from core.whatsapp_utils import send_whatsapp_verification

result = send_whatsapp_verification(
    phone_number='97466451589',
    verification_code='123456',
    verification_type='password_reset'
)

print(result)
# {'success': True, 'code': '123456', 'message': 'Verification code sent successfully'}
```

### Test Password Reset Notification

```python
from core.whatsapp_utils import send_password_reset_completion_notification
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username='testuser')

result = send_password_reset_completion_notification(
    user=user,
    phone_number='97466451589'
)

print(result)
# {'success': True, 'status_code': 200}
```

### Test Input Validation

```python
from core.whatsapp_utils import validate_input_phone

# Valid cases
is_valid, phone, error = validate_input_phone('66451589')
print(is_valid, phone)  # True, '97466451589'

is_valid, phone, error = validate_input_phone('97466451589')
print(is_valid, phone)  # True, '97466451589'

# Invalid cases
is_valid, phone, error = validate_input_phone('123')
print(is_valid, error)  # False, 'Phone number too short'
```

---

## Troubleshooting

### Issue: Webhook URL not configured
**Error**: `N8N webhook URL not configured`

**Solution**: Add `N8N_WHATSAPP_WEBHOOK_URL` to settings.py

### Issue: Invalid signature
**Error**: `Invalid signature - request rejected`

**Solution**:
1. Verify `N8N_WEBHOOK_SECRET_KEY` matches in both Django and n8n
2. Ensure payload is not modified between Django and n8n

### Issue: HTTPS required in production
**Error**: `Webhook URL must use HTTPS in production`

**Solution**: Use HTTPS URL for webhooks or set `DEBUG = True` for testing

### Issue: Phone number validation fails
**Error**: `Invalid Qatar phone number format`

**Solution**:
- Use format: `66451589` (8 digits) or `97466451589` (with country code)
- Remove spaces, dashes, and special characters

---

## Extending to Other Operations

The WhatsApp verification system can be extended to other operations:

### Phone Number Add/Update

```python
from core.whatsapp_utils import create_verification

result = create_verification(
    user=request.user,
    phone_number='97466451589',
    verification_type='phone_add'  # or 'phone_update'
)
```

### Account Verification

```python
result = create_verification(
    user=request.user,
    phone_number='97466451589',
    verification_type='account_verify'
)
```

---

## Production Checklist

- [ ] HTTPS enabled for all webhook URLs
- [ ] `N8N_WEBHOOK_SECRET_KEY` generated and configured
- [ ] Evolution API credentials configured
- [ ] HMAC signature validation enabled in n8n
- [ ] Rate limiting configured in n8n
- [ ] Firewall rules configured to restrict webhook access
- [ ] Monitoring and alerting set up
- [ ] Error logging configured
- [ ] Test verification flow end-to-end
- [ ] Test password reset completion notification
- [ ] Verify SSL certificate validity

---

## Support

For issues or questions:
- Django Code: Check [core/whatsapp_utils.py](../core/whatsapp_utils.py)
- Views: Check [core/password_reset_views.py](../core/password_reset_views.py)
- Models: Check [core/models.py](../core/models.py) - `WhatsAppVerification` model

---

## Changelog

### Version 1.0 (2025-01-13)
- Initial implementation
- HMAC signature validation
- HTTPS enforcement
- Input validation and sanitization
- Password reset completion notification
- Secure token generation
