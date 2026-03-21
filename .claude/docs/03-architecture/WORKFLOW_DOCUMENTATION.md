# Complete Order Verification & DMS Push Workflow Documentation

## Overview
This document describes the complete workflow from order creation to DMS push across all apps in the project.

## System Architecture

### Apps Involved:
1. **client** - Business/client management, order creation
2. **orders** - Order management, verification tracking
3. **workforce** - Staff verification workflow
4. **delivery** - Delivery task management
5. **ezzy_api** - API endpoints, DMS integration
6. **fleet** - Driver management
7. **core** - User profiles
8. **product** - Product management

## Complete Workflow

### 1. Order Creation (Client → Orders App)

**Entry Points:**
- Business creates order via web form (`orders/views.py:add_order`)
- API endpoint creates order (`ezzy_api/views.py:import_shopify_orders`, `import_woocommerce_orders`)
- Manual order creation by business

**Process:**
1. Order is created with `order_status='to_review'` and `verification_status='pending'`
2. Signal `order_post_save_receiver` automatically:
   - Saves original order data as proof in `original_order_data` JSONField
   - Creates initial `AddressVerification` record
   - Creates `DlAddressUpdate` record
   - Creates `OrderBarcode`
   - Creates `OrderProductList`

**Models:**
- `Order` - Main order model with verification tracking
- `OrderVerificationLog` - Audit trail
- `AddressVerification` - Address verification details
- `OrderDocument` - Order documents/proof

### 2. Order Verification (Workforce App)

**Workflow:**
1. **Address Verification** (`workforce/views.py:verify_order_address`)
   - Workforce verifies customer address
   - Updates address coordinates (latitude, longitude)
   - Updates zone, street, building numbers
   - Sets `verification_status='address_verified'` or `'address_needs_update'`
   - Creates/updates `AddressVerification` record
   - Logs action in `OrderVerificationLog`

2. **Order Verification** (`workforce/views.py:verify_order`)
   - Workforce verifies complete order
   - Sets `verification_status='verified'`
   - Logs action in `OrderVerificationLog`
   - **Automatically triggers delivery task creation** (via signal)

**URLs:**
- `/workforce/orders/pending-verification/` - List pending orders
- `/workforce/orders/<order_id>/verify-address/` - Verify address
- `/workforce/orders/<order_id>/verify/` - Verify order

### 3. Delivery Task Creation (Orders → Delivery App)

**Automatic Process:**
When order `verification_status` changes to `'verified'`:
1. Signal `order_post_save_receiver` detects status change
2. Calls `_create_delivery_task_from_order()` function:
   - Creates/updates `DlAddressUpdate` with verified address
   - Creates `DeliveryTask` linked to order
   - Updates order: `task_created=True`, `task_status='dl_task_listed'`
   - **Automatically pushes to DMS** (via `_push_task_to_dms()`)

**Manual Process:**
- Workforce can manually create task via `/workforce/orders/submit_to_task/<order_id>/`
- Checks if order is verified before creating task

### 4. DMS Push (Delivery → DMS via API)

**Automatic Push:**
1. When `DeliveryTask` is created, signal `delivery_task_post_save_receiver` triggers
2. Calls `_push_task_to_dms()` function:
   - Prepares task data
   - Sends POST request to DMS API
   - Updates task with DMS response (`dl_task_number_dms`, `dl_task_publish=True`)

**Manual Push:**
- API endpoint: `POST /api/tasks/<task_id>/push-to-dms/`
- Workforce can manually push via API

**Configuration:**
- Environment variables: `DMS_API_URL`, `DMS_API_KEY`
- Can be configured per business via `BusinessApiSettings`

### 5. Task Management (Delivery App)

**Features:**
- Tasks linked to orders (duplicate data for followups)
- Address updates tracked in `DlAddressUpdate`
- Driver assignment via `AssignedDriver`
- Status tracking with DMS status codes

## API Endpoints

### Order Verification APIs
- `GET /api/orders/pending-verification/` - Get orders pending verification
- `POST /api/orders/<order_id>/verify-address/` - Verify order address
- `POST /api/orders/<order_id>/verify/` - Verify order and create task
- `POST /api/orders/<order_id>/reject/` - Reject order
- `POST /api/tasks/<task_id>/push-to-dms/` - Manually push task to DMS

