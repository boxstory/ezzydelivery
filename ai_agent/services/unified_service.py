"""
Purpose: Unified AI provider factory — routes chat to Anthropic, OpenAI, xAI, or Gemini.
Used by: AgentService, WhatsApp reply handler
Notes: OpenAI/xAI use the same REST format; Gemini uses Google's generateContent API.
       All return the same dict shape as ClaudeService.chat().
"""
import re
import time
import json
import logging
import requests
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.conf import settings

logger = logging.getLogger(__name__)


class OpenAICompatService:
    """Chat service for OpenAI-compatible APIs (OpenAI, xAI/Grok). No SDK required."""

    ENDPOINTS = {
        'openai': 'https://api.openai.com/v1/chat/completions',
        'xai':    'https://api.x.ai/v1/chat/completions',
        'groq':   'https://api.groq.com/openai/v1/chat/completions',
    }
    KEY_SETTINGS = {
        'openai': ('OPENAI_API_KEY',  'gpt-4o'),
        'xai':    ('XAI_API_KEY',     'grok-3'),
        'groq':   ('GROQ_API_KEY',    'llama-3.3-70b-versatile'),
    }

    def __init__(self, provider: str, model: str = ''):
        self.provider   = provider
        self.max_tokens = getattr(settings, 'AI_AGENT_MAX_TOKENS', 4096)
        self.endpoint   = self.ENDPOINTS[provider]
        key_setting, default_model = self.KEY_SETTINGS[provider]
        self.api_key = getattr(settings, key_setting, '') or ''
        self.model   = model or getattr(settings, 'AI_CHAT_MODEL', default_model)

    # Keywords that map to tool names — used to pick the smallest relevant tool set
    # so a single request stays well under tight provider TPM limits.
    _TOOL_KEYWORDS: Dict[str, List[str]] = {
        'get_business_dashboard':  ['order', 'orders', 'total', 'summary', 'revenue', 'stats',
                                     'report', 'month', 'week', 'today', 'how many', 'count',
                                     'delivered', 'cancelled', 'pending', 'hi', 'hello', 'help'],
        'search_orders':           ['find', 'search', 'track', 'specific', 'reference', 'ref',
                                     'lookup', 'show order', 'get order'],
        'lookup_order':            ['order #', 'order id', 'order number', 'ezzy-', 'ezzy '],
        'get_business_deliveries': ['delivery', 'deliveries', 'in transit', 'assigned', 'on way',
                                     'out for'],
        'get_business_cod_summary':['cod', 'cash on delivery', 'payment', 'collect', 'collection',
                                     'unpaid', 'remit', 'cash'],
        'get_business_customers':  ['customer', 'customers', 'client', 'buyer', 'repeat'],
        'get_driver_status':       ['driver', 'drivers', 'fleet', 'vehicle', 'captain', 'rider'],
        'parse_address':           ['address', 'location', 'zone for', 'map'],
        'lookup_zone':             ['zone', 'area', 'region', 'which zone', 'coverage'],
        'list_import_sources':     ['import', 'source', 'shopify', 'woocommerce', 'integration',
                                     'connect', 'sync'],
        'get_import_history':      ['import history', 'past import', 'imported', 'last import'],
        'get_temp_orders':         ['temp order', 'draft', 'temporary', 'pending import'],
        'import_from_onedrive':    ['onedrive', 'excel', 'spreadsheet', 'one drive'],
        'import_from_api':         ['api sync', 'api import', 'auto import'],
        'parse_text_to_orders':    ['paste', 'text order', 'bulk', 'convert text'],
        'get_business_products':   ['product', 'products', 'catalog', 'catalogue', 'item',
                                     'items', 'sku', 'inventory', 'stock', 'low stock',
                                     'out of stock', 'price list', 'my page', 'store', 'shop'],
    }
    # Fallback tools sent when no keywords match (covers the most common queries)
    _DEFAULT_TOOLS = ['get_business_dashboard', 'search_orders', 'get_business_deliveries']
    # Max tools to send per request — keeps token usage ~2-3K on tight-limit providers
    _MAX_TOOLS = 4

    def _select_tools(self, message: str, tools: Optional[list]) -> Optional[list]:
        """Return a subset of tools relevant to the message, capped at _MAX_TOOLS.

        Returns None (no tools) for greetings/small-talk so we don't waste tokens
        sending schemas when the model just needs to respond in text.
        """
        if not tools:
            return None
        msg = message.lower()
        scores: Dict[str, int] = {}
        for tool in tools:
            name = tool['name']
            kws  = self._TOOL_KEYWORDS.get(name, [])
            scores[name] = sum(1 for kw in kws if kw in msg)

        top = [t for t in sorted(tools, key=lambda t: scores.get(t['name'], 0), reverse=True)
               if scores.get(t['name'], 0) > 0][:self._MAX_TOOLS]

        # If no keywords matched, don't send any tools (saves ~3K tokens for greetings)
        return top if top else None

    def _post(self, payload: dict) -> requests.Response:
        """POST payload to the provider endpoint."""
        return requests.post(
            self.endpoint,
            json=payload,
            headers={'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'},
            timeout=60,
        )

    def _parse_retry_seconds(self, err_body: dict) -> Optional[float]:
        """Extract retry-after seconds from a provider 429 error message, or None."""
        msg = (err_body.get('error') or {}).get('message', '')
        m = re.search(r'try again in (\d+(?:\.\d+)?)s', msg)
        return float(m.group(1)) if m else None

    def is_available(self) -> tuple[bool, str]:
        if not getattr(settings, 'AI_AGENT_ENABLED', False):
            return False, "AI Agent is disabled"
        if not self.api_key:
            return False, f"{self.provider} API key not configured"
        return True, "OK"

    # ------------------------------------------------------------------
    # Format converters: Anthropic ↔ OpenAI
    # agent_service.py always speaks Anthropic format; we translate here.
    # ------------------------------------------------------------------

    def _to_oai_messages(self, messages: list, system: Optional[str]) -> list:
        """Convert Anthropic-format message list to OpenAI format."""
        oai = []
        if system:
            oai.append({'role': 'system', 'content': system})

        for m in messages:
            role    = m['role']
            content = m.get('content', '')

            if isinstance(content, list):
                tool_uses    = [b for b in content if b.get('type') == 'tool_use']
                tool_results = [b for b in content if b.get('type') == 'tool_result']
                text         = ' '.join(b.get('text', '') for b in content if b.get('type') == 'text')

                if role == 'assistant' and tool_uses:
                    # Assistant made tool calls
                    oai_tool_calls = [
                        {
                            'id':   tu['id'],
                            'type': 'function',
                            'function': {
                                'name':      tu['name'],
                                'arguments': json.dumps(tu.get('input', {})),
                            },
                        }
                        for tu in tool_uses
                    ]
                    oai.append({
                        'role':       'assistant',
                        'content':    text or None,
                        'tool_calls': oai_tool_calls,
                    })
                    continue

                if role == 'user' and tool_results:
                    # Tool results (one message per result in OpenAI format)
                    for tr in tool_results:
                        result_content = tr.get('content', '')
                        if isinstance(result_content, list):
                            result_content = ' '.join(
                                b.get('text', '') for b in result_content if b.get('type') == 'text'
                            )
                        oai.append({
                            'role':         'tool',
                            'tool_call_id': tr.get('tool_use_id', ''),
                            'content':      result_content or '',
                        })
                    continue

                content = text or '(empty)'

            oai.append({'role': role, 'content': content or ''})

        return oai

    def _to_oai_tools(self, tools: Optional[list]) -> Optional[list]:
        """Convert Anthropic tool schemas to OpenAI function format."""
        if not tools:
            return None
        return [
            {
                'type': 'function',
                'function': {
                    'name':        t['name'],
                    'description': t.get('description', ''),
                    'parameters':  t.get('input_schema', {'type': 'object', 'properties': {}}),
                },
            }
            for t in tools
        ]

    def _parse_tool_calls(self, oai_tool_calls: list) -> list:
        """Convert OpenAI tool_calls → Anthropic-style list for agent_service."""
        result = []
        for tc in oai_tool_calls or []:
            try:
                input_data = json.loads(tc['function']['arguments'])
            except Exception:
                input_data = {}
            result.append({
                'id':    tc['id'],
                'name':  tc['function']['name'],
                'input': input_data,
            })
        return result

    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools=None,
        conversation=None,
        user_id: Optional[int] = None,
        business_id: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        available, msg = self.is_available()
        if not available:
            return {'error': True, 'message': msg, 'content': None, 'tool_calls': []}

        # If the most recent user message is a tool_result, this is a follow-up round.
        # The model already has the data — don't send tool schemas, just let it summarize.
        last_content = messages[-1].get('content', '') if messages else ''
        is_tool_followup = isinstance(last_content, list) and any(
            b.get('type') == 'tool_result' for b in last_content
        )

        if is_tool_followup:
            selected_tools = None
            # Append a clear instruction so the model summarises rather than calls more tools
            if system:
                system = system + "\n\nIMPORTANT: You have already received the tool results above. Summarise the data in a clear, concise answer. Do NOT call any more tools or emit function syntax."
        else:
            # Extract original user query for keyword-based tool routing
            last_user_msg = ''
            for m in reversed(messages):
                if m['role'] == 'user':
                    c = m.get('content', '')
                    if isinstance(c, str):
                        last_user_msg = c
                        break
                    text = ' '.join(b.get('text', '') for b in c if b.get('type') == 'text')
                    if text:
                        last_user_msg = text
                        break
            selected_tools = self._select_tools(last_user_msg, tools)
        oai_messages   = self._to_oai_messages(messages, system)
        oai_tools      = self._to_oai_tools(selected_tools)

        payload: Dict[str, Any] = {
            'model':      self.model,
            'max_tokens': self.max_tokens,
            'messages':   oai_messages,
        }
        if oai_tools:
            payload['tools'] = oai_tools

        try:
            start = time.time()
            resp = self._post(payload)
            latency_ms = int((time.time() - start) * 1000)

            if resp.status_code != 200:
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = {'error': {'message': resp.text, 'code': ''}}
                err_code = (err_body.get('error') or {}).get('code', '')
                err_msg  = f"API error {resp.status_code}: {err_body}"
                logger.error("[%s] %s", self.provider, err_msg)

                # 429 rate limit — retry once after the provider's suggested wait
                if resp.status_code == 429:
                    wait = self._parse_retry_seconds(err_body)
                    if wait and wait <= 30:
                        logger.warning("[%s] Rate limited — waiting %.1fs then retrying", self.provider, wait)
                        time.sleep(wait + 0.5)
                        resp = self._post(payload)
                        if resp.status_code == 200:
                            data       = resp.json()
                            choice     = data['choices'][0]
                            message_   = choice['message']
                            content    = message_.get('content') or ''
                            usage      = data.get('usage', {})
                            tokens_in  = usage.get('prompt_tokens', 0)
                            tokens_out = usage.get('completion_tokens', 0)
                            self._log_usage(conversation, tokens_in, tokens_out,
                                            int((time.time()-start)*1000), True, user_id, business_id)
                            return {
                                'content':       content,
                                'tool_calls':    self._parse_tool_calls(message_.get('tool_calls') or []),
                                'tokens_input':  tokens_in,
                                'tokens_output': tokens_out,
                                'stop_reason':   choice.get('finish_reason', 'stop'),
                                'error':         False,
                            }
                        # retry also failed — fall through to error return below
                        try:
                            err_body = resp.json()
                        except Exception:
                            err_body = {'error': {'message': resp.text, 'code': ''}}
                        err_msg = f"API error {resp.status_code}: {err_body}"

                # tool_use_failed: the model mangled the function-call format.
                # Retry immediately without tools so the model answers in plain text.
                if err_code == 'tool_use_failed' and oai_tools:
                    logger.warning("[%s] tool_use_failed — retrying without tools", self.provider)
                    fallback_payload = {k: v for k, v in payload.items() if k != 'tools'}
                    if system and 'Do NOT call' not in (oai_messages[0].get('content', '') if oai_messages else ''):
                        # Tell the model not to use tools in the retry
                        fm = list(oai_messages)
                        if fm and fm[0].get('role') == 'system':
                            fm[0] = dict(fm[0])
                            fm[0]['content'] += '\n\nAnswer the question directly without calling any tools.'
                        fallback_payload['messages'] = fm
                    r2 = requests.post(
                        self.endpoint, json=fallback_payload,
                        headers={'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'},
                        timeout=60,
                    )
                    if r2.status_code == 200:
                        d2      = r2.json()
                        c2      = d2['choices'][0]
                        u2      = d2.get('usage', {})
                        self._log_usage(conversation, u2.get('prompt_tokens', 0),
                                        u2.get('completion_tokens', 0), latency_ms, True, user_id, business_id)
                        return {
                            'content':      c2['message'].get('content') or '',
                            'tool_calls':   [],
                            'tokens_input': u2.get('prompt_tokens', 0),
                            'tokens_output':u2.get('completion_tokens', 0),
                            'stop_reason':  c2.get('finish_reason', 'stop'),
                            'error':        False,
                        }

                self._log_usage(conversation, 0, 0, latency_ms, False, user_id, business_id, err_msg)
                return {'error': True, 'message': err_msg, 'content': None, 'tool_calls': []}

            data       = resp.json()
            choice     = data['choices'][0]
            message    = choice['message']
            content    = message.get('content') or ''
            usage      = data.get('usage', {})
            tokens_in  = usage.get('prompt_tokens', 0)
            tokens_out = usage.get('completion_tokens', 0)
            tool_calls = self._parse_tool_calls(message.get('tool_calls') or [])

            self._log_usage(conversation, tokens_in, tokens_out, latency_ms, True, user_id, business_id)

            return {
                'content':       content,
                'tool_calls':    tool_calls,
                'tokens_input':  tokens_in,
                'tokens_output': tokens_out,
                'stop_reason':   choice.get('finish_reason', 'stop'),
                'error':         False,
            }

        except Exception as e:
            logger.exception("[%s] chat error", self.provider)
            return {'error': True, 'message': str(e), 'content': None, 'tool_calls': []}

    def chat_stream(self, messages, system=None, tools=None, conversation=None,
                    user_id=None, business_id=None, **kwargs):
        """Streaming-compatible wrapper: calls chat() and yields chunks in agent_service format."""
        result = self.chat(messages=messages, system=system, tools=tools,
                           conversation=conversation, user_id=user_id, business_id=business_id)
        if result.get('error'):
            yield {'type': 'error', 'message': result.get('message', 'API error')}
            return
        content    = result.get('content') or ''
        tool_calls = result.get('tool_calls') or []
        if content:
            yield {'type': 'text', 'text': content}
        for tc in tool_calls:
            yield {'type': 'tool_start', 'tool_name': tc['name']}
            yield {'type': 'tool_end', 'tool': tc}

    def _log_usage(self, conversation, tokens_in, tokens_out, latency_ms, success,
                   user_id=None, business_id=None, error_message=''):
        try:
            from ai_agent.models import UsageLog
            UsageLog.objects.create(
                conversation=conversation,
                user_id=user_id,
                business_id=business_id,
                api_call_type='chat',
                model=self.model,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                estimated_cost=Decimal('0'),
                latency_ms=latency_ms,
                success=success,
                error_message=error_message,
            )
        except Exception:
            pass


