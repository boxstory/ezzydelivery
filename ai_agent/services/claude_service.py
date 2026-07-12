"""
Claude Service

Wrapper for Anthropic Claude API with rate limiting, cost tracking,
and error handling for the AI Operations Agent.
"""

import time
import logging
import os
import requests
from typing import Optional, List, Dict, Any, Generator
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

import anthropic
from anthropic import APIError, RateLimitError, APIConnectionError

from ai_agent.models import UsageLog, Conversation

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of 2024)
PRICING = {
    'claude-sonnet-4-6': {'input': 3.00, 'output': 15.00},
    'claude-sonnet-4-20250514': {'input': 3.00, 'output': 15.00},
    'claude-3-5-sonnet-20241022': {'input': 3.00, 'output': 15.00},
    'claude-3-haiku-20240307': {'input': 0.25, 'output': 1.25},
    'claude-3-opus-20240229': {'input': 15.00, 'output': 75.00},
}


def send_whatsapp_alert(message: str) -> bool:
    """
    Send WhatsApp alert via Evolution API to multiple recipients.
    Used for budget limit notifications.

    Returns:
        bool: True if sent to at least one recipient, False if all failed
    """
    phones_str = getattr(settings, 'AI_AGENT_ALERT_PHONES', '')
    if not phones_str:
        logger.warning("AI_AGENT_ALERT_PHONES not configured for alerts")
        return False

    # Parse comma-separated phone numbers
    phones = [p.strip() for p in phones_str.split(',') if p.strip()]
    if not phones:
        logger.warning("No valid phone numbers in AI_AGENT_ALERT_PHONES")
        return False

    evo_url = getattr(settings, 'EVOLUTION_URL', '') or os.environ.get('EVOLUTION_URL', '')
    evo_key = getattr(settings, 'EVOLUTION_API_KEY', '') or os.environ.get('EVOLUTION_API_KEY', '')
    evo_instance = getattr(settings, 'EVOLUTION_INSTANCE', '') or os.environ.get('EVOLUTION_INSTANCE', '')

    if not evo_url or not evo_key or not evo_instance:
        logger.warning("Evolution API not configured for budget alerts")
        return False

    success_count = 0
    evo_url = evo_url.rstrip('/')

    for phone in phones:
        try:
            payload = {'number': phone, 'text': message}
            response = requests.post(
                f"{evo_url}/message/sendText/{evo_instance}",
                headers={'apikey': evo_key, 'Content-Type': 'application/json'},
                json=payload,
                timeout=10,
            )
            if response.status_code in (200, 201):
                logger.info(f"Budget alert sent successfully to {phone}")
                success_count += 1
            else:
                logger.error(f"Failed to send alert to {phone}: {response.status_code} {response.text[:200]}")
        except requests.RequestException as e:
            logger.error(f"Budget alert request failed for {phone}: {e}")

    return success_count > 0


class RateLimiter:
    """
    Token bucket rate limiter using Django cache.

    Supports both user-level and business-level rate limiting.
    """

    def __init__(self, key_prefix: str, rate_limit: int, window_seconds: int = 60):
        self.key_prefix = key_prefix
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds

    def _get_key(self, identifier: str) -> str:
        return f"ai_rate_limit:{self.key_prefix}:{identifier}"

    def check_and_consume(self, identifier: str, tokens: int = 1) -> tuple[bool, int]:
        """
        Check if request is allowed and consume tokens.

        Returns:
            (is_allowed, remaining_tokens)
        """
        key = self._get_key(identifier)

        # Get current usage
        current = cache.get(key, 0)

        if current + tokens > self.rate_limit:
            return False, max(0, self.rate_limit - current)

        # Increment usage
        new_value = current + tokens
        cache.set(key, new_value, self.window_seconds)

        return True, self.rate_limit - new_value

    def get_remaining(self, identifier: str) -> int:
        """Get remaining tokens for identifier."""
        key = self._get_key(identifier)
        current = cache.get(key, 0)
        return max(0, self.rate_limit - current)


