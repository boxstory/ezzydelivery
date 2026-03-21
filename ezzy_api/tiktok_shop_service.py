"""
TikTok Shop API Integration Service
====================================

This module provides integration with TikTok Shop API for order management.

TikTok Shop API Documentation:
    - Get Order List: https://partner.tiktokshop.com/docv2/page/get-order-list-202309
    - API Version: 202309 and later

Authentication:
    - Uses OAuth2 with App Key and App Secret
    - Access tokens expire and need refresh via refresh_token
    - API requests require: app_key, access_token, shop_cipher, timestamp, sign

Usage:
    service = TikTokShopService(api_settings)
    orders = service.get_orders(status='AWAITING_SHIPMENT')
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


class TikTokShopService:
    """
    TikTok Shop API client service.

    Handles authentication, request signing, and order operations
    for TikTok Shop integration.

    Attributes:
        api_settings: BusinessApiSettings instance with TikTok credentials
        base_url: TikTok Shop API base URL
        api_version: API version (default: 202309)
    """

    # TikTok Shop API base URLs by region
    BASE_URLS = {
        'global': 'https://open-api.tiktokglobalshop.com',
        'us': 'https://open-api.tiktokglobalshop.com',
        'uk': 'https://open-api.tiktokglobalshop.com',
    }

    # Order status mapping
    ORDER_STATUS = {
        'UNPAID': 'Unpaid',
        'AWAITING_SHIPMENT': 'Awaiting Shipment',
        'AWAITING_COLLECTION': 'Awaiting Collection',
        'IN_TRANSIT': 'In Transit',
        'DELIVERED': 'Delivered',
        'COMPLETED': 'Completed',
        'CANCELLED': 'Cancelled',
    }

    def __init__(self, api_settings):
        """
        Initialize TikTok Shop service.

        Args:
            api_settings: BusinessApiSettings instance with:
                - api_key: TikTok App Key
                - api_secret: TikTok App Secret
                - api_access_token: OAuth access token
                - tiktok_shop_id: Shop ID
                - tiktok_shop_cipher: Shop cipher
                - tiktok_refresh_token: Refresh token
                - api_version: API version (optional, default: 202309)
        """
        self.api_settings = api_settings
        self.app_key = api_settings.api_key
        self.app_secret = api_settings.api_secret
        self.access_token = api_settings.api_access_token
        self.shop_id = api_settings.tiktok_shop_id
        self.shop_cipher = api_settings.tiktok_shop_cipher
        self.refresh_token = api_settings.tiktok_refresh_token
        self.api_version = api_settings.api_version or '202309'
        self.base_url = self.BASE_URLS.get('global')

    def _generate_sign(self, path: str, params: dict, body: str = '') -> str:
        """
        Generate HMAC-SHA256 signature for TikTok Shop API request.

        The signature is calculated as:
        sign = HMAC-SHA256(app_secret, path + sorted_params + body)

        Args:
            path: API endpoint path (e.g., /order/202309/orders/search)
            params: Query parameters (excluding sign)
            body: Request body as JSON string

        Returns:
            Hexadecimal signature string
        """
        # Sort parameters alphabetically
        sorted_params = ''.join(f'{k}{v}' for k, v in sorted(params.items()))

        # Build string to sign: path + params + body
        string_to_sign = f'{path}{sorted_params}{body}'

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.app_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _make_request(self, method: str, path: str, params: dict = None,
                      body: dict = None) -> dict:
        """
        Make authenticated request to TikTok Shop API.

        Args:
            method: HTTP method (GET, POST)
            path: API endpoint path
            params: Query parameters
            body: Request body dict

        Returns:
            API response as dict

        Raises:
            TikTokShopAPIError: If API returns error
        """
        if params is None:
            params = {}

        # Add required parameters
        timestamp = str(int(time.time()))
        params.update({
            'app_key': self.app_key,
            'timestamp': timestamp,
            'shop_cipher': self.shop_cipher,
        })

        # Prepare body
        body_str = json.dumps(body) if body else ''

        # Generate signature
        sign = self._generate_sign(path, params, body_str)
        params['sign'] = sign

        # Build URL
        url = f'{self.base_url}{path}'

        # Set headers
        headers = {
            'Content-Type': 'application/json',
            'x-tts-access-token': self.access_token,
        }

        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=30)
            else:
                response = requests.post(url, params=params, json=body, headers=headers, timeout=30)

            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if data.get('code') != 0:
                error_msg = data.get('message', 'Unknown TikTok Shop API error')
                logger.error(f'TikTok Shop API error: {error_msg}')
                raise TikTokShopAPIError(data.get('code'), error_msg)

            return data.get('data', {})

        except requests.exceptions.RequestException as e:
            logger.error(f'TikTok Shop API request failed: {str(e)}')
            raise TikTokShopAPIError(-1, f'Request failed: {str(e)}')

    def refresh_access_token(self) -> bool:
        """
        Refresh the access token using refresh token.

        Updates api_settings with new tokens if successful.

        Returns:
            True if token refreshed successfully, False otherwise
        """
        if not self.refresh_token:
            logger.error('No refresh token available')
            return False

        url = f'{self.base_url}/api/v2/token/refresh'
        params = {
            'app_key': self.app_key,
            'app_secret': self.app_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token',
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('code') == 0:
                token_data = data.get('data', {})
                self.access_token = token_data.get('access_token')
                self.refresh_token = token_data.get('refresh_token')

                # Update api_settings
                self.api_settings.api_access_token = self.access_token
                self.api_settings.tiktok_refresh_token = self.refresh_token
                self.api_settings.tiktok_token_expires_at = timezone.now() + timedelta(
                    seconds=token_data.get('access_token_expire_in', 86400)
                )
                self.api_settings.save()

                logger.info('TikTok Shop access token refreshed successfully')
                return True
            else:
                logger.error(f'Token refresh failed: {data.get("message")}')
                return False

        except Exception as e:
            logger.error(f'Token refresh error: {str(e)}')
            return False

    def get_orders(self, order_status: str = None, create_time_from: int = None,
                   create_time_to: int = None, page_size: int = 20,
                   page_token: str = None) -> dict:
        """
        Get order list from TikTok Shop.

        API Endpoint: POST /order/202309/orders/search

        Args:
            order_status: Filter by order status (e.g., AWAITING_SHIPMENT)
            create_time_from: Start time (Unix timestamp)
            create_time_to: End time (Unix timestamp)
            page_size: Number of orders per page (max 100)
            page_token: Pagination token for next page

        Returns:
            dict with 'orders' list and 'next_page_token'
        """
        path = f'/order/{self.api_version}/orders/search'

        body = {
            'page_size': min(page_size, 100),
        }

        if order_status:
            body['order_status'] = order_status

        if create_time_from:
            body['create_time_ge'] = create_time_from

        if create_time_to:
            body['create_time_lt'] = create_time_to

        if page_token:
            body['page_token'] = page_token

        return self._make_request('POST', path, body=body)

    def get_order_detail(self, order_id: str) -> dict:
        """
        Get detailed information for a specific order.

        API Endpoint: POST /order/202309/orders

        Args:
            order_id: TikTok Shop order ID

        Returns:
            Order detail dict
        """
        path = f'/order/{self.api_version}/orders'

        body = {
            'order_ids': [order_id],
        }

        result = self._make_request('POST', path, body=body)
        orders = result.get('orders', [])
        return orders[0] if orders else None

    def test_connection(self) -> dict:
        """
        Test API connection by fetching shop info.

        Returns:
            dict with 'success' boolean and 'message' or 'shop_info'
        """
        try:
            # Try to get a single order to test connection
            result = self.get_orders(page_size=1)
            return {
                'success': True,
                'message': 'TikTok Shop API connection successful',
                'total_orders': result.get('total_count', 0),
            }
        except TikTokShopAPIError as e:
            return {
                'success': False,
                'message': f'API Error: {e.message}',
                'error_code': e.code,
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Connection failed: {str(e)}',
            }


class TikTokShopAPIError(Exception):
    """Exception for TikTok Shop API errors."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f'TikTok Shop API Error {code}: {message}')


