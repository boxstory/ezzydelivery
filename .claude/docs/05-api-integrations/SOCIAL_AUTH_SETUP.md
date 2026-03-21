# Social Authentication Setup Guide

## 📋 Overview

This guide explains how to set up Google and Facebook authentication for the EzzyDelivery platform using django-allauth.

**Status**: ✅ Configured (Needs API Keys)
**Providers**: Google OAuth 2.0, Facebook Login
**Framework**: django-allauth

---

## ✅ What's Already Configured

### 1. Installed Apps
```python
# ezzydelivery/settings.py
INSTALLED_APPS = [
    ...
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',      # ✅ Enabled
    'allauth.socialaccount.providers.facebook',    # ✅ Enabled
    ...
]
```

### 2. URLs Configuration
```python
# ezzydelivery/urls.py
urlpatterns = [
    ...
    path('accounts/', include('allauth.urls')),  # ✅ Configured
    ...
]
```

### 3. Settings
```python
# Site ID for django.contrib.sites
SITE_ID = 1

# Account settings
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_UNIQUE_EMAIL = True

# Provider configurations
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    },
    'facebook': {
        'METHOD': 'oauth2',
        'SCOPE': ['email', 'public_profile'],
        'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'FIELDS': ['id', 'first_name', 'last_name', 'name', 'email', 'picture'],
    }
}
```

### 4. Templates
- ✅ Login page with Google & Facebook buttons
- ✅ Signup page with Google & Facebook buttons
- ✅ Proper styling with brand colors

---

## 🔧 Setup Instructions

### Step 1: Obtain Google OAuth Credentials

#### 1.1. Go to Google Cloud Console
https://console.cloud.google.com/

#### 1.2. Create a New Project (or select existing)
- Click "Select a Project" → "New Project"
- Name: "EzzyDelivery" (or your preference)
- Click "Create"

#### 1.3. Enable Google+ API
- Go to "APIs & Services" → "Library"
- Search for "Google+ API"
- Click "Enable"

#### 1.4. Create OAuth 2.0 Credentials
- Go to "APIs & Services" → "Credentials"
- Click "Create Credentials" → "OAuth business ID"
- Application type: "Web application"
- Name: "EzzyDelivery Web Client"

**Authorized JavaScript origins:**
```
http://localhost:8000
http://127.0.0.1:8000
https://yourdomain.com
```

**Authorized redirect URIs:**
```
http://localhost:8000/accounts/google/login/callback/
http://127.0.0.1:8000/accounts/google/login/callback/
https://yourdomain.com/accounts/google/login/callback/
```

#### 1.5. Save Credentials
- Copy **Client ID**
- Copy **Client Secret**

---

### Step 2: Obtain Facebook App Credentials

#### 2.1. Go to Facebook Developers
https://developers.facebook.com/

#### 2.2. Create a New App
- Click "Create App"
- Use case: "Consumer"
- App name: "EzzyDelivery"
- Contact email: your-email@example.com
- Click "Create App"

#### 2.3. Add Facebook Login Product
- In the app dashboard, click "Add Product"
- Find "Facebook Login" and click "Set Up"

#### 2.4. Configure OAuth Settings
- Go to "Facebook Login" → "Settings"

**Valid OAuth Redirect URIs:**
```
http://localhost:8000/accounts/facebook/login/callback/
http://127.0.0.1:8000/accounts/facebook/login/callback/
https://yourdomain.com/accounts/facebook/login/callback/
```

**Client OAuth Settings:**
- Business OAuth Login: YES
- Web OAuth Login: YES
- Use Strict Mode for Redirect URIs: YES

#### 2.5. Get App Credentials
- Go to "Settings" → "Basic"
- Copy **App ID** (this is your Business ID)
- Copy **App Secret** (click "Show" to reveal)

#### 2.6. Make App Live (When Ready for Production)
- Toggle "App Mode" from "Development" to "Live"
- Complete the app review if required

---

### Step 3: Configure Django Admin

#### 3.1. Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

#### 3.2. Create Superuser (if not exists)
```bash
python manage.py createsuperuser
```

#### 3.3. Access Django Admin
http://localhost:8000/admin/

#### 3.4. Configure Site
- Go to "Sites" → "Sites"
- Edit the existing site (ID: 1)
- Domain name: `localhost:8000` (or your domain)
- Display name: `EzzyDelivery`
- Save

#### 3.5. Add Social Applications

**For Google:**
- Go to "Social accounts" → "Social applications"
- Click "Add Social Application"
- Provider: **Google**
- Name: `Google OAuth`
- Business ID: [Paste Google Business ID]
- Secret key: [Paste Google Business Secret]
- Sites: Select "localhost:8000" (or your domain)
- Save

**For Facebook:**
- Click "Add Social Application" again
- Provider: **Facebook**
- Name: `Facebook Login`
- Business ID: [Paste Facebook App ID]
- Secret key: [Paste Facebook App Secret]
- Sites: Select "localhost:8000" (or your domain)
- Save

---

### Step 4: Environment Variables (Optional but Recommended)

Create/update `.env` file:

```env
# Social Auth - Google
GOOGLE_CLIENT_ID=your-google-client-id-here
GOOGLE_CLIENT_SECRET=your-google-client-secret-here

# Social Auth - Facebook
FACEBOOK_APP_ID=your-facebook-app-id-here
FACEBOOK_APP_SECRET=your-facebook-app-secret-here
```

