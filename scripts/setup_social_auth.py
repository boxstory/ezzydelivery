"""
Quick Setup Script for Social Authentication
Helps configure Google and Facebook social auth in Django admin
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp


def setup_site():
    """Configure the Django site"""
    print("\n" + "="*60)
    print("  CONFIGURING DJANGO SITE")
    print("="*60 + "\n")

    site, created = Site.objects.get_or_create(id=1)

    if created:
        print("✅ Created new site (ID: 1)")
    else:
        print(f"📝 Updating existing site (ID: 1)")

    # Get domain from user
    domain = input("\nEnter domain (default: localhost:8000): ").strip()
    if not domain:
        domain = "localhost:8000"

    name = input("Enter site name (default: EzzyDelivery): ").strip()
    if not name:
        name = "EzzyDelivery"

    site.domain = domain
    site.name = name
    site.save()

    print(f"\n✅ Site configured:")
    print(f"   Domain: {site.domain}")
    print(f"   Name: {site.name}")

    return site


def setup_google(site):
    """Configure Google OAuth"""
    print("\n" + "="*60)
    print("  CONFIGURING GOOGLE OAUTH")
    print("="*60 + "\n")

    print("To get Google credentials:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create/select project")
    print("3. Enable Google+ API")
    print("4. Create OAuth 2.0 credentials")
    print("5. Add authorized redirect URI:")
    print(f"   http://{site.domain}/accounts/google/login/callback/")
    print()

    setup = input("Do you have Google credentials? (y/n): ").strip().lower()

    if setup != 'y':
        print("\n⏭️  Skipping Google setup. Configure later in Django admin.")
        return

    client_id = input("\nEnter Google Client ID: ").strip()
    client_secret = input("Enter Google Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n❌ Both Client ID and Secret are required. Skipping.")
        return

    # Check if Google app already exists
    google_app = SocialApp.objects.filter(provider='google').first()

    if google_app:
        print(f"\n📝 Updating existing Google OAuth app (ID: {google_app.id})")
        google_app.client_id = client_id
        google_app.secret = client_secret
    else:
        print("\n✅ Creating new Google OAuth app")
        google_app = SocialApp(
            provider='google',
            name='Google OAuth',
            client_id=client_id,
            secret=client_secret
        )

    google_app.save()
    google_app.sites.add(site)

    print("\n✅ Google OAuth configured successfully!")
    print(f"   Provider: Google")
    print(f"   Client ID: {client_id[:20]}...")
    print(f"   Redirect URI: http://{site.domain}/accounts/google/login/callback/")


def setup_facebook(site):
    """Configure Facebook Login"""
    print("\n" + "="*60)
    print("  CONFIGURING FACEBOOK LOGIN")
    print("="*60 + "\n")

    print("To get Facebook credentials:")
    print("1. Go to https://developers.facebook.com/")
    print("2. Create new app (Consumer type)")
    print("3. Add Facebook Login product")
    print("4. Configure OAuth redirect URIs:")
    print(f"   http://{site.domain}/accounts/facebook/login/callback/")
    print("5. Get App ID and App Secret from Settings → Basic")
    print()

    setup = input("Do you have Facebook credentials? (y/n): ").strip().lower()

    if setup != 'y':
        print("\n⏭️  Skipping Facebook setup. Configure later in Django admin.")
        return

    app_id = input("\nEnter Facebook App ID: ").strip()
    app_secret = input("Enter Facebook App Secret: ").strip()

    if not app_id or not app_secret:
        print("\n❌ Both App ID and Secret are required. Skipping.")
        return

    # Check if Facebook app already exists
    facebook_app = SocialApp.objects.filter(provider='facebook').first()

    if facebook_app:
        print(f"\n📝 Updating existing Facebook Login app (ID: {facebook_app.id})")
        facebook_app.client_id = app_id
        facebook_app.secret = app_secret
    else:
        print("\n✅ Creating new Facebook Login app")
        facebook_app = SocialApp(
            provider='facebook',
            name='Facebook Login',
            client_id=app_id,
            secret=app_secret
        )

    facebook_app.save()
    facebook_app.sites.add(site)

    print("\n✅ Facebook Login configured successfully!")
    print(f"   Provider: Facebook")
    print(f"   App ID: {app_id[:20]}...")
    print(f"   Redirect URI: http://{site.domain}/accounts/facebook/login/callback/")


def show_status():
    """Show current social auth status"""
    print("\n" + "="*60)
    print("  CURRENT SOCIAL AUTH STATUS")
    print("="*60 + "\n")

    # Check site
    try:
        site = Site.objects.get(id=1)
        print(f"✅ Site: {site.name} ({site.domain})")
    except Site.DoesNotExist:
        print("❌ Site not configured")

    # Check social apps
    google_app = SocialApp.objects.filter(provider='google').first()
    facebook_app = SocialApp.objects.filter(provider='facebook').first()

    if google_app:
        print(f"✅ Google OAuth: Configured (ID: {google_app.id})")
    else:
        print("❌ Google OAuth: Not configured")

    if facebook_app:
        print(f"✅ Facebook Login: Configured (ID: {facebook_app.id})")
    else:
        print("❌ Facebook Login: Not configured")

    print()


def main():
    """Main setup function"""
    print("\n" + "="*60)
    print("  EZZYDELIVERY SOCIAL AUTH SETUP")
    print("="*60)

    # Show current status
    show_status()

    # Main menu
    while True:
        print("\nWhat would you like to do?")
        print("1. Configure Site")
        print("2. Configure Google OAuth")
        print("3. Configure Facebook Login")
        print("4. Configure All")
        print("5. Show Status")
        print("6. Exit")

        choice = input("\nEnter choice (1-6): ").strip()

        if choice == '1':
            site = setup_site()
        elif choice == '2':
            try:
                site = Site.objects.get(id=1)
                setup_google(site)
            except Site.DoesNotExist:
                print("\n❌ Please configure site first (Option 1)")
        elif choice == '3':
            try:
                site = Site.objects.get(id=1)
                setup_facebook(site)
            except Site.DoesNotExist:
                print("\n❌ Please configure site first (Option 1)")
        elif choice == '4':
            site = setup_site()
            setup_google(site)
            setup_facebook(site)
        elif choice == '5':
            show_status()
        elif choice == '6':
            print("\n✅ Setup complete!")
            print("\nNext steps:")
            print("1. Test login at: http://localhost:8000/accounts/login/")
            print("2. Check admin at: http://localhost:8000/admin/socialaccount/socialapp/")
            print("3. Read docs/SOCIAL_AUTH_SETUP.md for more info")
            print()
            break
        else:
            print("\n❌ Invalid choice. Please enter 1-6.")


if __name__ == '__main__':
    main()