class BudgetTracker:
    """
    Tracks API spending against daily and monthly budgets.
    Sends WhatsApp alerts when limits are exceeded.
    """

    def __init__(self):
        self.daily_budget = getattr(settings, 'AI_AGENT_DAILY_BUDGET', 50.0)
        self.monthly_budget = getattr(settings, 'AI_AGENT_MONTHLY_BUDGET', 1000.0)
        self.whatsapp_enabled = getattr(settings, 'AI_AGENT_WHATSAPP_ENABLED', True)

    def _get_daily_key(self) -> str:
        today = timezone.now().strftime('%Y-%m-%d')
        return f"ai_budget:daily:{today}"

    def _get_monthly_key(self) -> str:
        month = timezone.now().strftime('%Y-%m')
        return f"ai_budget:monthly:{month}"

    def _get_alert_key(self, budget_type: str) -> str:
        """Get cache key for alert tracking."""
        if budget_type == 'daily':
            key = self._get_daily_key()
        else:
            key = self._get_monthly_key()
        return f"{key}:alert_sent"

    def _get_warning_key(self, budget_type: str) -> str:
        """Get cache key for warning tracking (80% threshold)."""
        if budget_type == 'daily':
            key = self._get_daily_key()
        else:
            key = self._get_monthly_key()
        return f"{key}:warning_sent"

    def record_cost(self, cost: float) -> None:
        """Record API cost to daily and monthly totals."""
        # Daily
        daily_key = self._get_daily_key()
        daily_total = cache.get(daily_key, 0.0)
        cache.set(daily_key, daily_total + cost, 86400)  # 24 hours

        # Monthly
        monthly_key = self._get_monthly_key()
        monthly_total = cache.get(monthly_key, 0.0)
        cache.set(monthly_key, monthly_total + cost, 2678400)  # 31 days

    def check_budget(self) -> tuple[bool, str]:
        """
        Check if within budget limits with tiered warnings.

        Behavior:
        - 80% threshold: Send warning, allow calls
        - 100% threshold: Send block alert, reject calls

        Returns:
            (is_within_budget, message)
        """
        daily_key = self._get_daily_key()
        daily_total = cache.get(daily_key, 0.0)

        monthly_key = self._get_monthly_key()
        monthly_total = cache.get(monthly_key, 0.0)

        # ============================================
        # DAILY BUDGET CHECKS
        # ============================================

        # Check if exceeded (100%)
        if daily_total >= self.daily_budget:
            # Send block alert if not already sent today
            if self.whatsapp_enabled:
                alert_key = self._get_alert_key('daily')
                if not cache.get(alert_key, False):
                    message = (
                        f"🚫 *AI Agent - Daily Budget EXCEEDED*\n\n"
                        f"Website: https://ezzydelivery.qa\n\n"
                        f"Daily spending: ${daily_total:.2f}\n"
                        f"Daily limit: ${self.daily_budget:.2f}\n\n"
                        f"⏸️ *API BLOCKED IMMEDIATELY*\n"
                        f"All Claude AI calls blocked now.\n"
                        f"Resumes tomorrow at 12:00 AM UTC."
                    )
                    if send_whatsapp_alert(message):
                        cache.set(alert_key, True, 86400)  # Cache for 24 hours
            return False, f"Daily budget exceeded (${daily_total:.2f}/${self.daily_budget:.2f})"

        # Check warning threshold (80%)
        daily_warning_threshold = self.daily_budget * 0.80
        if daily_total >= daily_warning_threshold:
            # Send warning if not already sent today
            if self.whatsapp_enabled:
                warning_key = self._get_warning_key('daily')
                if not cache.get(warning_key, False):
                    remaining = self.daily_budget - daily_total
                    message = (
                        f"⚠️ *AI Agent - Daily Budget Warning (80%)*\n\n"
                        f"Website: https://ezzydelivery.qa\n\n"
                        f"Daily spending: ${daily_total:.2f}\n"
                        f"Daily limit: ${self.daily_budget:.2f}\n"
                        f"Remaining: ${remaining:.2f}\n\n"
                        f"⚡ *API STILL WORKING*\n"
                        f"Calls allowed until limit reached.\n"
                        f"⚠️ Monitor usage carefully!"
                    )
                    if send_whatsapp_alert(message):
                        cache.set(warning_key, True, 86400)  # Cache for 24 hours

        # ============================================
        # MONTHLY BUDGET CHECKS
        # ============================================

        # Check if exceeded (100%)
        if monthly_total >= self.monthly_budget:
            # Send block alert if not already sent this month
            if self.whatsapp_enabled:
                alert_key = self._get_alert_key('monthly')
                if not cache.get(alert_key, False):
                    message = (
                        f"🚫 *AI Agent - Monthly Budget EXCEEDED*\n\n"
                        f"Website: https://ezzydelivery.qa\n\n"
                        f"Monthly spending: ${monthly_total:.2f}\n"
                        f"Monthly limit: ${self.monthly_budget:.2f}\n\n"
                        f"⏸️ *API BLOCKED IMMEDIATELY*\n"
                        f"All Claude AI calls blocked now.\n"
                        f"Resumes on the 1st of next month."
                    )
                    if send_whatsapp_alert(message):
                        cache.set(alert_key, True, 2678400)  # Cache for 31 days
            return False, f"Monthly budget exceeded (${monthly_total:.2f}/${self.monthly_budget:.2f})"

        # Check warning threshold (80%)
        monthly_warning_threshold = self.monthly_budget * 0.80
        if monthly_total >= monthly_warning_threshold:
            # Send warning if not already sent this month
            if self.whatsapp_enabled:
                warning_key = self._get_warning_key('monthly')
                if not cache.get(warning_key, False):
                    remaining = self.monthly_budget - monthly_total
                    message = (
                        f"⚠️ *AI Agent - Monthly Budget Warning (80%)*\n\n"
                        f"Website: https://ezzydelivery.qa\n\n"
                        f"Monthly spending: ${monthly_total:.2f}\n"
                        f"Monthly limit: ${self.monthly_budget:.2f}\n"
                        f"Remaining: ${remaining:.2f}\n\n"
                        f"⚡ *API STILL WORKING*\n"
                        f"Calls allowed until limit reached.\n"
                        f"⚠️ Monitor usage carefully!"
                    )
                    if send_whatsapp_alert(message):
                        cache.set(warning_key, True, 2678400)  # Cache for 31 days

        return True, "OK"

    def get_usage(self) -> Dict[str, Any]:
        """Get current budget usage."""
        daily_key = self._get_daily_key()
        monthly_key = self._get_monthly_key()

        return {
            'daily_used': cache.get(daily_key, 0.0),
            'daily_budget': self.daily_budget,
            'monthly_used': cache.get(monthly_key, 0.0),
            'monthly_budget': self.monthly_budget,
        }