Then update `settings.py` to use environment variables:

```python
# Add to settings.py
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': config('GOOGLE_CLIENT_ID', default=''),
            'secret': config('GOOGLE_CLIENT_SECRET', default=''),
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    },
    'facebook': {
        'APP': {
            'client_id': config('FACEBOOK_APP_ID', default=''),
            'secret': config('FACEBOOK_APP_SECRET', default=''),
        },
        'METHOD': 'oauth2',
        'SCOPE': ['email', 'public_profile'],
        'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'FIELDS': ['id', 'first_name', 'last_name', 'name', 'email', 'picture'],
    }
}
```

---

## 🧪 Testing

### Test Google Login
1. Go to http://localhost:8000/accounts/login/
2. Click "Continue with Google"
3. Select your Google account
4. Grant permissions
5. Should redirect back and be logged in

### Test Facebook Login
1. Go to http://localhost:8000/accounts/login/
2. Click "Continue with Facebook"
3. Log in to Facebook if not already
4. Grant permissions
5. Should redirect back and be logged in

### Test Signup
- Both providers should work from signup page as well
- User account will be created automatically

---

## 🔒 Security Considerations

### Production Checklist
- [ ] Use HTTPS only (enforce SSL)
- [ ] Update authorized redirect URIs to production domain
- [ ] Store credentials in environment variables (not in code)
- [ ] Enable Facebook app review and make live
- [ ] Verify Google API quotas
- [ ] Add proper error handling
- [ ] Implement rate limiting
- [ ] Log authentication attempts
- [ ] Add CSRF protection (already in Django)

### Security Settings
```python
# Add to settings.py for production
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # Social auth over HTTPS only
    ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'
```

---

## 📝 Available URLs

After setup, these URLs will be active:

```
# Google Auth
/accounts/google/login/                  # Initiates Google login
/accounts/google/login/callback/         # Google redirect URI

# Facebook Auth
/accounts/facebook/login/                # Initiates Facebook login
/accounts/facebook/login/callback/       # Facebook redirect URI

# General
/accounts/login/                         # Login page (with social buttons)
/accounts/signup/                        # Signup page (with social buttons)
/accounts/logout/                        # Logout
```

---

## 🛠️ Troubleshooting

### "Site matching query does not exist"
**Solution**: Run migrations and configure Site in Django admin
```bash
python manage.py migrate
python manage.py shell
>>> from django.contrib.sites.models import Site
>>> Site.objects.all()
>>> Site.objects.filter(id=1).update(domain='localhost:8000', name='EzzyDelivery')
```

### "Social Application matching query does not exist"
**Solution**: Add Social Applications in Django admin as described in Step 3.5

### "Redirect URI mismatch" (Google)
**Solution**: Ensure redirect URIs in Google Console exactly match:
```
http://localhost:8000/accounts/google/login/callback/
```

### "URL Blocked: This redirect failed" (Facebook)
**Solution**: Ensure redirect URIs in Facebook settings exactly match:
```
http://localhost:8000/accounts/facebook/login/callback/
```

### Buttons disabled on login page
**Solution**: Social apps not configured in Django admin. Complete Step 3.

### "Access denied" errors
**Solution**:
- Check app is set to "Live" mode (Facebook)
- Check API is enabled (Google)
- Verify credentials are correct
- Check user's email is verified

---

## 📚 Additional Resources

### Official Documentation
- django-allauth: https://django-allauth.readthedocs.io/
- Google OAuth: https://developers.google.com/identity/protocols/oauth2
- Facebook Login: https://developers.facebook.com/docs/facebook-login/

### Useful Commands
```bash
# Check installed providers
python manage.py shell
>>> from allauth.socialaccount import providers
>>> providers.registry.get_list()

# Check social apps
>>> from allauth.socialaccount.models import SocialApp
>>> SocialApp.objects.all()

# Check sites
>>> from django.contrib.sites.models import Site
>>> Site.objects.all()
```

---

## ✅ Checklist

### Initial Setup
- [x] Providers added to INSTALLED_APPS
- [x] URLs configured
- [x] Settings configured
- [x] Templates updated
- [ ] Google OAuth credentials obtained
- [ ] Facebook app credentials obtained
- [ ] Django admin configured
- [ ] Social apps added in admin
- [ ] Site configured in admin
- [ ] Tested on local environment

### Production Deployment
- [ ] Update authorized origins/redirect URIs
- [ ] Environment variables set
- [ ] HTTPS enabled
- [ ] Facebook app made live
- [ ] Security settings enabled
- [ ] Error handling implemented
- [ ] Analytics tracking added

---

## 🎯 Next Steps

1. **Obtain API Credentials**
   - Get Google OAuth credentials from Google Cloud Console
   - Get Facebook app credentials from Facebook Developers

2. **Configure Django Admin**
   - Add Google social application
   - Add Facebook social application
   - Verify site configuration

3. **Test Locally**
   - Test Google login
   - Test Facebook login
   - Test signup with both providers

4. **Prepare for Production**
   - Set up environment variables
   - Update redirect URIs for production
   - Enable HTTPS
   - Make Facebook app live

---

**Last Updated**: 2025-11-22
**Status**: Configured and ready for API credentials
**Version**: django-allauth 0.57+

