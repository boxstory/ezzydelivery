# Flutter Native Driver App — Full Implementation Plan
## EzzyDelivery Qatar

**Created:** 2026-03-21
**Status:** Planning Phase
**Target Platforms:** Android 6.0+ (API 23) · iOS 12.0+
**Backend:** Django REST API at `https://ezzydelivery.qa/api/`
**Estimated Duration:** 10–12 weeks (2 developers)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [App Architecture](#3-app-architecture)
4. [Brand & Design System](#4-brand--design-system)
5. [Screen Map & Navigation](#5-screen-map--navigation)
6. [Feature Specifications](#6-feature-specifications)
7. [Backend API Reference](#7-backend-api-reference)
8. [Data Models (Dart)](#8-data-models-dart)
9. [Authentication & Security](#9-authentication--security)
10. [State Management](#10-state-management)
11. [Background Services](#11-background-services)
12. [Push Notifications](#12-push-notifications)
13. [Offline Mode](#13-offline-mode)
14. [Development Phases](#14-development-phases)
15. [Testing Strategy](#15-testing-strategy)
16. [Deployment](#16-deployment)
17. [What's Already Built (PWA Reference)](#17-whats-already-built-pwa-reference)
18. [API Endpoints Needing Creation](#18-api-endpoints-needing-creation)

---

## 1. Project Overview

The EzzyDelivery Flutter Driver App replaces the existing PWA with a native Android/iOS application. It enables drivers to:

- View and manage delivery tasks in real time
- Accept/reject assigned jobs
- Navigate to pickup and delivery locations
- Collect COD (Cash on Delivery) and submit to admin
- Track earnings, wallet balance, and settlements
- Upload proof of delivery (photo + GPS)
- Receive push notifications for new orders
- Operate with limited offline capability

### Current PWA (Reference)
All screens already exist as Django PWA templates at:
```
fleet/templates/fleet/pwa_base.html
fleet/templates/fleet/fleet_dashboard_pwa.html
fleet/templates/fleet/driver_tasks_pwa.html
fleet/templates/fleet/task_navigation_pwa.html
fleet/templates/fleet/cod_collection_pwa.html
fleet/templates/fleet/cod_submission_pwa.html
fleet/templates/fleet/driver_earnings_pwa.html
fleet/templates/fleet/driver_profile_pwa.html
fleet/templates/fleet/pickup_scanner_pwa.html
fleet/templates/fleet/driver_notifications_pwa.html
fleet/templates/fleet/driver_settings_pwa.html
```
The Flutter app reproduces all these screens natively.

---

## 2. Tech Stack & Dependencies

### Flutter / Dart Versions
```yaml
environment:
  sdk: ">=3.0.0 <4.0.0"
  flutter: ">=3.10.0"
```

### `pubspec.yaml` — Full Dependencies

```yaml
dependencies:
  flutter:
    sdk: flutter

  # ── State Management ──────────────────────────────────────
  flutter_riverpod: ^2.5.1         # Primary state management
  riverpod_annotation: ^2.3.5      # Code generation support

  # ── Networking ────────────────────────────────────────────
  dio: ^5.4.3                      # HTTP client with interceptors
  pretty_dio_logger: ^1.3.1        # Debug logging
  json_annotation: ^4.8.1          # JSON serialization
  json_serializable: ^6.7.1        # Code generation

  # ── Authentication & Storage ──────────────────────────────
  flutter_secure_storage: ^9.0.0   # Token storage (Keychain/Keystore)
  shared_preferences: ^2.2.3       # Non-sensitive preferences

  # ── Location & Maps ───────────────────────────────────────
  google_maps_flutter: ^2.6.0      # Google Maps widget
  geolocator: ^11.0.0              # GPS location stream
  geocoding: ^3.0.0                # Address ↔ coordinates
  url_launcher: ^6.2.7             # Open Google Maps / phone calls

  # ── Camera & Barcode ──────────────────────────────────────
  camera: ^0.11.0                  # Camera feed
  image_picker: ^1.1.2             # Gallery / camera picker
  image_cropper: ^7.0.1            # Crop before upload
  mobile_scanner: ^5.1.1           # Barcode/QR scanner (replaces PWA BarcodeDetector)

  # ── Signature ─────────────────────────────────────────────
  signature: ^5.4.1                # Signature pad for POD

  # ── Push Notifications ────────────────────────────────────
  firebase_core: ^3.3.0
  firebase_messaging: ^15.1.3
  flutter_local_notifications: ^17.2.2

  # ── Background Services ───────────────────────────────────
  workmanager: ^0.5.2              # Background GPS ping task
  flutter_background_service: ^5.0.5  # Foreground service on Android

  # ── UI / Components ───────────────────────────────────────
  flutter_svg: ^2.0.10             # SVG brand assets
  cached_network_image: ^3.3.1     # Cached async images
  shimmer: ^3.0.0                  # Skeleton loading screens
  lottie: ^3.1.2                   # Animated icons (delivery, success)
  fl_chart: ^0.68.0                # Earnings bar/line charts
  percent_indicator: ^4.2.3        # Wallet usage % bar

  # ── Utilities ─────────────────────────────────────────────
  intl: ^0.19.0                    # Number/date formatting (QR currency)
  connectivity_plus: ^6.0.3        # Online/offline detection
  permission_handler: ^11.3.1      # Camera, location permissions
  package_info_plus: ^8.0.2        # App version
  device_info_plus: ^10.1.2        # Device fingerprint for FCM
  path_provider: ^2.1.4            # File system paths
  open_filex: ^4.4.1               # Open downloaded PDF reports
  local_auth: ^2.3.0               # Biometric / fingerprint auth
  pin_code_fields: ^8.0.1          # PIN entry widget
  timeago: ^3.6.1                  # "2 minutes ago" timestamps
  collection: ^1.18.0              # Dart collection helpers

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  build_runner: ^2.4.12
  riverpod_generator: ^2.4.3
  json_serializable: ^6.7.1
  mocktail: ^1.0.4                 # Mocking for tests
```

---

## 3. App Architecture

### Pattern: Clean Architecture + Riverpod

```
lib/
├── main.dart                         # App entry point + providers
├── app.dart                          # MaterialApp + router setup
│
├── core/
│   ├── constants/
│   │   ├── api_constants.dart        # Base URL, endpoint paths
│   │   ├── app_colors.dart           # Brand colors (EzzyDelivery)
│   │   ├── app_theme.dart            # ThemeData
│   │   └── app_strings.dart          # Localized strings (EN/AR)
│   ├── errors/
│   │   ├── app_exception.dart        # Custom exceptions
│   │   └── error_handler.dart        # Global error handling
│   ├── network/
│   │   ├── dio_client.dart           # Dio instance + interceptors
│   │   ├── auth_interceptor.dart     # Token injection + 401 refresh
│   │   └── network_info.dart         # Connectivity checker
│   ├── storage/
│   │   ├── secure_storage.dart       # Token + sensitive data
│   │   └── local_storage.dart        # Shared preferences wrapper
│   ├── router/
│   │   └── app_router.dart           # GoRouter route definitions
│   └── utils/
│       ├── currency_formatter.dart   # "1,500 QR" formatting
│       ├── date_formatter.dart       # Arabic/English date display
│       └── validators.dart           # Form validation rules
│
├── data/
│   ├── models/                       # JSON-serializable data classes
│   │   ├── driver_model.dart
│   │   ├── delivery_task_model.dart
│   │   ├── order_model.dart
│   │   ├── transaction_model.dart
│   │   ├── settlement_model.dart
│   │   ├── notification_model.dart
│   │   ├── location_model.dart
│   │   └── wallet_status_model.dart
│   ├── repositories/
│   │   ├── auth_repository.dart
│   │   ├── task_repository.dart
│   │   ├── earnings_repository.dart
│   │   ├── location_repository.dart
│   │   └── notification_repository.dart
│   └── datasources/
│       ├── remote/
│       │   ├── auth_api.dart
│       │   ├── task_api.dart
│       │   ├── earnings_api.dart
│       │   └── location_api.dart
│       └── local/
│           ├── task_cache.dart       # Hive/SQLite for offline tasks
│           └── location_queue.dart   # Offline GPS ping queue
│
├── presentation/
│   ├── providers/                    # Riverpod providers
│   │   ├── auth_provider.dart
│   │   ├── task_provider.dart
│   │   ├── earnings_provider.dart
│   │   ├── location_provider.dart
│   │   └── notification_provider.dart
│   ├── screens/
│   │   ├── splash/
│   │   │   └── splash_screen.dart
│   │   ├── auth/
│   │   │   ├── login_screen.dart
│   │   │   └── biometric_screen.dart
│   │   ├── dashboard/
│   │   │   └── dashboard_screen.dart
│   │   ├── tasks/
│   │   │   ├── task_list_screen.dart
│   │   │   ├── task_detail_screen.dart
│   │   │   ├── task_navigation_screen.dart
│   │   │   └── delivery_proof_screen.dart
│   │   ├── scanner/
│   │   │   └── pickup_scanner_screen.dart
│   │   ├── cod/
│   │   │   ├── cod_collection_screen.dart
│   │   │   └── cod_submission_screen.dart
│   │   ├── earnings/
│   │   │   ├── earnings_screen.dart
│   │   │   ├── transaction_list_screen.dart
│   │   │   └── settlement_screen.dart
│   │   ├── notifications/
│   │   │   └── notifications_screen.dart
│   │   └── profile/
│   │       ├── profile_screen.dart
│   │       ├── documents_screen.dart
│   │       ├── vehicles_screen.dart
│   │       └── settings_screen.dart
│   └── widgets/
│       ├── common/
│       │   ├── ezzy_button.dart
│       │   ├── ezzy_card.dart
│       │   ├── loading_shimmer.dart
│       │   ├── empty_state.dart
│       │   ├── error_state.dart
│       │   └── connectivity_banner.dart
│       ├── task/
│       │   ├── task_status_badge.dart
│       │   ├── task_card.dart
│       │   └── cod_amount_chip.dart
│       ├── earnings/
│       │   ├── wallet_progress_bar.dart
│       │   └── earnings_chart.dart
│       └── bottom_nav/
│           └── main_bottom_nav.dart
│
└── services/
    ├── background_location_service.dart  # Workmanager GPS task
    ├── fcm_service.dart                  # Firebase push handling
    └── sync_service.dart                 # Offline queue sync
```

---

## 4. Brand & Design System

### Colors (matching existing PWA)
```dart
class AppColors {
  // Brand
  static const primary       = Color(0xFFF7C000);  // Ezzy Yellow
  static const primaryDark   = Color(0xFFF4C20D);
  static const navy          = Color(0xFF001F3F);
  static const navyLight     = Color(0xFF003366);

  // Status
  static const success       = Color(0xFF10B981);
  static const warning       = Color(0xFFF59E0B);
  static const danger        = Color(0xFFEF4444);
  static const info          = Color(0xFF3B82F6);

  // Neutrals
  static const grey100       = Color(0xFFFAFAFA);
  static const grey300       = Color(0xFFDCDCDC);
  static const grey600       = Color(0xFF555555);
  static const grey800       = Color(0xFF1F1F1F);
  static const white         = Color(0xFFFFFFFF);
  static const black         = Color(0xFF000000);

  // Task Status Colors
  static const taskPending   = Color(0xFFF59E0B);
  static const taskAssigned  = Color(0xFF3B82F6);
  static const taskAccepted  = Color(0xFF8B5CF6);
  static const taskPickedUp  = Color(0xFFF97316);
  static const taskInTransit = Color(0xFF06B6D4);
  static const taskDelivered = Color(0xFF10B981);
  static const taskFailed    = Color(0xFFEF4444);
  static const taskCancelled = Color(0xFF6B7280);
}
```

### Typography
```dart
// Font: Inter (matching brand kit)
static const fontFamily = 'Inter';

// Scale
static const double xs   = 12.0;
static const double sm   = 14.0;
static const double base = 15.0;  // Body text
static const double lg   = 18.0;
static const double xl   = 20.0;
static const double xl2  = 24.0;
static const double xl3  = 30.0;
```

### Spacing
```dart
static const double xs  = 4.0;
static const double sm  = 8.0;
static const double md  = 16.0;
static const double lg  = 24.0;
static const double xl  = 32.0;
```

### Border Radius
```dart
static const double radiusSm   = 8.0;
static const double radiusMd   = 12.0;
static const double radiusLg   = 18.0;
static const double radiusFull = 50.0;
```

---

## 5. Screen Map & Navigation

### Bottom Navigation (5 tabs)
```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│  Home    │  Tasks   │  Scan    │ Earnings │ Profile  │
│ (house)  │ (truck)  │ (qrcode) │ (wallet) │ (user)   │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

### Full Route Map
```
/splash
/login
/biometric

/dashboard                        ← Home tab
  /notifications

/tasks                            ← Tasks tab
  /tasks/:id                      ← Task detail
    /tasks/:id/navigate           ← Full-screen map + navigation
    /tasks/:id/proof              ← Delivery proof capture
    /tasks/:id/cod-collect        ← COD collection form

/scanner                          ← Scan tab (pickup barcode scanner)

/earnings                         ← Earnings tab
  /earnings/transactions
  /earnings/transactions/:code
  /earnings/settlements
  /earnings/settlements/:code
  /cod-submission                 ← Submit COD to admin

/profile                          ← Profile tab
  /profile/documents
  /profile/vehicles
  /profile/settings
  /profile/help
```

---

## 6. Feature Specifications

---

### 6.1 Splash Screen
- Show EzzyDelivery logo + animated truck
- Check stored auth token → if valid, go to Dashboard
- If expired/missing, go to Login
- Check driver status: if `suspended` or `blocked`, show alert + logout

---

### 6.2 Login Screen
- **Fields**: Username, Password
- **Actions**: Login button, Biometric login (if enrolled)
- **API**: `POST /api/driver/login/`
- **On success**: Store token securely, fetch driver profile, go to Dashboard
- **Error states**: Invalid credentials, Account not approved, Account suspended

**Biometric Login** (optional, if `local_auth` enrolled):
- After first login, offer to save credentials with biometric
- Subsequent logins: fingerprint / Face ID → skip password entry

---

### 6.3 Dashboard (Home)

**Layout:**
```
┌─────────────────────────────────────────┐
│  👋 Good morning, Ahmed!    🔔 [3]      │
│  Status: [● ONLINE ▾]                   │
├─────────────────────────────────────────┤
│  🚨 WALLET ALERT (if cod_in_hand ≥ 80%) │
├─────────────────────────────────────────┤
│  ┌─────────────────────────────────┐   │
│  │  COD WALLET                     │   │
│  │  ████████░░  80%                │   │
│  │  In Hand: 4,000 QR | Limit: 5,000│  │
│  │  Available: 1,000 QR            │   │
│  │  [Submit COD]  [View Earnings]  │   │
│  └─────────────────────────────────┘   │
├─────────────────────────────────────────┤
│  TODAY   │  THIS WEEK  │  PENDING       │
│  8 tasks │  42 tasks   │  2 QAR 320    │
├─────────────────────────────────────────┤
│  ACTIVE TASK (if exists)                │
│  ORD-2026-1234 → Al Sadd Zone 25       │
│  COD: 150 QR  [Open Task ›]            │
├─────────────────────────────────────────┤
│  QUICK ACTIONS                          │
│  [📦 Tasks] [💰 COD] [📊 Earnings]    │
│  [📷 Scan]  [📄 Docs] [🗺️ Map]        │
├─────────────────────────────────────────┤
│  LATEST TASKS (last 5)                  │
│  ...                                    │
└─────────────────────────────────────────┘
```

**Wallet Alert Logic:**
- 🟢 Normal: cod_in_hand < 80% of credit_limit → no alert
- 🟡 Warning: cod_in_hand ≥ 80% → yellow "Submit COD soon" banner
- 🔴 Blocked: cod_in_hand ≥ credit_limit → red "Wallet blocked" banner

**Availability Toggle:**
- Tap status chip → bottom sheet: [Available] [On Break] [Offline]
- API: `POST /api/driver/status/`
- Payload: `{"availability": "available"}`

---

### 6.4 Task List Screen

**Tabs:**
| Tab | Filter |
|-----|--------|
| Available | status = pending (unassigned batch) |
| Active | status = accepted / picked_up / in_transit / out_for_delivery |
| Completed | status = delivered |
| Failed | status = failed / cancelled |

**Task Card shows:**
- Task number + order number
- Customer name + zone/area
- COD amount (if applicable)
- Status badge (colored)
- Scheduled time / created time
- Earnings amount

**Pull to refresh** → re-fetch from API

---

### 6.5 Task Detail Screen

```
┌────────────────────────────────────────┐
│  ← TASK-20260228-001        [PENDING]  │
├────────────────────────────────────────┤
│  PICKUP                                │
│  📍 Fareej Sudan, Doha                 │
│  EzzyDelivery Warehouse                │
│  [📞 Call Warehouse]  [🗺️ Navigate]   │
├────────────────────────────────────────┤
│  DELIVERY                              │
│  👤 Ahmed Al-Mansouri                  │
│  📞 +974 5512 3456    [Call] [WhatsApp]│
│  📍 Zone 25 · Building 43 · St 890    │
│  [🗺️ Navigate to Customer]            │
├────────────────────────────────────────┤
│  ORDER DETAILS                         │
│  Items: 3 packages (perfume)           │
│  COD Amount: 250 QR                    │
│  Speed: Same Day                       │
│  Notes: "Leave at door"                │
├────────────────────────────────────────┤
│  EARNINGS                              │
│  Delivery charge: 15 QR               │
│  (Paid after delivery confirmation)   │
├────────────────────────────────────────┤
│  TASK TIMELINE                         │
│  ● Assigned  14:30                    │
│  ○ Accepted  --                       │
│  ○ Picked Up --                       │
│  ○ Delivered --                       │
└────────────────────────────────────────┘

[  REJECT  ]        [  ACCEPT TASK  ]
```

**Status Action Buttons (change by current status):**
| Current Status | Button(s) |
|----------------|-----------|
| pending | Accept / Reject |
| accepted | Picked Up |
| picked_up | Start Ride |
| in_transit / out_for_delivery | Mark Delivered / Failed |
| delivered | View Proof |

---

### 6.6 Navigation Screen (Maps)

- Full-screen Google Maps
- Driver location marker (live, updated every 10s)
- Destination pin (pickup or delivery depending on task status)
- Polyline route from driver → destination
- Bottom sheet showing:
  - Customer name + address
  - ETA (calculated from Google Maps Distance Matrix API)
  - Distance remaining
  - [Call Customer] button
  - [Open in Google Maps] → deep link to turn-by-turn
- Map type toggle: Normal / Satellite

**Location update to backend:**
```dart
// Every 30 seconds while task is active
POST /api/driver/location/
{
  "latitude": 25.2854,
  "longitude": 51.5310,
  "accuracy": 8.5,
  "speed": 40.0,
  "heading": 180.0,
  "task_id": 1234,
  "timestamp": "2026-03-21T14:30:00Z"
}
```

---

### 6.7 Delivery Proof Screen

Required before marking task as delivered.

**Steps:**
1. **Photo Capture** — Take 1–3 photos (camera or gallery)
   - Shows thumbnail previews with delete option
2. **COD Confirmation** — if cod_collected required:
   - Amount pre-filled from task
   - Checkbox: "I confirm I collected X QR from customer"
3. **Signature Pad** — customer draws signature (optional per business setting)
4. **Notes** — free text (optional)
5. **Submit** — calls `POST /api/driver/tasks/:id/complete/`

**GPS auto-captured** on submit (proof of location).

---

### 6.8 Pickup Scanner Screen

Replaces the PWA `BarcodeDetector API` scanner.

- Full-screen `mobile_scanner` camera feed
- Scan frame overlay with animated scan line
- Flashlight toggle button
- On barcode detected:
  - Vibrate (haptic feedback)
  - Show confirmation sheet: "Order #ORD-2026-1234 — Confirm pickup?"
  - [Confirm] → `POST /api/driver/tasks/:id/status/` with `{status: "picked_up"}`
- Manual entry button → text field for order number

---

### 6.9 COD Collection Screen

Lists all tasks with COD to collect (status = delivered but `cod_collected = false`).

**Per task:**
- Order number, customer name
- COD amount
- [Confirm Collected] button → marks `cod_collected = true`

**COD Submission Screen:**
- Summary of total COD in hand
- List of collected but unsubmitted tasks
- [Submit to Admin] → `POST /api/driver/cod/submit/`
- Generates DriverTransaction of type `cod_driver_settle`

---

### 6.10 Earnings Screen

**Period selector:** Today · This Week · This Month · All

```
┌─────────────────────────────────────┐
│  TOTAL EARNINGS                     │
│       2,850 QR                      │
│  This Month                         │
├─────────────────────────────────────┤
│  Deliveries: 45    COD: 12,400 QR  │
│  Pending:  320 QR  Rate: 98%       │
├─────────────────────────────────────┤
│  [Bar chart — daily earnings 7d]    │
├─────────────────────────────────────┤
│  RECENT TRANSACTIONS                │
│  + 15 QR  EARN-20260228  delivery  │
│  - 0 QR   COD-20260228  submitted  │
│  ...                                │
└─────────────────────────────────────┘
```

**Transaction Detail:** shows full breakdown — amount, type, wallet snapshot, reference.

**Settlement History:**
- List of paid/pending settlements
- Tap → settlement detail with period, deliveries, gross, deductions, net
- [Download PDF] → open PDF in device viewer

---

### 6.11 Notifications Screen

- List of all DriverNotification records
- Types with icons:
  - 🚚 `delivery_assigned` → navigate to task
  - 💰 `earnings_settled` → navigate to settlement
  - ⚠️ `alert` → show modal
  - 📢 `system` → informational
- Unread badge count on bottom nav tab
- Tap notification → mark as read + navigate to relevant screen
- [Mark All Read] button

---

### 6.12 Profile Screen

**Sections:**
1. **Driver Info** — Name, Code, Phone, Rating (stars), Total deliveries
2. **Documents** — QID, License, Passport — upload/view with expiry alerts
3. **Vehicles** — List of registered vehicles, add/edit/delete
4. **Settings** — Language (EN/AR), Biometric toggle, Notification preferences
5. **Help & Support** — FAQ, WhatsApp support button
6. **Logout**

---

## 7. Backend API Reference

### Base URL
```
Production: https://ezzydelivery.qa/api/
Development: http://localhost:8000/api/
```

### Authentication Header
```
Authorization: Token <driver_token>
Content-Type: application/json
```

### Endpoint Summary

**All endpoints use `Authorization: Token <token>` header. Base URL: `https://ezzydelivery.qa`**

#### Auth & Profile
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| POST | `/api/driver/login/` | ✅ Exists | Returns token + full driver profile |
| POST | `/api/driver/logout/` | ✅ Exists | Invalidates token + sets availability → offline |
| GET/POST | `/api/driver/profile/` | ✅ Exists | Driver info, vehicle, documents |
| POST | `/api/driver/status/` | ✅ Exists | Body: `{"availability": "available\|on_break\|offline\|returning"}` |
| POST | `/api/driver/device-token/` | ✅ Exists | FCM registration. Body: `{"token": "...", "platform": "android\|ios"}` |

#### Dashboard
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/dashboard/` | ✅ Exists | One-shot: wallet{cod_in_hand, credit_limit, available_credit, pending_earnings, wallet_usage_pct, is_wallet_warning, is_wallet_blocked} + today_stats + active_task + pending_cod_count + unread_notifications |

#### Tasks
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/tasks/` | ✅ Exists | `?status=&date=YYYY-MM-DD` |
| GET | `/api/driver/tasks/<id>/` | ✅ Exists | Full detail: address, items, customer contact, coords |
| POST | `/api/driver/tasks/<id>/accept/` | ✅ Exists | |
| POST | `/api/driver/tasks/<id>/reject/` | ✅ Exists | |
| POST | `/api/driver/tasks/<id>/status/` | ✅ Exists | `{"status": "picked_up\|start_ride\|out_for_delivery\|in_transit\|contacted"}` |
| POST | `/api/driver/tasks/<id>/complete/` | ✅ Exists | Multipart: `status`, `cod_collected`, `cod_amount_collected`, `delivery_proof`, `photo`, GPS coords |
| GET | `/api/driver/tasks/<id>/documents/` | ✅ Exists | Lists uploaded proof/signature/photos |
| POST | `/api/driver/tasks/<id>/documents/upload/` | ✅ Exists | `document_type` + `document_file` |
| GET | `/api/driver/tasks/<id>/items/` | ✅ Exists | Package contents: name, SKU, qty, price, fragile flag |
| POST | `/api/driver/tasks/<id>/report-issue/` | ✅ Exists | `{issue_type, description, latitude, longitude}` — saved as order comment |
| GET | `/api/driver/statistics/` | ✅ Exists | `?start_date=&end_date=` → totals, earnings, rating |

#### Location
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| POST | `/api/driver/location/` | ✅ Exists | `{"latitude", "longitude", "accuracy", "speed", "heading", "task_id"}` — called by Workmanager |
| GET | `/api/driver/<id>/location/` | ✅ Exists | Latest GPS ping for a driver (admin use) |

#### COD
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/cod/pending/` | ✅ Exists | Tasks with `cod_collected=True, cod_settled=False` + wallet credit bar data |
| POST | `/api/driver/cod/submit/` | ✅ Exists | Single task: `{"task_id", "payment_method": "cash\|bank\|atm\|fawran", "notes"}` |
| POST | `/api/driver/cod/submit-bulk/` | ✅ Exists | Multiple tasks: `{"task_ids": [...], "payment_method", "notes"}` → transaction_code + cod_in_hand_before/after |

#### Earnings & Finance
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/transactions/` | ✅ Exists | `?type=earning\|cod_collection\|settlement&start_date=&end_date=` |
| GET | `/api/driver/transactions/<code>/` | ✅ Exists | Full detail with balance snapshots |
| GET | `/api/driver/settlements/` | ✅ Exists | `?status=pending\|approved\|paid\|rejected` |
| GET | `/api/driver/settlements/<code>/` | ✅ Exists | Receipt detail with linked transactions |
| GET | `/api/driver/performance-metrics/` | ✅ Exists | `?period=week\|month\|all` → success_rate, completed/failed counts, earnings, rating, pending_settlement |

#### Notifications
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/notifications/` | ✅ Exists | `?unread=1` · always returns `unread_count` · max 100 |
| POST | `/api/driver/notifications/mark-read/` | ✅ Exists | `{"ids": [1,2,3]}` or `{}` for all |

#### Driver Documents
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| POST | `/api/driver/documents/upload/` | ✅ Exists | Multipart: `document_type`, `document_no`, `document_expiry_date`, `document_file`, `document_file_back` · types: QID \| Driving License \| Passport \| National Identification · update_or_create → status: pending_review |

#### Order Lookup (barcode scan at pickup)
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/order/lookup/?q=` | ✅ Exists | q = order_number or client_order_code · returns task_id, task_status, customer, cod_amount |

#### Pickup Locations
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/pickup-locations/` | ✅ Exists | Active pickup locations for currently assigned tasks → id, name, zone, street, building, lat/lon, business_name |

#### App Config (public — no auth required)
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/app-config/` | ✅ Exists | min_app_version, force_update, feature flags, store URLs, support contact |

#### Hub Batches
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/driver/hub-batches/` | ✅ Exists | Active batches with pickup location + order list |
| GET | `/api/driver/hub-batches/<id>/` | ✅ Exists | Single batch detail |
| POST | `/api/driver/hub-batches/<id>/accept/` | ✅ Exists | |
| POST | `/api/driver/hub-batches/<id>/status/` | ✅ Exists | |

#### QNAS Address (Qatar National Address System)
| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/api/qnas/get-zones/` | ✅ Exists | All Qatar zones |
| GET | `/api/qnas/get-streets/?zone=X` | ✅ Exists | Streets in a zone |
| GET | `/api/qnas/get-buildings/?zone=X&street=Y` | ✅ Exists | Buildings on a street |
| GET | `/api/qnas/search/?q=<text>` | ✅ Exists | Free-text address search |
| GET | `/api/qnas/address-details/?zone=X&street=Y&building=Z` | ✅ Exists | Full address with coordinates |
| GET | `/api/qnas/geocode/?lat=25.x&lng=51.x` | ✅ Exists | Reverse geocode → QNAS address |
| POST | `/api/qnas/coordinates/` | ✅ Exists | `{"zone","street","building"}` → lat/lng (exact or street-level) |
| GET | `/api/qnas/get-zone-polygon/<zone>/` | ✅ Exists | Zone boundary polygon for map overlay |

---
**Totals: 47 endpoints — all ✅ exist · 0 ⚠️ need creation**

### Key Request/Response Examples

#### Login
```json
// POST /api/driver/login/
// Request
{ "username": "driver001", "password": "pass123", "device_token": "fcm_token_xyz" }

// Response
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "driver": {
    "id": 12,
    "driver_code": "DRV001",
    "full_name": "Ahmed Al-Mansouri",
    "phone": "+97455123456",
    "status": "approved",
    "availability": "offline",
    "rating": 4,
    "wallet_balance": 3200.00,
    "credit_limit": 5000.00,
    "cod_in_hand": 3200.00,
    "pending_earnings": 320.00
  }
}
```

#### Task Detail
```json
// GET /api/driver/tasks/1234/
{
  "id": 1234,
  "task_number": "TASK-20260221-001",
  "status": "assigned",
  "order_number": "ORD-2026-5678",
  "customer_name": "Sara Al-Ahmad",
  "customer_phone": "+97455987654",
  "customer_address": "Building 43, St 890, Zone 25, Doha",
  "latitude": "25.2854",
  "longitude": "51.5310",
  "dl_zone": "25",
  "cod_amount": "250.00",
  "cod_collected": false,
  "driver_earnings": "15.00",
  "dl_category": "Regular",
  "dl_speed": "Same Day",
  "preferred_time": "2pm-6pm",
  "package_description": "3 perfume boxes",
  "created_at": "2026-03-21T10:00:00Z",
  "assigned_at": "2026-03-21T10:05:00Z",
  "failure_reason": null,
  "pickup_location": {
    "name": "EzzyDelivery Warehouse",
    "address": "Fareej Sudan, Doha",
    "latitude": "25.2650",
    "longitude": "51.5200"
  }
}
```

#### Update Task Status
```json
// POST /api/driver/tasks/1234/status/
{ "status": "picked_up", "latitude": "25.2650", "longitude": "51.5200" }

// Response
{ "success": true, "task": { ... updated task ... } }
```

#### Complete Delivery (with proof)
```json
// POST /api/driver/tasks/1234/complete/
// multipart/form-data
{
  "status": "delivered",
  "cod_collected": true,
  "cod_collected_amount": "250.00",
  "completion_latitude": "25.2854",
  "completion_longitude": "51.5310",
  "notes": "Left with security guard",
  "photos": [<file>, <file>],
  "signature": <file>
}
```

---

## 8. Data Models (Dart)

### DriverModel
```dart
@JsonSerializable()
class DriverModel {
  final int id;
  final String driverCode;
  final String fullName;
  final String phone;
  final String status;           // approved, suspended, blocked
  final String availability;     // offline, available, on_delivery, on_break
  final int rating;
  final double walletBalance;
  final double creditLimit;
  final double codInHand;
  final double pendingEarnings;
  final double totalEarnings;
  final String? profilePicture;
  final String? driverLanguages;

  // Computed
  double get availableCredit => creditLimit - codInHand;
  double get walletUsagePercent => (codInHand / creditLimit) * 100;
  bool get isWalletWarning => walletUsagePercent >= 80;
  bool get isWalletBlocked => codInHand >= creditLimit;
}
```

### DeliveryTaskModel
```dart
@JsonSerializable()
class DeliveryTaskModel {
  final int id;
  final String taskNumber;
  final String status;
  final String orderNumber;
  final String customerName;
  final String customerPhone;
  final String customerAddress;
  final String? latitude;
  final String? longitude;
  final String? dlZone;
  final double codAmount;
  final bool codCollected;
  final double driverEarnings;
  final String dlCategory;
  final String dlSpeed;
  final String? preferredTime;
  final String? packageDescription;
  final DateTime createdAt;
  final DateTime? assignedAt;
  final DateTime? completedAt;
  final String? failureReason;
  final PickupLocationModel? pickupLocation;

  Color get statusColor => TaskStatusHelper.color(status);
  String get statusLabel => TaskStatusHelper.label(status);
}
```

### WalletStatusModel
```dart
@JsonSerializable()
class WalletStatusModel {
  final double codInHand;
  final double creditLimit;
  final double pendingEarnings;
  final double totalEarnings;
  final bool isBlocked;
  final bool isWarning;
  final double availableCredit;
  final double usagePercent;
}
```

### TransactionModel
```dart
@JsonSerializable()
class TransactionModel {
  final String transactionCode;
  final String transactionType;  // earning, cod_collection, settlement, deduction
  final double amount;
  final String description;
  final DateTime createdAt;
  final double walletBalanceAfter;
  final double codInHandAfter;
  final double pendingEarningsAfter;
}
```

---

## 9. Authentication & Security

### Token Flow
```
Login → Store token in flutter_secure_storage
↓
Every API request → inject "Authorization: Token <token>"
↓
On 401 response → clear token → redirect to Login
```

### Secure Storage Keys
```dart
static const tokenKey        = 'driver_token';
static const driverIdKey     = 'driver_id';
static const fcmTokenKey     = 'fcm_token';
static const biometricKey    = 'biometric_enabled';
```

### Dio Interceptor (Token + Error Handling)
```dart
class AuthInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = secureStorage.read(key: 'driver_token');
    if (token != null) {
      options.headers['Authorization'] = 'Token $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (err.response?.statusCode == 401) {
      // Clear auth + navigate to login
      authProvider.logout();
    }
    handler.next(err);
  }
}
```

### Security Checklist
- ✅ Token stored in Keychain (iOS) / Keystore (Android) via `flutter_secure_storage`
- ✅ HTTPS only — reject plain HTTP in production
- ✅ Certificate pinning via Dio's `BadCertificateCallback`
- ✅ Biometric authentication option after first login
- ✅ Auto-logout after 30 min inactivity
- ✅ Code obfuscation: `flutter build apk --obfuscate --split-debug-info`
- ✅ No sensitive data in SharedPreferences (only in SecureStorage)
- ✅ API errors logged locally but not shown raw to user

---

## 10. State Management

### Riverpod Providers

```dart
// Auth
@riverpod
class AuthNotifier extends _$AuthNotifier {
  AsyncValue<DriverModel?> build() => const AsyncData(null);
  Future<void> login(String username, String password) async { ... }
  Future<void> logout() async { ... }
}

// Task List (auto-refreshing)
@riverpod
Future<List<DeliveryTaskModel>> driverTasks(
  Ref ref, {
  String? status,
  String? date,
}) async {
  return ref.watch(taskRepositoryProvider).getTasks(status: status, date: date);
}

// Active Task
@riverpod
DeliveryTaskModel? activeTask(Ref ref) {
  final tasks = ref.watch(driverTasksProvider(status: 'in_transit'));
  return tasks.valueOrNull?.firstOrNull;
}

// Wallet Status
@riverpod
Future<WalletStatusModel> walletStatus(Ref ref) async {
  return ref.watch(earningsRepositoryProvider).getWalletStatus();
}

// Location (stream)
@riverpod
Stream<Position> driverLocation(Ref ref) {
  return Geolocator.getPositionStream(
    locationSettings: const LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 50,
    ),
  );
}
```

---

## 11. Background Services

### GPS Tracking (Workmanager)
```dart
// Register background task on login
Workmanager().registerPeriodicTask(
  'location_update',
  'locationUpdateTask',
  frequency: const Duration(seconds: 30),
  constraints: Constraints(networkType: NetworkType.connected),
);

// Task handler
@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    if (task == 'locationUpdateTask') {
      final position = await Geolocator.getCurrentPosition();
      final taskId = await LocalStorage.getActiveTaskId();
      if (taskId != null) {
        await LocationApi.updateLocation(position, taskId);
      }
    }
    return Future.value(true);
  });
}
```

### Android Foreground Service
When driver is actively on a task, show persistent notification:
```
EzzyDelivery Driver
📍 Tracking active — TASK-20260228-001
[Stop Tracking]
```

---

## 12. Push Notifications

### Firebase Setup
1. Create Firebase project `ezzydelivery-driver-app`
2. Add Android (`com.ezzydelivery.driver`) + iOS (`com.ezzydelivery.driver`) apps
3. Download `google-services.json` + `GoogleService-Info.plist`

### Notification Types & Actions
| Type | Title | Body | On Tap |
|------|-------|------|--------|
| `delivery_assigned` | New Task Assigned | Task #TASK-001 ready | Open task detail |
| `cod_reminder` | COD Reminder | Submit 3,200 QR COD soon | Open COD submission |
| `earnings_settled` | Payment Settled | 320 QR transferred | Open settlement |
| `wallet_warning` | Wallet Warning | 80% wallet used | Open COD submission |
| `wallet_blocked` | Wallet Blocked | Submit COD immediately | Open COD submission |
| `system` | EzzyDelivery | <message> | Open notifications |

### Backend Integration (Django → FCM)
```python
# Django side — send FCM via firebase-admin SDK
from firebase_admin import messaging

def send_driver_notification(driver, notif_type, task=None):
    token = driver.fcm_token
    if not token:
        return

    msg = messaging.Message(
        notification=messaging.Notification(
            title=NOTIFICATION_TITLES[notif_type],
            body=build_body(notif_type, task),
        ),
        data={
            'type': notif_type,
            'task_id': str(task.id) if task else '',
        },
        token=token,
    )
    messaging.send(msg)
```

### Register Device Token (Flutter)
```dart
// On login, get FCM token and send to backend
final fcmToken = await FirebaseMessaging.instance.getToken();
await api.registerDeviceToken(fcmToken);

// POST /api/driver/device-token/
// { "fcm_token": "fXm_token_abc123...", "platform": "android" }
```

---

## 13. Offline Mode

### Strategy
| Data | Offline Behavior |
|------|-----------------|
| Task list | Show cached tasks from last sync |
| Task detail | Show cached detail |
| Status updates | Queue locally, sync on reconnect |
| GPS pings | Queue locally (max 100 pings), sync on reconnect |
| Delivery proof | Store photos locally, upload on reconnect |
| Earnings | Show last cached data with "last updated" timestamp |

### Offline Queue Implementation
```dart
class OfflineQueue {
  Future<void> addRequest(QueuedRequest request) async { ... }

  Future<void> processQueue() async {
    final pending = await localDb.getPendingRequests();
    for (final req in pending) {
      try {
        await apiClient.execute(req);
        await localDb.markProcessed(req.id);
      } catch (e) {
        // Keep in queue for next sync
      }
    }
  }
}

// Listen for connectivity
connectivity.onConnectivityChanged.listen((result) {
  if (result != ConnectivityResult.none) {
    offlineQueue.processQueue();
  }
});
```

### Connectivity Banner (always visible when offline)
```dart
class ConnectivityBanner extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isOnline = ref.watch(connectivityProvider);
    if (isOnline) return const SizedBox.shrink();
    return Container(
      color: AppColors.warning,
      padding: const EdgeInsets.all(8),
      child: const Row(
        children: [
          Icon(Icons.wifi_off, color: Colors.white, size: 16),
          SizedBox(width: 8),
          Text('No internet — changes will sync when connected',
               style: TextStyle(color: Colors.white, fontSize: 12)),
        ],
      ),
    );
  }
}
```

---

## 14. Development Phases

### Phase 1 — Foundation (Week 1–2)
- [ ] Flutter project setup with Clean Architecture folder structure
- [ ] Dio HTTP client with auth interceptor
- [ ] Secure storage for token
- [ ] Login screen + API integration (`POST /api/driver/login/`)
- [ ] GoRouter navigation setup
- [ ] Bottom navigation shell
- [ ] Brand theme (colors, typography, spacing)
- [ ] Basic error handling + connectivity check

**Deliverable:** Working login → dashboard skeleton

---

### Phase 2 — Core Features (Week 3–4)
- [ ] Dashboard screen (wallet status, stats, active task card)
- [ ] Task list screen (tabbed: Available / Active / Completed / Failed)
- [ ] Task detail screen (customer info, order details, action buttons)
- [ ] Accept / Reject task functionality
- [ ] Status update flow (picked_up → in_transit → delivered)
- [ ] Driver availability toggle (Online/Offline/Break)

**Deliverable:** Full task lifecycle working end-to-end

---

### Phase 3 — Navigation & Proof (Week 5–6)
- [ ] Google Maps integration (full-screen map + route polyline)
- [ ] Live driver location on map (updates every 10s)
- [ ] Navigate to pickup / delivery (deep link to Google Maps)
- [ ] GPS location updates to backend (every 30s)
- [ ] Delivery proof screen (photo capture, signature pad, notes)
- [ ] Barcode/QR scanner for pickup confirmation
- [ ] COD collection confirmation form

**Deliverable:** Full delivery flow including maps, proof, COD

---

### Phase 4 — Earnings & Wallet (Week 7–8)
- [ ] Earnings screen (period filter, stats, chart)
- [ ] Transaction history list + detail
- [ ] Settlement history + PDF download
- [ ] COD submission screen
- [ ] Wallet status progress bar with alerts
- [ ] Driver profile screen (info, rating display)
- [ ] Documents screen (upload/view)
- [ ] Vehicles screen (add/edit/delete)

**Deliverable:** Complete financial/profile section

---

### Phase 5 — Notifications & Background (Week 9–10)
- [ ] Firebase push notifications setup
- [ ] In-app notification center
- [ ] Background GPS tracking service (Workmanager)
- [ ] Offline mode + request queue
- [ ] Connectivity banner
- [ ] Auto-sync on reconnect
- [ ] Biometric authentication
- [ ] Settings screen (language, biometric toggle)

**Deliverable:** Production-ready feature complete app

---

### Phase 6 — Testing & Launch (Week 11–12)
- [ ] Unit tests (repositories, use cases, providers)
- [ ] Widget tests (key screens)
- [ ] Integration tests (login → task → deliver flow)
- [ ] Performance profiling (frame rate, memory)
- [ ] Real device testing (Android + iOS)
- [ ] Code obfuscation + release builds
- [ ] Google Play Store submission
- [ ] Apple App Store submission
- [ ] Post-launch bug monitoring (Firebase Crashlytics)

**Deliverable:** Live on Google Play + App Store

---

## 15. Testing Strategy

### Unit Tests (Dart `test` package)
```
test/
├── data/
│   ├── auth_repository_test.dart
│   ├── task_repository_test.dart
│   └── earnings_repository_test.dart
├── domain/
│   ├── accept_task_usecase_test.dart
│   └── update_status_usecase_test.dart
└── utils/
    ├── currency_formatter_test.dart
    └── validator_test.dart
```

### Widget Tests
```
test/
└── presentation/
    ├── login_screen_test.dart
    ├── dashboard_screen_test.dart
    ├── task_card_test.dart
    └── wallet_progress_bar_test.dart
```

### Manual Test Checklist
```
Authentication:
□ Login with valid credentials → Dashboard
□ Login with wrong credentials → error message
□ Suspended driver → blocked message + logout
□ Biometric login (if enrolled)
□ Auto-logout on token expiry

Tasks:
□ Task list loads with correct tabs
□ Accept task → status changes to accepted
□ Reject task → removed from list
□ Full delivery flow: accept → pickup → transit → delivered
□ Failure flow: accept → failure reason → reschedule
□ Pull to refresh works

Maps & Navigation:
□ Map loads with driver location
□ Route drawn from driver → destination
□ Deep link opens Google Maps
□ Location updates sent every 30s
□ Background tracking works when app minimized

Delivery Proof:
□ Camera opens and captures photo
□ Multiple photos can be added
□ Signature captured
□ Form submits with GPS coordinates
□ COD amount validated

COD & Earnings:
□ Wallet % bar shows correctly
□ Warning alert at 80%
□ Blocked alert at 100%
□ COD submission updates wallet balance
□ Transactions load with correct amounts

Offline:
□ App shows offline banner when no internet
□ Cached tasks displayed when offline
□ Status updates queued and synced on reconnect
□ GPS pings queued when offline

Push Notifications:
□ New task notification received + tap navigates correctly
□ COD reminder notification
□ Settlement notification
```

---

## 16. Deployment

### Android — Google Play Store
```bash
# 1. Create keystore (one-time)
keytool -genkey -v -keystore ezzy-driver.keystore \
  -alias ezzy-driver -keyalg RSA -keysize 2048 -validity 10000

# 2. Build release AAB
flutter build appbundle --release \
  --obfuscate \
  --split-debug-info=build/debug-info

# 3. Upload to Google Play Console
#    Package: com.ezzydelivery.driver
```

**Play Store Metadata:**
- App name: EzzyDelivery Driver
- Category: Business
- Target audience: Delivery drivers in Qatar
- Permissions required: Location (background), Camera, Storage, Notifications

### iOS — App Store
```bash
# Build release IPA
flutter build ios --release

# Upload via Xcode → Product → Archive → Distribute
# Bundle ID: com.ezzydelivery.driver
```

**App Store Requirements:**
- Location Always permission justification (background tracking)
- Camera permission justification (delivery proof)
- NSLocationAlwaysAndWhenInUseUsageDescription
- NSCameraUsageDescription

### Environment Configuration
```dart
// .env (not committed) or --dart-define flags
class AppConfig {
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://ezzydelivery.qa/api/',
  );
  static const googleMapsApiKey = String.fromEnvironment('MAPS_KEY');
  static const isProduction = bool.fromEnvironment('PROD', defaultValue: false);
}
```

### Release Build Command
```bash
flutter build appbundle \
  --release \
  --dart-define=API_BASE_URL=https://ezzydelivery.qa/api/ \
  --dart-define=MAPS_KEY=YOUR_GOOGLE_MAPS_KEY \
  --dart-define=PROD=true \
  --obfuscate \
  --split-debug-info=build/symbols
```

---

## 17. What's Already Built (PWA Reference)

The following functionality is already live in the Django PWA and should be mirrored exactly in Flutter:

| PWA Template | Flutter Screen | Status |
|---|---|---|
| `fleet_dashboard_pwa.html` | `DashboardScreen` | 🔵 Build |
| `driver_tasks_pwa.html` | `TaskListScreen` | 🔵 Build |
| `task_navigation_pwa.html` | `TaskNavigationScreen` | 🔵 Build |
| `pickup_scanner_pwa.html` | `PickupScannerScreen` | 🔵 Build |
| `cod_collection_pwa.html` | `CodCollectionScreen` | 🔵 Build |
| `cod_submission_pwa.html` | `CodSubmissionScreen` | 🔵 Build |
| `driver_earnings_pwa.html` | `EarningsScreen` | 🔵 Build |
| `driver_profile_pwa.html` | `ProfileScreen` | 🔵 Build |
| `driver_settings_pwa.html` | `SettingsScreen` | 🔵 Build |
| `driver_notifications_pwa.html` | `NotificationsScreen` | 🔵 Build |

**Native-only additions (no PWA equivalent):**
- Biometric login
- Background GPS tracking service
- Offline request queue with auto-sync
- Push notification deep linking
- Certificate pinning
- Real native maps (vs. iframe embed)
- Native camera with image compression

---

## 18. API Endpoints Needing Creation (Django)

Add to `ezzy_api/views.py` + register in `ezzy_api/urls.py`.
All endpoints require `TokenAuthentication` + `IsAuthenticated`.

---

### 1. `POST /api/driver/cod/submit/`

**Purpose:** Driver submits collected COD cash to the admin office.

**Implementation notes:**
- Call `WalletService.submit_cod_to_admin(driver, amount, payment_method, delivery_ids)` — already in `fleet/wallet_service.py`
- `task_ids` is optional; if omitted, submits all tasks where `cod_collected=True` and `cod_settled=False`
- Reduces `driver.cod_in_hand`, marks tasks `cod_settled=True`, sets order status → `cod_with_ezzy`
- Records a `cod_driver_settle` transaction (auto-code prefix `CODS-`)

**Request body:**
```json
{
  "amount": "850.00",
  "payment_method": "cash",
  "task_ids": [1234, 1235],
  "notes": "Handed to Ahmed at counter"
}
```
`payment_method` options: `cash` | `bank` | `atm` | `fawran`
`task_ids` is optional — omit to submit all pending COD tasks at once.

**Response (201):**
```json
{
  "transaction_code": "CODS-20260322-001",
  "submitted_amount": "850.00",
  "payment_method": "cash",
  "cod_in_hand_before": "850.00",
  "cod_in_hand_after": "0.00",
  "tasks_settled": 2,
  "submitted_at": "2026-03-22T14:30:00Z"
}
```

**Error cases:**
- `400` — `amount` exceeds `driver.cod_in_hand` (cannot over-submit)
- `400` — `task_ids` includes tasks where `cod_collected=False`
- `403` — driver is not approved or suspended

---

### 2. `GET /api/driver/cod/pending/`

**Purpose:** Lists all tasks where the driver collected COD but hasn't submitted it yet.

**Implementation notes:**
- Query: `DeliveryTask.objects.filter(driver=driver, cod_collected=True, cod_settled=False)`
- Status is typically `delivered` but may be `failed` for partial COD collections
- Always include wallet usage so Flutter can display the credit bar and warning/blocked state
- Optional `?date=YYYY-MM-DD` to filter by `cod_collected_at` date

**Response (200):**
```json
{
  "total_pending_cod": "850.00",
  "cod_in_hand": "850.00",
  "credit_limit": "5000.00",
  "wallet_usage_pct": 17.0,
  "is_wallet_warning": false,
  "is_wallet_blocked": false,
  "tasks": [
    {
      "task_id": 1234,
      "task_number": "TASK-20260322-001",
      "order_number": "ORD-2026-5678",
      "customer_name": "Sara Al-Ahmad",
      "cod_collected_amount": "600.00",
      "cod_collected_at": "2026-03-22T12:00:00Z",
      "cod_settled": false
    },
    {
      "task_id": 1235,
      "task_number": "TASK-20260322-002",
      "order_number": "ORD-2026-5679",
      "customer_name": "Khalid Al-Dosari",
      "cod_collected_amount": "250.00",
      "cod_collected_at": "2026-03-22T13:15:00Z",
      "cod_settled": false
    }
  ]
}
```

`is_wallet_warning` = True when usage ≥ 80% of `credit_limit`
`is_wallet_blocked` = True when `cod_in_hand >= credit_limit` — driver cannot accept more COD orders

---

### 3. `GET /api/driver/transactions/`

**Purpose:** Full transaction history — earnings, COD events, bonuses, deductions, settlements.

**Implementation notes:**
- Query: `DriverTransaction.objects.filter(driver=driver).order_by('-created_at')`
- Paginate at `page_size=20`
- Supports `?type=` and `?start_date=` / `?end_date=` filters
- Return `period_total` (sum of amounts in filtered results) for the header summary card in Flutter

**Query params:**
- `?type=earning` — filter by type: `earning` | `cod_collection` | `cod_driver_settle` | `settlement` | `deduction` | `bonus` | `adjustment`
- `?start_date=2026-03-01&end_date=2026-03-31`
- `?page=2`

**Response (200):**
```json
{
  "count": 47,
  "next": "/api/driver/transactions/?page=2",
  "previous": null,
  "period_total": "1240.00",
  "results": [
    {
      "transaction_code": "EARN-20260322-003",
      "transaction_type": "earning",
      "type_label": "Delivery Earning",
      "amount": "15.00",
      "description": "Earning for TASK-20260322-001",
      "payment_method": null,
      "reference_number": null,
      "wallet_balance_after": "0.00",
      "cod_in_hand_after": "600.00",
      "pending_earnings_after": "15.00",
      "related_task_id": 1234,
      "created_at": "2026-03-22T12:05:00Z"
    }
  ]
}
```

Snapshots (`wallet_balance_after`, `cod_in_hand_after`, `pending_earnings_after`) are recorded automatically by `WalletService.record_transaction()` — these provide an audit trail Flutter can display per-row.

---

### 4. `GET /api/driver/transactions/<code>/`

**Purpose:** Full detail for a single transaction by `transaction_code`.

**Implementation notes:**
- Lookup: `DriverTransaction.objects.get(transaction_code=code, driver=driver)` — always scope to requesting driver
- Include related task summary if `delivery_task` FK is set
- Include `settlement_code` if the transaction belongs to a settlement batch

**Response (200):**
```json
{
  "transaction_code": "CODS-20260322-001",
  "transaction_type": "cod_driver_settle",
  "type_label": "COD Submitted to Admin",
  "amount": "-850.00",
  "description": "COD submission — 2 tasks",
  "payment_method": "cash",
  "reference_number": null,
  "notes": "Handed to Ahmed at counter",
  "wallet_balance_after": "0.00",
  "cod_in_hand_after": "0.00",
  "pending_earnings_after": "320.00",
  "related_task": null,
  "settlement_code": null,
  "created_by": "admin",
  "created_at": "2026-03-22T14:30:00Z"
}
```

Returns `404` if the code doesn't exist or belongs to a different driver.

---

### 5. `GET /api/driver/settlements/`

**Purpose:** Lists all settlement batches for the driver — periodic payout records created by admin.

**Implementation notes:**
- Query: `DriverSettlement.objects.filter(driver=driver).order_by('-created_at')`
- Filter by `?status=pending|approved|paid|rejected`
- Include `pending_count` and `total_paid` in the response header so Flutter can show the earnings summary banner
- Most recent settlement is shown prominently on the Earnings tab

**Response (200):**
```json
{
  "count": 8,
  "pending_count": 1,
  "total_paid": "4800.00",
  "results": [
    {
      "settlement_code": "STL-12-1711108800",
      "period_start": "2026-03-01",
      "period_end": "2026-03-15",
      "total_deliveries": 42,
      "gross_earnings": "630.00",
      "deductions": "0.00",
      "bonuses": "50.00",
      "net_amount": "680.00",
      "status": "paid",
      "payment_method": "bank",
      "paid_at": "2026-03-17T09:00:00Z",
      "created_at": "2026-03-16T10:00:00Z"
    }
  ]
}
```

---

### 6. `GET /api/driver/settlements/<code>/`

**Purpose:** Full settlement detail including all linked transactions for receipt display.

**Implementation notes:**
- Lookup: `DriverSettlement.objects.get(settlement_code=code, driver=driver)`
- Include all `DriverTransaction` records where `settlement=settlement_obj`
- `approved_by` and `paid_at` render a receipt-style detail page in Flutter

**Response (200):**
```json
{
  "settlement_code": "STL-12-1711108800",
  "period_start": "2026-03-01",
  "period_end": "2026-03-15",
  "total_deliveries": 42,
  "gross_earnings": "630.00",
  "deductions": "0.00",
  "bonuses": "50.00",
  "net_amount": "680.00",
  "status": "paid",
  "payment_method": "bank",
  "payment_reference": "QNB-TXN-20260317-001",
  "approved_by": "Operations Manager",
  "approved_at": "2026-03-16T16:00:00Z",
  "paid_at": "2026-03-17T09:00:00Z",
  "notes": "",
  "transactions": [
    {
      "transaction_code": "EARN-20260301-001",
      "transaction_type": "earning",
      "amount": "15.00",
      "description": "Earning for TASK-20260301-001",
      "created_at": "2026-03-01T11:30:00Z"
    }
  ]
}
```

---

### 7. `GET /api/driver/notifications/`

**Purpose:** In-app notification feed for the driver.

**Implementation notes:**
- Query: `DriverNotification.objects.filter(driver=driver).order_by('-created_at')[:100]`
- `?unread=1` filters to `is_read=False` only
- Always return `unread_count` so Flutter can update the tab badge independently of loading the full list
- `notification_type` values: `delivery_assigned` | `cod_collected` | `earnings_settled` | `order_comment` | `alert` | `system`
- If `related_task_id` is not null, Flutter deep-links to that task's detail screen on tap

**Response (200):**
```json
{
  "unread_count": 3,
  "notifications": [
    {
      "id": 45,
      "title": "New Delivery Assigned",
      "message": "TASK-20260322-005 has been assigned to you",
      "notification_type": "delivery_assigned",
      "related_task_id": 1239,
      "is_read": false,
      "created_at": "2026-03-22T15:00:00Z",
      "read_at": null
    },
    {
      "id": 44,
      "title": "Settlement Paid",
      "message": "Your settlement STL-12-1711108800 of QR 680 has been paid",
      "notification_type": "earnings_settled",
      "related_task_id": null,
      "is_read": true,
      "created_at": "2026-03-17T09:05:00Z",
      "read_at": "2026-03-17T09:10:00Z"
    }
  ]
}
```

---

### 8. `POST /api/driver/notifications/mark-read/`

**Purpose:** Mark one, several, or all notifications as read.

**Implementation notes:**
- If `ids` key present → mark only those IDs (verify they belong to the requesting driver)
- If body is empty or `{}` → mark ALL unread for this driver
- Set `is_read=True`, `read_at=timezone.now()`
- Return updated `unread_count` so Flutter clears the badge immediately without a second request

**Request body (option A — specific IDs):**
```json
{ "ids": [45, 46, 47] }
```

**Request body (option B — mark all):**
```json
{}
```

**Response (200):**
```json
{
  "marked_count": 3,
  "unread_count": 0
}
```

---

### 9. `POST /api/driver/device-token/`

**Purpose:** Register or refresh the driver's FCM push notification token after app launch or Firebase token rotation.

**Implementation notes:**
- Store on `Driver` model (add `fcm_token` + `fcm_platform` fields) or a dedicated `DriverDeviceToken` model
- `platform` distinguishes Android (FCM direct) vs iOS (APNs-via-FCM)
- If same `fcm_token` arrives from a different driver (re-login) → reassign to new driver
- If same driver sends a new token → update in place (token rotation)
- Django's notification sender (`firebase-admin` SDK) reads the stored `fcm_token` when pushing alerts

**Request body:**
```json
{
  "fcm_token": "dGhpcyBpcyBhIGZha2UgZmNtIHRva2Vu...",
  "platform": "android"
}
```
`platform`: `android` | `ios`

**Response (200):**
```json
{
  "status": "registered",
  "platform": "android",
  "updated_at": "2026-03-22T15:30:00Z"
}
```

---

### Implementation Priority Order

| # | Endpoint | Why First |
|---|---|---|
| 1 | `POST /device-token/` | Required from first launch — enables all push notifications |
| 2 | `GET /cod/pending/` | Core daily workflow — drivers check this constantly |
| 3 | `POST /cod/submit/` | Core daily workflow — pairs with pending list |
| 4 | `GET /transactions/` + `/<code>/` | Earnings tab needs this |
| 5 | `GET /settlements/` + `/<code>/` | Earnings tab — payout history |
| 6 | `GET /notifications/` + `/mark-read/` | Notification feed + badge |

### Django Files to Edit
- **Views:** `ezzy_api/views.py` — add 9 new `APIView` classes
- **URLs:** `ezzy_api/urls.py` — register 9 new routes under `driver/`
- **Wallet service reuse:** `fleet/wallet_service.py` — use existing `submit_cod_to_admin()` for endpoint 1
- **Models referenced:** `fleet/models.py` (`DriverTransaction`, `DriverSettlement`, `DriverNotification`), `delivery/models.py` (`DeliveryTask`)

---

## Summary

| Category | Detail |
|---|---|
| **Framework** | Flutter 3.x + Dart 3.x |
| **Architecture** | Clean Architecture + Riverpod |
| **Auth** | DRF Token Auth → SecureStorage |
| **Maps** | Google Maps Flutter SDK |
| **Notifications** | Firebase Cloud Messaging |
| **Background** | Workmanager (GPS every 30s) |
| **Offline** | Local queue + Hive cache |
| **Biometric** | local_auth (fingerprint/Face ID) |
| **Scanner** | mobile_scanner (barcode/QR) |
| **Screens** | 18 screens across 5 tabs |
| **Timeline** | 10–12 weeks, 2 developers |
| **Existing APIs** | 35 endpoints ready ✅ |
| **APIs to build** | 3 new endpoints needed ⚠️ (`/logout/`, `/status/`, `/dashboard/`) |
| **App IDs** | `com.ezzydelivery.driver` |
| **Target** | Android 6.0+ · iOS 12.0+ |

---

*Created: 2026-03-21 | Based on live EzzyDelivery Django codebase analysis*
