# Flutter Driver App Specification

## Project Overview

A comprehensive Flutter-based mobile application for delivery drivers that connects to the Django EzzyDelivery backend via REST API. This app enables drivers to manage deliveries, track earnings, navigate to destinations, and communicate with the system in real-time.

---

## 1. Technical Stack

### Frontend (Flutter)
- **Framework**: Flutter 3.x+
- **Language**: Dart 3.x+
- **Target Platforms**: Android & iOS
- **Minimum Versions**:
  - Android 6.0 (API 23+)
  - iOS 12.0+

### Key Dependencies
```yaml
dependencies:
  flutter:
    sdk: flutter

  # State Management
  provider: ^6.1.0
  riverpod: ^2.4.0

  # API & Networking
  dio: ^5.4.0
  http: ^1.1.0
  retrofit: ^4.0.0
  json_annotation: ^4.8.0

  # Authentication & Storage
  flutter_secure_storage: ^9.0.0
  shared_preferences: ^2.2.0
  jwt_decoder: ^2.0.1

  # Location & Maps
  google_maps_flutter: ^2.5.0
  geolocator: ^10.1.0
  geocoding: ^2.1.0
  url_launcher: ^6.2.0

  # Push Notifications
  firebase_messaging: ^14.7.0
  firebase_core: ^2.24.0
  flutter_local_notifications: ^16.0.0

  # Camera & Image
  image_picker: ^1.0.0
  camera: ^0.10.5
  image_cropper: ^5.0.0

  # Signature Capture
  signature: ^5.4.0

  # Background Services
  workmanager: ^0.5.1
  background_fetch: ^1.1.0

  # UI Components
  flutter_svg: ^2.0.9
  cached_network_image: ^3.3.0
  shimmer: ^3.0.0
  lottie: ^2.7.0

  # Utilities
  intl: ^0.18.1
  connectivity_plus: ^5.0.0
  permission_handler: ^11.0.0
  package_info_plus: ^5.0.0
```

---

## 2. Architecture

### Design Pattern: Clean Architecture + MVVM

```
lib/
├── core/
│   ├── constants/
│   │   ├── api_constants.dart
│   │   ├── app_colors.dart
│   │   ├── app_strings.dart
│   │   └── route_constants.dart
│   ├── errors/
│   │   ├── exceptions.dart
│   │   └── failures.dart
│   ├── network/
│   │   ├── api_client.dart
│   │   ├── dio_client.dart
│   │   └── network_info.dart
│   ├── storage/
│   │   ├── secure_storage.dart
│   │   └── local_storage.dart
│   └── utils/
│       ├── helpers.dart
│       ├── validators.dart
│       └── formatters.dart
│
├── data/
│   ├── models/
│   │   ├── driver_model.dart
│   │   ├── order_model.dart
│   │   ├── location_model.dart
│   │   └── earnings_model.dart
│   ├── repositories/
│   │   ├── auth_repository_impl.dart
│   │   ├── order_repository_impl.dart
│   │   └── location_repository_impl.dart
│   └── datasources/
│       ├── remote/
│       │   ├── auth_remote_datasource.dart
│       │   ├── order_remote_datasource.dart
│       │   └── location_remote_datasource.dart
│       └── local/
│           ├── auth_local_datasource.dart
│           └── order_local_datasource.dart
│
├── domain/
│   ├── entities/
│   │   ├── driver.dart
│   │   ├── order.dart
│   │   ├── location.dart
│   │   └── earnings.dart
│   ├── repositories/
│   │   ├── auth_repository.dart
│   │   ├── order_repository.dart
│   │   └── location_repository.dart
│   └── usecases/
│       ├── auth/
│       │   ├── login_usecase.dart
│       │   ├── logout_usecase.dart
│       │   └── refresh_token_usecase.dart
│       ├── orders/
│       │   ├── get_orders_usecase.dart
│       │   ├── accept_order_usecase.dart
│       │   ├── complete_order_usecase.dart
│       │   └── update_order_status_usecase.dart
│       └── location/
│           ├── track_location_usecase.dart
│           └── update_location_usecase.dart
│
├── presentation/
│   ├── providers/
│   │   ├── auth_provider.dart
│   │   ├── order_provider.dart
│   │   ├── location_provider.dart
│   │   └── theme_provider.dart
│   ├── screens/
│   │   ├── splash/
│   │   ├── auth/
│   │   │   ├── login_screen.dart
│   │   │   └── profile_setup_screen.dart
│   │   ├── home/
│   │   │   ├── home_screen.dart
│   │   │   └── widgets/
│   │   ├── orders/
│   │   │   ├── orders_list_screen.dart
│   │   │   ├── order_details_screen.dart
│   │   │   └── delivery_proof_screen.dart
│   │   ├── navigation/
│   │   │   └── navigation_screen.dart
│   │   ├── earnings/
│   │   │   ├── earnings_screen.dart
│   │   │   └── payment_history_screen.dart
│   │   └── profile/
│   │       ├── profile_screen.dart
│   │       └── settings_screen.dart
│   └── widgets/
│       ├── common/
│       ├── buttons/
│       └── cards/
│
└── main.dart
```

