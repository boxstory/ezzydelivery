# Purpose: allauth social account adapter — prefill username from the Gmail/e-mail local part on social signup
# Used by: settings.SOCIALACCOUNT_ADAPTER; /accounts/3rdparty/signup/ form initial data
# Notes: generate_unique_username sanitizes the local part and de-duplicates against existing users

from allauth.account.utils import user_email, user_username
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.utils import generate_unique_username


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not user_username(user):
            email = user_email(user) or data.get('email') or ''
            local_part = email.split('@')[0] if '@' in email else ''
            if local_part:
                user_username(user, generate_unique_username([local_part]))
        return user