class ClaudeService:
    """
    Service for interacting with Claude API.

    Features:
    - Rate limiting (per user and per business)
    - Budget tracking
    - Cost calculation
    - Usage logging
    - Retry with exponential backoff
    - Tool use support
    """

    def __init__(self):
        self.api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
        self.model = getattr(settings, 'AI_AGENT_MODEL', 'claude-sonnet-4-6')
        self.max_tokens = getattr(settings, 'AI_AGENT_MAX_TOKENS', 4096)
        self.enabled = getattr(settings, 'AI_AGENT_ENABLED', True)

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not configured")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=self.api_key)

        # Rate limiters
        user_limit = getattr(settings, 'AI_AGENT_RATE_LIMIT_USER', 50)
        business_limit = getattr(settings, 'AI_AGENT_RATE_LIMIT_BUSINESS', 200)

        self.user_limiter = RateLimiter('user', user_limit)
        self.business_limiter = RateLimiter('business', business_limit)

        # Budget tracker
        self.budget_tracker = BudgetTracker()

    def is_available(self) -> tuple[bool, str]:
        """Check if service is available."""
        if not self.enabled:
            return False, "AI Agent is disabled"

        if not self.client:
            return False, "API key not configured"

        within_budget, budget_msg = self.budget_tracker.check_budget()
        if not within_budget:
            return False, budget_msg

        return True, "OK"

    def _calculate_cost(self, tokens_input: int, tokens_output: int) -> Decimal:
        """Calculate cost for token usage."""
        pricing = PRICING.get(self.model, PRICING['claude-sonnet-4-6'])

        input_cost = (tokens_input / 1_000_000) * pricing['input']
        output_cost = (tokens_output / 1_000_000) * pricing['output']

        return Decimal(str(round(input_cost + output_cost, 6)))

    def _check_rate_limits(
        self,
        user_id: Optional[int] = None,
        business_id: Optional[int] = None
    ) -> tuple[bool, str]:
        """Check rate limits for user and/or business."""
        if user_id:
            allowed, remaining = self.user_limiter.check_and_consume(str(user_id))
            if not allowed:
                return False, f"User rate limit exceeded. Try again in 1 minute."

        if business_id:
            allowed, remaining = self.business_limiter.check_and_consume(str(business_id))
            if not allowed:
                return False, f"Business rate limit exceeded. Try again in 1 minute."

        return True, "OK"

    def _log_usage(
        self,
        conversation: Optional[Conversation],
        api_call_type: str,
        tokens_input: int,
        tokens_output: int,
        latency_ms: int,
        success: bool,
        error_message: str = '',
        user_id: Optional[int] = None,
        business_id: Optional[int] = None
    ) -> UsageLog:
        """Log API usage to database."""
        cost = self._calculate_cost(tokens_input, tokens_output)

        # Record cost for budget tracking
        self.budget_tracker.record_cost(float(cost))

        log = UsageLog.objects.create(
            conversation=conversation,
            user_id=user_id,
            business_id=business_id,
            api_call_type=api_call_type,
            model=self.model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            estimated_cost=cost,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message
        )

        return log

    def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        conversation: Optional[Conversation] = None,
        user_id: Optional[int] = None,
        business_id: Optional[int] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Send a chat completion request to Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system: System prompt
            tools: List of tool definitions for function calling
            conversation: Associated conversation for logging
            user_id: User ID for rate limiting
            business_id: Business ID for rate limiting
            max_retries: Number of retries on transient errors

        Returns:
            Dict with 'content', 'tool_calls', 'tokens_input', 'tokens_output', 'stop_reason'
        """
        # Check availability
        available, msg = self.is_available()
        if not available:
            return {
                'error': True,
                'message': msg,
                'content': None,
                'tool_calls': [],
            }

        # Check rate limits
        allowed, rate_msg = self._check_rate_limits(user_id, business_id)
        if not allowed:
            return {
                'error': True,
                'message': rate_msg,
                'content': None,
                'tool_calls': [],
            }

        # Prepare request
        request_params = {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'messages': messages,
        }

        if system:
            request_params['system'] = system

        if tools:
            request_params['tools'] = tools

        # Execute with retries
        start_time = time.time()
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(**request_params)

                # Calculate latency
                latency_ms = int((time.time() - start_time) * 1000)

                # Extract response data
                tokens_input = response.usage.input_tokens
                tokens_output = response.usage.output_tokens

                # Parse response content
                content = None
                tool_calls = []

                for block in response.content:
                    if block.type == 'text':
                        content = block.text
                    elif block.type == 'tool_use':
                        tool_calls.append({
                            'id': block.id,
                            'name': block.name,
                            'input': block.input,
                        })

                # Log successful usage
                self._log_usage(
                    conversation=conversation,
                    api_call_type='tool_use' if tool_calls else 'chat',
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    latency_ms=latency_ms,
                    success=True,
                    user_id=user_id,
                    business_id=business_id
                )

                # Update conversation tokens if provided
                if conversation:
                    conversation.total_tokens_input += tokens_input
                    conversation.total_tokens_output += tokens_output
                    conversation.total_messages += 1
                    conversation.save(update_fields=[
                        'total_tokens_input',
                        'total_tokens_output',
                        'total_messages',
                        'last_activity'
                    ])

                return {
                    'error': False,
                    'content': content,
                    'tool_calls': tool_calls,
                    'tokens_input': tokens_input,
                    'tokens_output': tokens_output,
                    'stop_reason': response.stop_reason,
                }

            except RateLimitError as e:
                last_error = e
                logger.warning(f"Rate limit hit, attempt {attempt + 1}/{max_retries}")
                time.sleep(2 ** attempt)  # Exponential backoff

            except APIConnectionError as e:
                last_error = e
                logger.error(f"API connection error: {e}")
                time.sleep(1)

            except APIError as e:
                last_error = e
                logger.error(f"API error: {e}")
                break  # Don't retry on non-transient errors

        # Log failed request
        latency_ms = int((time.time() - start_time) * 1000)
        self._log_usage(
            conversation=conversation,
            api_call_type='chat',
            tokens_input=0,
            tokens_output=0,
            latency_ms=latency_ms,
            success=False,
            error_message=str(last_error),
            user_id=user_id,
            business_id=business_id
        )

        return {
            'error': True,
            'message': str(last_error),
            'content': None,
            'tool_calls': [],
        }

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        conversation: Optional[Conversation] = None,
        user_id: Optional[int] = None,
        business_id: Optional[int] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Send a streaming chat completion request to Claude.

        Yields chunks of the response as they arrive.
        """
        # Check availability
        available, msg = self.is_available()
        if not available:
            yield {'error': True, 'message': msg, 'type': 'error'}
            return

        # Check rate limits
        allowed, rate_msg = self._check_rate_limits(user_id, business_id)
        if not allowed:
            yield {'error': True, 'message': rate_msg, 'type': 'error'}
            return

        # Prepare request
        request_params = {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'messages': messages,
        }

        if system:
            request_params['system'] = system

        if tools:
            request_params['tools'] = tools

        start_time = time.time()
        tokens_input = 0
        tokens_output = 0
        full_content = ''
        tool_calls = []
        current_tool = None
        usage_logged = False

        try:
            with self.client.messages.stream(**request_params) as stream:
                for event in stream:
                    if event.type == 'message_start':
                        tokens_input = event.message.usage.input_tokens
                        yield {'type': 'start', 'tokens_input': tokens_input}

                    elif event.type == 'content_block_start':
                        if event.content_block.type == 'tool_use':
                            current_tool = {
                                'id': event.content_block.id,
                                'name': event.content_block.name,
                                'input': '',
                            }
                            yield {'type': 'tool_start', 'tool_name': current_tool['name']}

                    elif event.type == 'content_block_delta':
                        if hasattr(event.delta, 'text'):
                            full_content += event.delta.text
                            yield {'type': 'text', 'text': event.delta.text}
                        elif hasattr(event.delta, 'partial_json'):
                            if current_tool:
                                current_tool['input'] += event.delta.partial_json

                    elif event.type == 'content_block_stop':
                        if current_tool:
                            try:
                                import json
                                parsed = json.loads(current_tool['input'])
                                current_tool['input'] = parsed if isinstance(parsed, dict) else {}
                            except (json.JSONDecodeError, TypeError):
                                current_tool['input'] = {}
                            tool_calls.append(current_tool)
                            yield {'type': 'tool_end', 'tool': current_tool}
                            current_tool = None

                    elif event.type == 'message_delta':
                        tokens_output = event.usage.output_tokens

                    elif event.type == 'message_stop':
                        yield {'type': 'stop', 'tokens_output': tokens_output}

            # Log usage once — flag prevents a second log if post-stream work fails
            latency_ms = int((time.time() - start_time) * 1000)
            self._log_usage(
                conversation=conversation,
                api_call_type='tool_use' if tool_calls else 'chat',
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                latency_ms=latency_ms,
                success=True,
                user_id=user_id,
                business_id=business_id
            )
            usage_logged = True

            # Update conversation
            if conversation:
                conversation.total_tokens_input += tokens_input
                conversation.total_tokens_output += tokens_output
                conversation.total_messages += 1
                conversation.save(update_fields=[
                    'total_tokens_input',
                    'total_tokens_output',
                    'total_messages',
                    'last_activity'
                ])

            yield {
                'type': 'complete',
                'content': full_content,
                'tool_calls': tool_calls,
                'tokens_input': tokens_input,
                'tokens_output': tokens_output,
            }

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            if not usage_logged:
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_usage(
                    conversation=conversation,
                    api_call_type='chat',
                    tokens_input=0,
                    tokens_output=0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=str(e),
                    user_id=user_id,
                    business_id=business_id
                )
            yield {'type': 'error', 'error': True, 'message': str(e)}


# Singleton instance
_claude_service = None


def get_claude_service() -> ClaudeService:
    """Get the singleton ClaudeService instance."""
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service