class GeminiService:
    """Chat service for Google Gemini via REST API."""

    def __init__(self, model: str = ''):
        self.api_key    = getattr(settings, 'GOOGLE_AI_API_KEY', '') or ''
        self.model      = model or getattr(settings, 'AI_CHAT_MODEL', 'gemini-2.0-flash')
        self.max_tokens = getattr(settings, 'AI_AGENT_MAX_TOKENS', 4096)

    def is_available(self) -> tuple[bool, str]:
        if not getattr(settings, 'AI_AGENT_ENABLED', False):
            return False, "AI Agent is disabled"
        if not self.api_key:
            return False, "Google AI API key not configured"
        return True, "OK"

    def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools=None,
        conversation=None,
        user_id: Optional[int] = None,
        business_id: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        available, msg = self.is_available()
        if not available:
            return {'error': True, 'message': msg, 'content': None, 'tool_calls': []}

        gemini_contents = []
        for m in messages:
            role = 'user' if m['role'] == 'user' else 'model'
            content = m.get('content', '')
            if isinstance(content, list):
                text = ' '.join(b.get('text', '') for b in content if b.get('type') == 'text') or '(no text)'
            else:
                text = content or ''
            gemini_contents.append({'role': role, 'parts': [{'text': text}]})

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            'contents': gemini_contents,
            'generationConfig': {'maxOutputTokens': self.max_tokens},
        }
        if system:
            payload['systemInstruction'] = {'parts': [{'text': system}]}

        try:
            start = time.time()
            resp = requests.post(url, json=payload, timeout=60)
            latency_ms = int((time.time() - start) * 1000)

            if resp.status_code != 200:
                msg = f"Gemini API error {resp.status_code}: {resp.text}"
                logger.error("[gemini] %s", msg)
                return {'error': True, 'message': msg, 'content': None, 'tool_calls': []}

            data = resp.json()
            content = data['candidates'][0]['content']['parts'][0].get('text', '')
            meta = data.get('usageMetadata', {})
            tokens_in  = meta.get('promptTokenCount', 0)
            tokens_out = meta.get('candidatesTokenCount', 0)

            return {
                'content': content,
                'tool_calls': [],
                'tokens_input': tokens_in,
                'tokens_output': tokens_out,
                'stop_reason': 'stop',
                'error': False,
            }

        except Exception as e:
            logger.exception("[gemini] chat error")
            return {'error': True, 'message': str(e), 'content': None, 'tool_calls': []}

    def chat_stream(self, messages, system=None, tools=None, conversation=None,
                    user_id=None, business_id=None, **kwargs):
        """Streaming-compatible wrapper for Gemini."""
        result = self.chat(messages=messages, system=system, tools=tools,
                           conversation=conversation, user_id=user_id, business_id=business_id)
        if result.get('error'):
            yield {'type': 'error', 'message': result.get('message', 'API error')}
            return
        content = result.get('content') or ''
        if content:
            yield {'type': 'text', 'text': content}


def get_chat_service(purpose: str = 'chat'):
    """
    Factory: returns the AI service for the given purpose.
      purpose='chat' → AI_CHAT_PROVIDER / AI_CHAT_MODEL  (business dashboard)
      purpose='wa'   → AI_WA_PROVIDER  / AI_WA_MODEL     (WhatsApp reply)
    Falls back to Claude if provider is unknown or key is missing.
    """
    from ai_agent.services.claude_service import get_claude_service

    if purpose == 'wa':
        provider = getattr(settings, 'AI_WA_PROVIDER', 'anthropic') or 'anthropic'
        model    = getattr(settings, 'AI_WA_MODEL', '') or ''
    else:
        provider = getattr(settings, 'AI_CHAT_PROVIDER', 'anthropic') or 'anthropic'
        model    = getattr(settings, 'AI_CHAT_MODEL', '') or ''

    if provider == 'anthropic':
        return get_claude_service()
    elif provider in ('openai', 'xai', 'groq'):
        return OpenAICompatService(provider, model)
    elif provider == 'gemini':
        return GeminiService(model)
    else:
        logger.warning("Unknown AI_CHAT_PROVIDER=%s, falling back to Anthropic", provider)
        return get_claude_service()
