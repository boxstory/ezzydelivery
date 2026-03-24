# EzzyDelivery — Business Client Workflow Guide

This guide explains everything a business client needs to know to use EzzyDelivery effectively — from account setup to order creation, tracking, and COD settlement.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard Overview](#2-dashboard-overview)
3. [Setting Up Your Account](#3-setting-up-your-account)
4. [Creating Orders](#4-creating-orders)
5. [Managing Your Orders](#5-managing-your-orders)
6. [Tracking Order Status](#6-tracking-order-status)
7. [COD (Cash on Delivery)](#7-cod-cash-on-delivery)
8. [Finance & Statements](#8-finance--statements)
9. [Team Members & Permissions](#9-team-members--permissions)
10. [E-commerce Integrations](#10-e-commerce-integrations)
11. [Order Status Reference](#11-order-status-reference)
12. [FAQs](#12-faqs)

---

## 1. Getting Started

### Your Account Type
You are a **Business** account. This gives you access to:
- Create and manage delivery orders
- Track real-time delivery status
- Manage COD collections
- View finance and COD statements
- Invite team members with specific permissions

### Login
Go to your dashboard at:
```
/business/dashboard/
```

If you manage multiple businesses, use the business selector:
```
/business/selector/
```
Switch between businesses at:
```
/business/switch/{business_id}/
```

---

## 2. Dashboard Overview

Your dashboard (`/business/dashboard/`) shows:
- **Recent orders** — latest 5 orders and their statuses
- **Pending orders** — orders waiting for pickup or delivery
- **Delivered orders** — completed deliveries
- **Failed/Cancelled** — orders that could not be delivered
- **COD summary** — total COD pending collection

---

## 3. Setting Up Your Account

Complete these steps before creating your first order.

### 3a. Business Profile
Set up your business information at:
```
/business/{business_id}/update/
```
- Business name, logo, contact details
- Business address and zone

### 3b. Pickup Locations
A **Pickup Location** is where our driver will collect packages from you.

Manage pickup locations at:
```
/business/settings/pickup_locations/
```

**To add a new pickup location:**
1. Go to `/business/settings/pickup_location/add/`
2. Fill in:
   - Location name / title
   - Address and zone details
   - Contact person and phone
3. Save — this location will appear in your order form

> You can have multiple pickup locations (e.g. different warehouses or stores).
> The fulfillment center (if enabled) always appears first in the dropdown.

### 3c. Fulfillment Service (Optional)
If you use EzzyDelivery's warehouse fulfillment service:
- Your inventory is stored in our warehouse
- Orders are picked, packed, and shipped from the warehouse
- The fulfillment center automatically appears as your default pickup location

Request warehouse access at:
```
/business/settings/warehouse-request/
```

---

## 4. Creating Orders

You have four ways to create orders. Choose based on your volume.

---

### Method 1 — Single Order Form
**Best for:** 1–5 orders at a time

Go to:
```
/orders/add_order/
```

Fill in the following:

#### Order Information
| Field | Description | Required |
|---|---|---|
| Client Order Code | Your own internal order/invoice number | Recommended |
| Order Notes | Short description or delivery instructions | Optional |
| Order Type | `Normal Delivery` or `Pick & Drop` | Required |
| Pickup Location | Where driver picks up the package | Required |

#### Customer Details
| Field | Description | Required |
|---|---|---|
| Customer Name | Recipient's full name | Required |
| Customer Phone | Primary contact number | Required |
| Customer WhatsApp | WhatsApp number (if different from phone) | Optional |

#### Delivery Address
| Field | Description |
|---|---|
| Customer Address | Free-text address description |
| Zone Number | Qatar zone number (use the map or QNAS lookup) |
| Street Number | Qatar street number |
| Building Number | Qatar building number |
| Map Pin | Click on map to auto-fill zone/street/building |

> **Tip:** Use the QNAS address search to auto-fill zone, street, and building numbers. Accurate address data reduces failed deliveries.

#### COD Details
| Field | Description |
|---|---|
| COD Amount | Amount in QAR the driver will collect from the customer. Enter `0` for no COD. |
| COD Status | Select `No COD` if not collecting cash, or `Pending` if COD is expected |

---

### Method 2 — Bulk Spreadsheet Entry
**Best for:** 10–100 orders, entered manually row by row

Go to:
```
/orders/bulk_entry/
```

Enter orders in a spreadsheet-style table. Each row is one order.

**Columns:**
| Column | Description |
|---|---|
| Order ID | Your internal reference code |
| Customer Name | Recipient name |
| Phone 1 | Primary contact |
| Phone 2 (WhatsApp) | WhatsApp number |
| Customer Address | Full address |
| Zone No | Zone number |
| Street No | Street number |
| Building No | Building number |
| Deadline Date | Required delivery date |
| Note | Delivery instructions |
| Product Name | Item description |
| Qty | Quantity |
| Price | COD amount |

**Tips:**
- Leave Order ID blank — it will be auto-generated
- All valid rows are saved together in one batch
- Fix any row errors before submitting

---

### Method 3 — CSV / Excel File Upload
**Best for:** 100+ orders prepared in a spreadsheet

Go to:
```
/orders/bulk-import/
```

**Step 1 — Upload File**
- Supported formats: `.csv`, `.xlsx`, `.xls`
- Max file size: 5MB

**Step 2 — Map Columns**
The system auto-detects your column names. If your column headers are different, manually map them to the correct fields.

Supported column names:
| Your Column | Maps To |
|---|---|
| `client_order_code`, `order_id`, `reference` | Client Order Code |
| `customer_name`, `name`, `recipient` | Customer Name |
| `customer_phone`, `phone`, `mobile` | Phone |
| `customer_whatsapp`, `whatsapp` | WhatsApp |
| `customer_address`, `address` | Delivery Address |
| `dl_zone`, `zone`, `zone_no` | Zone Number |
| `dl_street`, `street`, `street_no` | Street Number |
| `dl_building`, `building`, `building_no` | Building Number |
| `cod_amount`, `price`, `cod` | COD Amount |
| `deadline_date`, `delivery_date` | Deadline Date |
| `internal_notes`, `notes`, `note` | Notes |
| `product_name`, `item`, `product` | Product Name |
| `quantity`, `qty` | Quantity |

**Step 3 — Preview & Edit**
Review all rows before saving. Fix any errors inline.

**Step 4 — Confirm**
Click Save — all valid orders are created instantly.

---

### Method 4 — Import from E-commerce Platform
**Best for:** Shopify, WooCommerce, or TikTok Shop sellers

Go to:
```
/orders/api/shopify_orders/
```

#### Shopify
1. Connect your Shopify store in Settings → API
2. Import orders by:
   - Date range (start date / end date)
   - Specific order IDs
   - Limit: up to 50 orders per import

#### WooCommerce
1. Connect your WooCommerce store in Settings → API
   ```
   /business/{business_id}/settings/api/add/
   ```
2. Import options:
   - Date range
   - Order status filter (e.g. `processing`, `completed`)
   - Specific order IDs
   - Limit: up to 50 per import

#### TikTok Shop
1. Connect your TikTok Shop in Settings → API
2. Import orders in the same way

---

## 5. Managing Your Orders

### Viewing Your Orders
All orders:
```
/orders/partial/all/
```

Filter by:
- **Order number** — search by your order or client reference
- **Customer name or phone**
- **Zone** — delivery zone number
- **Status** — to_review, ready to pickup, delivered, cancelled
- **Date range** — today, yesterday, last 3 days, this week, this month, or custom range
- **COD** — with COD or without
- **Delivery result** — pending, delivered, failed

### Order Views
Switch between:
- **List view** — compact rows
- **Table view** — full-width spreadsheet view
- **Kanban view** — cards grouped by status
- **Mobile view** — optimized for phones

### Editing an Order
You can edit an order while it is still in **Hold for Review** status:
```
/orders/order_update/{order_id}/
```

**Editable fields:**
- Customer phone and WhatsApp
- Delivery address (zone, street, building)
- COD amount and COD status
- Pickup location
- Order notes

> Once an order is verified and assigned to a driver, editing is restricted.

### Cancelling an Order
You can cancel an order if it has **not yet been picked up**.

Go to the order detail page and select Cancel:
```
/orders/order_details/{order_id}/
```

> Orders that are already picked up or delivered cannot be cancelled by the client. Contact EzzyDelivery support.

### Deleting an Order
Orders can only be deleted if status is **Hold for Review** or **Cancelled**.

```
/orders/delete_order/{order_id}/
```

> Deletion is permanent and cannot be undone.

### Adding Products / Items to an Order
Attach item details for fulfillment tracking:
```
/orders/add_order_product/{order_id}/
```

For each item:
- Select product from your catalog
- Set quantity and unit price
- Add item notes

---

## 6. Tracking Order Status

### What Happens After You Submit

```
You Submit Order
      ↓
Status: Hold for Review
      ↓
EzzyDelivery Staff Verifies Address & Details
      ↓
Status: Ready to Pickup
      ↓
Driver Assigned & Picks Up Package
      ↓
Driver Out for Delivery
      ↓
Status: Delivered ✓  (or Failed / Cancelled)
```

### Order Status Explained

| Status | What It Means | Action Needed? |
|---|---|---|
| **Hold for Review** | Order received, staff checking details | None — wait for verification |
| **Ready to Pickup** | Verified, driver being assigned | None |
| **Published** | Driver pool can see the task | None |
| **Delivered** | Package delivered to customer | Check COD if applicable |
| **Failed** | Delivery attempt failed | Contact support to reschedule |
| **Cancelled** | Order cancelled | No further action |

### Order Detail Page
View full order history and timeline at:
```
/orders/order_details/{order_id}/
```

Shows:
- Order creation details
- Verification status
- Driver assignment
- All delivery status changes with timestamps
- Comments from staff
- COD status

### Adding Comments to an Order
If you have a note or question about an order:
1. Open the order detail page
2. Scroll to Comments section
3. Type your message and submit

Comments are visible to EzzyDelivery staff and cannot be edited after posting.

---

## 7. COD (Cash on Delivery)

### How COD Works

1. **You set the COD amount** when creating the order
2. **Driver collects cash** from the customer on delivery
3. **EzzyDelivery holds the cash** after driver handover
4. **Cash is settled** to your account on the agreed schedule

### COD Status — What You See

| Status | Meaning |
|---|---|
| **No COD** | No cash collection for this order |
| **Pending** | COD expected, driver has not yet collected |
| **Collected** | Driver collected cash from customer |
| **Received by Company** | Cash handed from driver to EzzyDelivery |
| **Invoiced** | Included in your invoice |
| **Settled** | Cash transferred to your account |
| **Online Paid** | Customer paid online directly to you |
| **Disputed** | COD amount in dispute — contact support |

### Viewing COD Summary
Go to Finance:
```
/business/finance/
/business/finance/cod-statement/
```

Filter by date range to see:
- Total COD collected by drivers
- COD received by EzzyDelivery
- COD settled to your account
- Pending COD balances

---

## 8. Finance & Statements

### Finance Dashboard
```
/business/finance/
```
Overview of:
- Total orders this month
- Total COD collected
- COD pending settlement
- Delivery fees invoiced

### Transactions
```
/business/finance/transactions/
```
Full transaction history with filters by date, type, and status.

### COD Statement
```
/business/finance/cod-statement/
```
Detailed breakdown of all COD transactions — useful for reconciliation.

---

## 9. Team Members & Permissions

### Adding Team Members
Invite staff to manage orders on your behalf:
```
/business/{business_id}/teams/add/
```

### Permission Levels
Control exactly what each team member can do:

| Permission | What It Allows |
|---|---|
| **Order View** | View all orders and order details |
| **Order Create** | Create new orders (single, bulk, import) |
| **Order Edit** | Update order details and status |
| **Order Delete** | Delete orders (restricted by status) |

### Managing Team
View and manage all team members:
```
/business/{business_id}/teams/
```

Update permissions:
```
/business/{business_id}/teams/{team_id}/permissions/
```

Remove a team member:
```
/business/{business_id}/teams/{team_id}/remove/
```

---

## 10. E-commerce Integrations

Connect your online store to automatically import orders.

### Setting Up an Integration
```
/business/{business_id}/settings/api/add/
```

Supported platforms:
- **Shopify**
- **WooCommerce**
- **TikTok Shop**

You will need your store's API key and secret from the platform's developer settings.

### Testing a Connection
After adding an integration:
```
/business/{business_id}/settings/api/{api_id}/test/
```

### Importing Orders
Once connected, go to:
```
/orders/api/shopify_orders/
```
Select date range or specific order IDs and import.

---

## 11. Order Status Reference

### Order Status
| Value | Display | Description |
|---|---|---|
| `to_review` | Hold for Review | Newly submitted, pending staff verification |
| `ready_to_pickup` | Ready to Pickup | Verified, awaiting driver assignment |
| `publish` | Published | Task visible to drivers in fleet |
| `delivered` | Delivered | Successfully delivered |
| `cancelled` | Cancelled | Order cancelled |

### COD Status (Client View)
| Value | Display | Description |
|---|---|---|
| `no_cod` | No COD | No cash collection |
| `pending` | COD Pending | Awaiting collection |
| `collected` | Collected by Driver | Driver has the cash |
| `received_by_company` | Received by Company | EzzyDelivery received cash |
| `invoiced` | Invoiced | Added to your invoice |
| `settled` | Settled | Paid to your account |
| `online_paid` | Paid Online | Customer paid online |
| `disputed` | Disputed | Under review |

### Verification Status
| Value | Display | Meaning |
|---|---|---|
| `pending` | Pending | Not yet reviewed |
| `address_verified` | Address Verified | Address confirmed |
| `address_needs_update` | Needs Update | Address has issues |
| `customer_contacted` | Customer Contacted | Staff contacted customer |
| `verified` | Verified | Fully verified, ready for delivery |
| `rejected` | Rejected | Order has issues — action required |

---

## 12. FAQs

**Q: My order is stuck in "Hold for Review" — what should I do?**
A: This is normal. EzzyDelivery staff will verify your order's address and details. If there's an issue, they will add a comment or contact you. You can check the order detail page for any staff notes.

**Q: Can I edit an order after submitting?**
A: Yes, while the order is in "Hold for Review" status. Once verified and assigned to a driver, editing is restricted. Contact support for urgent changes.

**Q: The delivery failed — what happens next?**
A: EzzyDelivery staff will contact you to reschedule or arrange a second delivery attempt. The order status remains unchanged until a resolution is reached.

**Q: When will I receive my COD money?**
A: COD is settled according to your agreed settlement schedule (weekly or bi-weekly). Check your COD Statement for the current balance.

**Q: How do I import orders from Shopify?**
A: Go to Settings → API, connect your Shopify store, then use the import page to pull orders by date range. See [Section 10](#10-e-commerce-integrations) for full steps.

**Q: Can multiple team members create orders at the same time?**
A: Yes. Team members with `ORDER_CREATE` permission can create orders simultaneously. Each order is tracked with the user who created it.

**Q: What is the QNAS address system?**
A: QNAS (Qatar National Address System) uses zone, street, and building numbers to precisely locate addresses in Qatar. Using accurate QNAS numbers reduces failed deliveries and speeds up verification.

**Q: My customer wants to update their delivery address — can they do it themselves?**
A: Yes. EzzyDelivery can send your customer a secure verification link. The customer opens the link (no login needed), confirms or updates their address on a map, and the order is updated automatically.

---

*For support, contact your EzzyDelivery account manager or email support@ezzydelivery.qa*

*Last updated: 2026-02-26*