---

## 3. Authentication & Security

### Authentication Flow

#### Method: JWT Token Authentication
```dart
// API Authentication Headers
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Endpoints
```
POST /api/auth/driver/login/
POST /api/auth/driver/logout/
POST /api/auth/token/refresh/
GET  /api/auth/driver/profile/
PUT  /api/auth/driver/profile/update/
```

### Request/Response Examples

#### Login Request
```json
{
  "username": "driver123",
  "password": "SecurePass123!",
  "device_token": "fcm_device_token_here"
}
```

#### Login Response
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "driver": {
    "id": 123,
    "username": "driver123",
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "profile_picture": "https://...",
    "vehicle_type": "motorcycle",
    "vehicle_number": "ABC123",
    "status": "active",
    "rating": 4.8,
    "total_deliveries": 245
  }
}
```

### Security Features
- ✅ Secure token storage using `flutter_secure_storage`
- ✅ Automatic token refresh before expiration
- ✅ Biometric authentication (fingerprint/face unlock)
- ✅ API request encryption (HTTPS only)
- ✅ Certificate pinning for production
- ✅ Automatic logout on token invalidation

---

## 4. Core Features

### 4.1 Dashboard / Home Screen

**Features:**
- Driver status toggle (Online/Offline)
- Current order summary card
- Quick stats (Today's deliveries, earnings)
- Pending orders count
- Quick action buttons

**API Endpoints:**
```
GET  /api/driver/dashboard/
POST /api/driver/status/toggle/
```

**Dashboard Response:**
```json
{
  "driver_status": "online",
  "current_order": {
    "id": 789,
    "order_number": "ORD-2024-789",
    "status": "picked_up",
    "customer_name": "Jane Smith",
    "delivery_address": "123 Main St"
  },
  "today_stats": {
    "completed_deliveries": 8,
    "earnings": 120.50,
    "distance_traveled": 45.2,
    "average_rating": 4.9
  },
  "pending_orders_count": 3
}
```

---

### 4.2 Order Management

#### Order Statuses
```dart
enum OrderStatus {
  pending,        // Order created, waiting for driver
  assigned,       // Assigned to driver
  accepted,       // Driver accepted
  rejected,       // Driver rejected
  picked_up,      // Driver picked up from merchant
  in_transit,     // On the way to customer
  arrived,        // Arrived at delivery location
  delivered,      // Successfully delivered
  cancelled,      // Order cancelled
  failed          // Delivery failed
}
```

#### API Endpoints
```
GET  /api/driver/orders/                    # List all orders
GET  /api/driver/orders/{id}/               # Order details
POST /api/driver/orders/{id}/accept/        # Accept order
POST /api/driver/orders/{id}/reject/        # Reject order
PUT  /api/driver/orders/{id}/status/        # Update status
POST /api/driver/orders/{id}/complete/      # Complete delivery
POST /api/driver/orders/{id}/upload-proof/  # Upload proof
```

#### Order Detail Response
```json
{
  "id": 789,
  "order_number": "ORD-2024-789",
  "status": "assigned",
  "created_at": "2024-01-20T10:30:00Z",
  "pickup_time": "2024-01-20T11:00:00Z",
  "delivery_time": null,

  "merchant": {
    "name": "Pizza Palace",
    "address": "456 Restaurant Ave",
    "phone": "+1234567890",
    "location": {
      "latitude": 40.7128,
      "longitude": -74.0060
    }
  },

  "customer": {
    "name": "Jane Smith",
    "phone": "+1987654321",
    "address": "123 Main St, Apt 4B",
    "delivery_instructions": "Leave at door, ring bell",
    "location": {
      "latitude": 40.7580,
      "longitude": -73.9855
    }
  },

  "items": [
    {
      "name": "Large Pepperoni Pizza",
      "quantity": 2,
      "price": 24.99
    },
    {
      "name": "Garlic Bread",
      "quantity": 1,
      "price": 5.99
    }
  ],

  "payment": {
    "method": "credit_card",
    "total_amount": 35.98,
    "delivery_fee": 5.00,
    "driver_earning": 8.00,
    "tip": 3.00,
    "is_paid": true
  },

  "distance": {
    "pickup_to_delivery": 3.5,
    "unit": "km"
  }
}
```

#### Update Order Status
```json
// Request
{
  "status": "picked_up",
  "notes": "Package picked up from merchant",
  "location": {
    "latitude": 40.7128,
    "longitude": -74.0060
  },
  "timestamp": "2024-01-20T11:05:00Z"
}

// Response
{
  "success": true,
  "message": "Order status updated",
  "order": { /* updated order object */ }
}
```

---

### 4.3 GPS Tracking & Navigation

#### Features
- Real-time location tracking
- Background location updates (every 30 seconds)
- Route display on map
- Turn-by-turn navigation integration
- Distance calculation
- ETA estimation

#### API Endpoints
```
POST /api/driver/location/update/
GET  /api/driver/location/history/
```

#### Location Update Request
```json
{
  "latitude": 40.7128,
  "longitude": -74.0060,
  "accuracy": 10.5,
  "speed": 45.0,
  "heading": 90.0,
  "timestamp": "2024-01-20T11:10:00Z",
  "order_id": 789
}
```

#### Navigation Integration
```dart
// Open Google Maps for navigation
String origin = "${pickupLat},${pickupLng}";
String destination = "${deliveryLat},${deliveryLng}";
String url = "https://www.google.com/maps/dir/?api=1&origin=$origin&destination=$destination&travelmode=driving";
```

---

### 4.4 Delivery Proof Capture

#### Features
- Photo capture (multiple images)
- Signature capture
- Notes field
- Timestamp & location stamp

#### API Endpoint
```
POST /api/driver/orders/{id}/complete/
```

#### Complete Delivery Request
```json
{
  "status": "delivered",
  "delivery_time": "2024-01-20T11:45:00Z",
  "proof_of_delivery": {
    "photos": [
      "base64_encoded_image_1",
      "base64_encoded_image_2"
    ],
    "signature": "base64_encoded_signature",
    "notes": "Left at front door as requested",
    "location": {
      "latitude": 40.7580,
      "longitude": -73.9855
    }
  },
  "customer_rating": 5,
  "feedback": "Great service!"
}
```

---

### 4.5 Earnings & Analytics

#### Features
- Daily, weekly, monthly earnings
- Payment history
- Delivery statistics
- Performance metrics
- Tips tracking

#### API Endpoints
```
GET /api/driver/earnings/summary/
GET /api/driver/earnings/history/?period=weekly
GET /api/driver/statistics/
```

#### Earnings Summary Response
```json
{
  "today": {
    "total_earnings": 120.50,
    "base_pay": 96.00,
    "tips": 24.50,
    "deliveries_count": 12,
    "online_hours": 8.5
  },
  "week": {
    "total_earnings": 680.00,
    "base_pay": 544.00,
    "tips": 136.00,
    "deliveries_count": 68,
    "online_hours": 42.0
  },
  "month": {
    "total_earnings": 2850.00,
    "base_pay": 2280.00,
    "tips": 570.00,
    "deliveries_count": 285,
    "online_hours": 178.5
  },
  "statistics": {
    "acceptance_rate": 95.5,
    "completion_rate": 98.2,
    "average_rating": 4.8,
    "total_distance": 1240.5
  }
}
```

---

### 4.6 Push Notifications

#### Notification Types
- 🔔 New order assigned
- 📦 Order status updates
- 💰 Payment received
- ⭐ New rating/review
- 📢 System announcements
- ⚠️ Important alerts

#### Firebase Cloud Messaging Setup
```dart
// Handle foreground notifications
FirebaseMessaging.onMessage.listen((RemoteMessage message) {
  // Show local notification
});

// Handle notification tap
FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
  // Navigate to relevant screen
});
```

#### Notification Payload
```json
{
  "notification": {
    "title": "New Order Assigned",
    "body": "Order #ORD-2024-789 from Pizza Palace"
  },
  "data": {
    "type": "new_order",
    "order_id": "789",
    "action": "view_order"
  }
}
```

---

### 4.7 Offline Mode

#### Features
- Cache recent orders locally
- Queue API requests when offline
- Sync when connection restored
- Show offline indicator
- Store location updates locally

#### Implementation Strategy
```dart
// Check connectivity
ConnectivityResult result = await Connectivity().checkConnectivity();

// Queue offline requests
if (result == ConnectivityResult.none) {
  await offlineQueue.add(request);
} else {
  await apiClient.execute(request);
}

// Sync on reconnection
Connectivity().onConnectivityChanged.listen((ConnectivityResult result) {
  if (result != ConnectivityResult.none) {
    syncOfflineData();
  }
});
```

---

## 5. UI/UX Design Guidelines

### Color Scheme (Customizable)
```dart
// Primary Colors
const Color primaryColor = Color(0xFF2196F3);      // Blue
const Color primaryDark = Color(0xFF1976D2);
const Color primaryLight = Color(0xFFBBDEFB);

// Status Colors
const Color successColor = Color(0xFF4CAF50);      // Green
const Color warningColor = Color(0xFFFF9800);      // Orange
const Color errorColor = Color(0xFFF44336);        // Red
const Color infoColor = Color(0xFF2196F3);         // Blue

// Order Status Colors
const Color pendingColor = Color(0xFFFFEB3B);      // Yellow
const Color assignedColor = Color(0xFF03A9F4);     // Light Blue
const Color pickedUpColor = Color(0xFFFF9800);     // Orange
const Color deliveredColor = Color(0xFF4CAF50);    // Green
```

### Typography
```dart
// Headings
headline1: 32px, Bold
headline2: 24px, Bold
headline3: 20px, SemiBold

// Body
bodyText1: 16px, Regular
bodyText2: 14px, Regular
caption: 12px, Regular

// Buttons
button: 16px, SemiBold
```

### Key Screens Mockup Structure

#### 1. Login Screen
- App logo
- Username/Email input
- Password input
- Biometric login button
- Forgot password link
- Login button

#### 2. Home/Dashboard
- Top bar: Driver name, status toggle, notifications
- Current order card (if active)
- Quick stats cards (deliveries, earnings)
- Pending orders list
- Bottom navigation bar

#### 3. Orders List
- Filter tabs (All, Pending, Active, Completed)
- Order cards with:
  - Order number
  - Customer name
  - Pickup/delivery address
  - Status badge
  - Time info
  - Earnings

#### 4. Order Details
- Order info section
- Pickup location (with map)
- Delivery location (with map)
- Items list
- Payment details
- Customer contact buttons
- Action buttons (Accept/Reject, Update Status, Navigate)

#### 5. Navigation Screen
- Full-screen map
- Route overlay
- ETA & distance display
- Customer location marker
- Driver location marker
- Bottom sheet with order details
- Navigate button (opens Google Maps)

#### 6. Delivery Proof
- Camera preview
- Capture photo button
- Photo gallery
- Signature pad
- Notes text field
- Location display
- Submit button

#### 7. Earnings Dashboard
- Period selector (Today, Week, Month)
- Total earnings card
- Earnings breakdown chart
- Payment history list
- Statistics cards

---

## 6. Backend API Requirements

### Django REST Framework Endpoints Summary

```python
# Authentication
POST   /api/auth/driver/login/
POST   /api/auth/driver/logout/
POST   /api/auth/token/refresh/
GET    /api/auth/driver/profile/
PUT    /api/auth/driver/profile/update/

# Dashboard
GET    /api/driver/dashboard/
POST   /api/driver/status/toggle/

# Orders
GET    /api/driver/orders/
GET    /api/driver/orders/{id}/
POST   /api/driver/orders/{id}/accept/
POST   /api/driver/orders/{id}/reject/
PUT    /api/driver/orders/{id}/status/
POST   /api/driver/orders/{id}/complete/
POST   /api/driver/orders/{id}/upload-proof/

# Location
POST   /api/driver/location/update/
GET    /api/driver/location/history/

# Earnings
GET    /api/driver/earnings/summary/
GET    /api/driver/earnings/history/
GET    /api/driver/statistics/

# Notifications
POST   /api/driver/device-token/register/
GET    /api/driver/notifications/
PUT    /api/driver/notifications/{id}/read/
```

### Required Django Models

```python
# models.py (simplified structure)

class Driver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=50)
    vehicle_number = models.CharField(max_length=20)
    license_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20)  # online, offline, busy
    rating = models.DecimalField(max_digits=3, decimal_places=2)
    total_deliveries = models.IntegerField(default=0)

class Order(models.Model):
    order_number = models.CharField(max_length=50, unique=True)
    driver = models.ForeignKey(Driver, null=True, blank=True)
    status = models.CharField(max_length=20)
    merchant = models.ForeignKey(Merchant)
    customer = models.ForeignKey(Customer)
    pickup_location = models.JSONField()
    delivery_location = models.JSONField()
    items = models.JSONField()
    payment = models.JSONField()

class DriverLocation(models.Model):
    driver = models.ForeignKey(Driver)
    order = models.ForeignKey(Order, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    accuracy = models.FloatField()
    timestamp = models.DateTimeField()

class DeliveryProof(models.Model):
    order = models.OneToOneField(Order)
    photos = models.JSONField()  # Store image URLs
    signature = models.ImageField()
    notes = models.TextField()
    delivered_at = models.DateTimeField()
    location = models.JSONField()
```

---

## 7. Development Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Project setup and architecture
- [ ] Authentication implementation
- [ ] API business setup
- [ ] Secure storage implementation
- [ ] Basic navigation structure

### Phase 2: Core Features (Week 3-4)
- [ ] Dashboard/Home screen
- [ ] Orders list and details
- [ ] Order status management
- [ ] GPS location tracking
- [ ] Map integration

### Phase 3: Advanced Features (Week 5-6)
- [ ] Delivery proof capture
- [ ] Signature capture
- [ ] Image upload
- [ ] Navigation integration
- [ ] Offline mode

### Phase 4: Analytics & Polish (Week 7-8)
- [ ] Earnings dashboard
- [ ] Statistics and reports
- [ ] Push notifications
- [ ] Performance optimization
- [ ] UI/UX refinements

### Phase 5: Testing & Deployment (Week 9-10)
- [ ] Unit testing
- [ ] Integration testing
- [ ] User acceptance testing
- [ ] Bug fixes
- [ ] App store submission

---

## 8. Testing Strategy

### Unit Tests
- Authentication logic
- API business methods
- Data models
- Utility functions

### Widget Tests
- UI components
- Forms validation
- Screen navigation

### Integration Tests
- API integration
- Location tracking
- Image upload
- Offline mode sync

### Manual Testing Checklist
- [ ] Login/logout flow
- [ ] Order acceptance/rejection
- [ ] Status updates
- [ ] Photo capture
- [ ] Signature capture
- [ ] GPS tracking accuracy
- [ ] Push notifications
- [ ] Offline mode
- [ ] Network error handling
- [ ] Battery optimization

---

## 9. Performance Optimization

### Best Practices
- ✅ Lazy load images with caching
- ✅ Pagination for order lists
- ✅ Debounce location updates
- ✅ Minimize API calls
- ✅ Optimize image uploads (compress before upload)
- ✅ Use background services wisely
- ✅ Implement proper memory management
- ✅ Reduce app size (remove unused dependencies)

### Location Tracking Optimization
```dart
// Battery-friendly location settings
LocationSettings(
  accuracy: LocationAccuracy.balanced,
  distanceFilter: 50,  // Update every 50 meters
  timeInterval: 30000, // Update every 30 seconds
);
```

---

## 10. Security Best Practices

### App Security
- ✅ Store tokens in secure storage (never SharedPreferences)
- ✅ Implement certificate pinning in production
- ✅ Obfuscate code before release
- ✅ Validate all user inputs
- ✅ Use HTTPS only
- ✅ Implement rate limiting on sensitive actions
- ✅ Add biometric authentication
- ✅ Auto-logout on inactivity

### API Security
```dart
// Example: Certificate pinning
SecurityContext context = SecurityContext.defaultContext;
context.setTrustedCertificatesBytes(pemBytes);
```

---

## 11. Deployment

### Android (Google Play Store)
1. Update version in `pubspec.yaml`
2. Build release APK/AAB
   ```bash
   flutter build appbundle --release
   ```
3. Sign with keystore
4. Upload to Google Play Console
5. Complete store listing
6. Submit for review

### iOS (App Store)
1. Update version in Xcode
2. Configure signing & capabilities
3. Build archive
   ```bash
   flutter build ios --release
   ```
4. Upload via Xcode or Application Loader
5. Complete App Store Connect listing
6. Submit for review

### Environment Configuration
```dart
// lib/core/constants/environment.dart
class Environment {
  static const String API_BASE_URL = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://api.ezzydelivery.com',
  );

  static const String GOOGLE_MAPS_API_KEY = String.fromEnvironment(
    'GOOGLE_MAPS_API_KEY',
  );
}
```

---

## 12. Monitoring & Analytics

### Crash Reporting
- Firebase Crashlytics
- Sentry

### Analytics
- Firebase Analytics
- Mixpanel
- Custom event tracking

### Key Metrics to Track
- Daily active drivers
- Order acceptance rate
- Average delivery time
- App crash rate
- API error rate
- Location tracking accuracy

---

## 13. Future Enhancements

### Potential Features
- [ ] In-app chat with customers/support
- [ ] Voice navigation
- [ ] Multiple language support
- [ ] Dark mode
- [ ] Driver-to-driver communication
- [ ] Route optimization for multiple orders
- [ ] Fuel expense tracking
- [ ] Tax reporting
- [ ] Referral system
- [ ] Driver rewards/badges

---

## 14. Support & Documentation

### Developer Resources
- Flutter documentation: https://flutter.dev/docs
- Google Maps Flutter: https://pub.dev/packages/google_maps_flutter
- Firebase setup: https://firebase.google.com/docs/flutter/setup

### Contact Information
- Backend API Documentation: [Your Django API docs URL]
- Technical Support: [Support email/Slack]
- Project Repository: [GitHub/GitLab URL]

---

## 15. Questions & Customization

To customize this app for your specific needs, please provide:

1. **API Configuration**
   - Django API base URL
   - Authentication method details
   - Any existing API documentation

2. **Business Rules**
   - Order assignment logic (auto-assign vs manual accept)
   - Payment calculation method
   - Driver commission structure
   - Supported order statuses

3. **Design Assets**
   - Brand logo and colors
   - Any existing design mockups
   - Style guide if available

4. **Feature Priorities**
   - Must-have features for MVP
   - Nice-to-have features for future releases
   - Any custom requirements

---

## Conclusion

This specification provides a comprehensive blueprint for building a production-ready Flutter driver app for the EzzyDelivery platform. The architecture is scalable, maintainable, and follows industry best practices.

**Estimated Timeline**: 8-10 weeks for full implementation
**Recommended Team**: 2-3 Flutter developers + 1 Backend developer + 1 QA engineer

Ready to start development! 🚀
