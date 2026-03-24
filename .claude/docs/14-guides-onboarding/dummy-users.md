# Dummy/Test User Credentials

## Primary Test Users (create_dummy_data command)

| Role | Username | Password | Name | Details |
|------|----------|----------|------|---------|
| Business | `testbusiness` | `TestBusiness@123` | Test Business | Business: Al Shams Electronics (ALSHAM) |
| Driver | `testdriver` | `TestDriver@123` | Hamad Al Farsi | Driver Code: DRV-DUMMY-001, ID: 153 |

## Production Drivers

| Driver ID | Code | Username | Name |
|-----------|------|----------|------|
| 53 | 224503 | ahsanhabib | AHSAN HABIB |
| 19 | 880862 | hashim | MUHAMMED HASHID |
| 17 | 690038 | MULLET22 | ALJO MULLET |

## Warehouse Test Users (warehouse/tests/generate_test_data.py)

| Role | Username | Password |
|------|----------|----------|
| Superuser | `admin` | `admin123` |
| Warehouse Manager | `warehouse_manager_1` to `warehouse_manager_4` | `manager123` |
| Warehouse Staff | `warehouse_staff_1` to `warehouse_staff_5` | `staff123` |

## Bulk Dummy Users (populate_dummy_data command)

All users created by `populate_dummy_data` use password: `testpass123`

## Unit Test Passwords

| App | Common Passwords |
|-----|-----------------|
| orders | `testpass123`, `verifypass123`, `statuspass123`, `signalpass123` |
| delivery | `taskpass123`, `driverpass123`, `statuspass123`, `assignpass123` |
| business | `businesspass123`, `apipass123`, `pickuppass123`, `ownerpass123` |

## Test Data Management

```bash
# Create dummy data
python manage.py create_dummy_data

# Clear dummy data
python manage.py create_dummy_data --clear

# Bulk populate (65+ users, 55+ businesses, 50+ drivers)
python manage.py populate_dummy_data
```

## Test Business Data

- **Name:** Al Shams Electronics
- **Code:** ALSHAM
- **Phone:** +97444123456
- **Email:** info@alshamselectronics.qa
- **Address:** Building 45, Street 810, Zone 44 (West Bay)

## Fleet Profile URLs

- Driver Dashboard: `/fleet/`
- Driver Profile (mobile): `/fleet/profile/`
- Driver Profile (public): `/fleet/profile/<fleet_id>/`
