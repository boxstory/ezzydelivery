from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from ezzy_api.models import ClientApiKey


class ClientApiKeyAuthentication(BaseAuthentication):
    """
    DRF authentication using ClientApiKey.

    Accepts either:
        Authorization: Bearer <api_key>
        X-API-Key: <api_key>

    On success, request.user is set to the owning business's user (so
    `get_api_user_business(request)` continues to scope queries by business),
    and request.auth is set to the ClientApiKey instance.
    """

    keyword = 'Bearer'

    def authenticate(self, request):
        key = self._extract_key(request)
        if not key:
            return None

        try:
            api_key = (
                ClientApiKey.objects
                .select_related('business', 'business__user')
                .get(key_hash=ClientApiKey.hash_key(key))
            )
        except ClientApiKey.DoesNotExist:
            raise AuthenticationFailed('Invalid API key')

        if not api_key.is_valid():
            raise AuthenticationFailed('API key is inactive or expired')

        user = api_key.business.user
        if user is None or not user.is_active:
            raise AuthenticationFailed('API key business has no active owner')

        ClientApiKey.objects.filter(pk=api_key.pk).update(last_used=timezone.now())

        return (user, api_key)

    def authenticate_header(self, request):
        return 'Bearer'

    @staticmethod
    def _extract_key(request):
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if auth:
            parts = auth.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                return parts[1].strip() or None
        x_api = request.META.get('HTTP_X_API_KEY', '').strip()
        return x_api or None