def create_order_from_tiktok(tiktok_order: dict, business) -> 'Order':
    """
    Create an EzzyDelivery order from TikTok Shop order data.

    Args:
        tiktok_order: Order data from TikTok Shop API
        business: Business instance

    Returns:
        Created Order instance
    """
    from orders.models import Order, OrderItem

    # Extract recipient info
    recipient = tiktok_order.get('recipient_address', {})

    # Check for existing order
    tiktok_order_id = tiktok_order.get('order_id')
    existing = Order.objects.filter(
        business=business,
        client_order_code=f'TTS-{tiktok_order_id}'
    ).first()

    if existing:
        logger.info(f'Order TTS-{tiktok_order_id} already exists')
        return existing

    # Map TikTok status to EzzyDelivery status
    status_map = {
        'UNPAID': 'to_review',
        'AWAITING_SHIPMENT': 'ready_to_pickup',
        'AWAITING_COLLECTION': 'ready_to_pickup',
        'IN_TRANSIT': 'out_for_delivery',
        'DELIVERED': 'delivered',
        'COMPLETED': 'delivered',
        'CANCELLED': 'cancelled',
    }

    tiktok_status = tiktok_order.get('order_status', 'UNPAID')

    # Calculate COD amount
    payment_info = tiktok_order.get('payment_info', {})
    is_cod = payment_info.get('payment_method') == 'COD'
    total_amount = float(payment_info.get('total_amount', 0))

    # Create order
    order = Order.objects.create(
        business=business,
        client_order_code=f'TTS-{tiktok_order_id}',
        customer_name=recipient.get('name', 'TikTok Customer'),
        customer_phone=recipient.get('phone', ''),
        customer_address=recipient.get('full_address', ''),
        dl_zone=recipient.get('district', '0'),
        order_status=status_map.get(tiktok_status, 'to_review'),
        cod_status_by_client='unpaid' if is_cod else 'online_paid',
        cod_amount=total_amount if is_cod else 0,
        order_notes=f'TikTok Shop Order #{tiktok_order_id}',
    )

    # Create order items
    for item in tiktok_order.get('line_items', []):
        OrderItem.objects.create(
            order=order,
            product=None,  # TikTok products not linked to local products
            quantity=int(item.get('quantity', 1)),
            unit_price=float(item.get('sale_price', 0)),
            notes=item.get('product_name', 'TikTok Product'),
        )

    logger.info(f'Created order {order.id} from TikTok Shop order {tiktok_order_id}')
    return order