### Driver App APIs
- `POST /api/driver/login/` - Driver login
- `GET /api/driver/tasks/` - Get driver tasks
- `POST /api/driver/tasks/<task_id>/complete/` - Complete task with proof
- `POST /api/driver/tasks/<task_id>/documents/upload/` - Upload documents

### Webhook APIs
- `POST /api/webhooks/task/status/` - Receive task status updates
- `POST /api/webhooks/task/complete/` - Receive task completion
- `POST /api/webhooks/driver/location/` - Receive driver location

### E-commerce Integration APIs
- `POST /api/integrations/shopify/import/` - Import Shopify orders
- `POST /api/integrations/woocommerce/import/` - Import WooCommerce orders

## Data Flow Diagram

```
Client Creates Order
    ↓
Order Saved (original_order_data as proof)
    ↓
Address Verification Record Created
    ↓
Workforce Verifies Address
    ↓
Address Verified (coordinates updated)
    ↓
Workforce Verifies Order
    ↓
Order Status: verified
    ↓
Signal Triggers: _create_delivery_task_from_order()
    ↓
DeliveryTask Created
    ↓
Signal Triggers: _push_task_to_dms()
    ↓
Task Pushed to DMS
    ↓
Task Listed in Delivery Tasks
    ↓
Driver Assigned
    ↓
Task Completed
```

## Key Features

### 1. Order Proof Storage
- `original_order_data` JSONField stores complete original order data
- Preserved for audit trail and future followups
- Automatically saved on order creation

### 2. Address Verification
- Separate `AddressVerification` model tracks verification details
- Coordinates (latitude, longitude) stored
- Zone, street, building numbers updated
- Original vs verified address comparison

### 3. Verification Workflow
- Status tracking: `pending` → `address_verified` → `verified`
- Complete audit trail via `OrderVerificationLog`
- Automated task creation on verification

### 4. DMS Integration
- Automatic push when task is created
- Manual push endpoint available
- Status synchronization
- Error handling and retry capability

### 5. Duplicate Data for Followups
- Order data duplicated in DeliveryTask
- Address data in DlAddressUpdate
- Allows independent tracking and updates

## Signals Configuration

### Orders App (`orders/signals.py`)
- `order_pre_save_receiver` - Generates order number, tracks old status
- `order_post_save_receiver` - Saves original data, creates verification records, triggers task creation

### Delivery App (`delivery/signals.py`)
- `delivery_task_post_save_receiver` - Pushes task to DMS on creation/update

### App Configuration
- `orders/apps.py` - Signals imported in `ready()`
- `delivery/apps.py` - Signals imported in `ready()`

## Environment Variables Required

```env
DMS_API_URL=https://your-dms-api-url.com
DMS_API_KEY=your-dms-api-key
```

## Database Models

### Orders App
- `Order` - Main order with verification fields
- `OrderVerificationLog` - Verification audit trail
- `AddressVerification` - Address verification details
- `OrderDocument` - Order documents
- `OrderBarcode` - Order barcodes
- `OrderProductList` - Order products

### Delivery App
- `DeliveryTask` - Delivery tasks linked to orders
- `DlAddressUpdate` - Delivery address updates
- `AssignedDriver` - Driver assignments

### EZzy API App
- `ClientApiKey` - API keys for clients
- `TaskDocument` - Task documents
- `OrderDocument` - Order documents
- `EcommerceIntegration` - E-commerce integrations
- `WebhookEndpoint` - Webhook configurations
- `WebhookDelivery` - Webhook delivery tracking

## Testing Checklist

1. ✅ Order creation saves original data
2. ✅ Address verification workflow
3. ✅ Order verification triggers task creation
4. ✅ Task creation triggers DMS push
5. ✅ API endpoints for verification
6. ✅ Webhook endpoints for driver app
7. ✅ E-commerce integration (Shopify/WooCommerce)
8. ✅ Document upload functionality
9. ✅ API key generation
10. ✅ Signal connections verified

## Next Steps

1. Run migrations: `python manage.py makemigrations` then `python manage.py migrate`
2. Configure DMS API credentials in environment variables
3. Test order creation → verification → task creation → DMS push workflow
4. Test API endpoints with Postman or similar tool
5. Configure webhook endpoints for driver app status updates

