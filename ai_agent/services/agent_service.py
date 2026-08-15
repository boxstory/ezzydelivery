"""
Agent Service

Main orchestration service for the AI Operations Agent.
Manages conversations, tool execution, and message flow.
"""

import logging
import json
from typing import Any, Dict, List, Optional, Generator
from uuid import UUID

from django.contrib.auth.models import User
from django.utils import timezone

from ai_agent.models import Conversation, ConversationMessage
from ai_agent.services.claude_service import get_claude_service
from ai_agent.services.unified_service import get_chat_service
from ai_agent.tools import tool_registry
from ai_agent.tools.base import get_user_role
from ai_agent.prompts.system_prompts import get_prompt_for_role_and_channel

logger = logging.getLogger(__name__)


class AgentService:
    """
    Main service for handling AI agent interactions.

    Manages:
    - Conversation creation and retrieval
    - Message processing with Claude
    - Tool execution loop
    - Response generation
    """

    MAX_TOOL_ITERATIONS = 10  # Prevent infinite tool loops

    def __init__(self, purpose: str = 'chat'):
        self.claude_service = get_chat_service(purpose)

    def get_or_create_conversation(
        self,
        conversation_id: Optional[str] = None,
        channel: str = 'web',
        user: Optional[User] = None,
        business=None,
        phone_number: str = ''
    ) -> Conversation:
        """Get existing conversation or create new one."""
        if conversation_id:
            try:
                conversation = Conversation.objects.get(
                    conversation_id=conversation_id,
                    status='active'
                )
                return conversation
            except Conversation.DoesNotExist:
                pass

        # Create new conversation
        conversation = Conversation.objects.create(
            channel=channel,
            user=user,
            business=business,
            phone_number=phone_number,
            status='active',
            context={}
        )

        logger.info(f"Created new conversation: {conversation.conversation_id}")
        return conversation

    def process_message(
        self,
        message: str,
        conversation: Conversation,
        user: Optional[User] = None,
        tools_enabled: bool = True
    ) -> Dict[str, Any]:
        """
        Process a user message and generate AI response.

        Args:
            message: User's message text
            conversation: Conversation instance
            user: Optional user for auth/rate limiting
            tools_enabled: Whether to allow tool use

        Returns:
            Dict with 'response', 'tool_calls', 'conversation_id', etc.
        """
        # Store user message
        user_message = ConversationMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message
        )

        # Build message history
        messages = self._build_message_history(conversation)

        # Detect user role and get role-specific prompt/tools
        role = get_user_role(user)
        system_prompt = get_prompt_for_role_and_channel(role, conversation.channel)

        tools = None
        if tools_enabled:
            tools = tool_registry.get_claude_tools(role=role)

        # Call Claude
        user_id = user.id if user else None
        business_id = conversation.business_id if conversation.business else None

        response = self.claude_service.chat(
            messages=messages,
            system=system_prompt,
            tools=tools,
            conversation=conversation,
            user_id=user_id,
            business_id=business_id
        )

        if response.get('error'):
            return {
                'success': False,
                'error': response.get('message'),
                'conversation_id': str(conversation.conversation_id),
            }

        # Process tool calls if any
        tool_results = []
        iterations = 0

        while response.get('tool_calls') and iterations < self.MAX_TOOL_ITERATIONS:
            iterations += 1

            # Execute each tool call
            for tool_call in response['tool_calls']:
                tool_result = self._execute_tool(
                    tool_call=tool_call,
                    conversation=conversation,
                    user=user
                )
                tool_results.append(tool_result)

            # Build tool results message
            tool_results_content = []
            for result in tool_results[-len(response['tool_calls']):]:
                tool_results_content.append({
                    'type': 'tool_result',
                    'tool_use_id': result['tool_call_id'],
                    'content': json.dumps(result['result'], default=str),
                })

            # Add assistant message and tool results to history
            messages.append({
                'role': 'assistant',
                'content': response.get('content') or '',
            })

            # Add tool use blocks
            for tool_call in response['tool_calls']:
                messages[-1]['content'] = [
                    {'type': 'text', 'text': response.get('content') or ''},
                    {
                        'type': 'tool_use',
                        'id': tool_call['id'],
                        'name': tool_call['name'],
                        'input': tool_call['input'],
                    }
                ] if response.get('content') else [
                    {
                        'type': 'tool_use',
                        'id': tool_call['id'],
                        'name': tool_call['name'],
                        'input': tool_call['input'],
                    }
                ]

            # Add tool results
            messages.append({
                'role': 'user',
                'content': tool_results_content,
            })

            # Get next response
            response = self.claude_service.chat(
                messages=messages,
                system=system_prompt,
                tools=tools,
                conversation=conversation,
                user_id=user_id,
                business_id=business_id
            )

            if response.get('error'):
                break

        # Store assistant response
        final_content = response.get('content', '')
        if final_content:
            assistant_message = ConversationMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=final_content,
                tokens_input=response.get('tokens_input', 0),
                tokens_output=response.get('tokens_output', 0)
            )

        return {
            'success': True,
            'response': final_content,
            'conversation_id': str(conversation.conversation_id),
            'tool_calls': tool_results,
            'tokens_used': {
                'input': response.get('tokens_input', 0),
                'output': response.get('tokens_output', 0),
            }
        }

    def process_message_stream(
        self,
        message: str,
        conversation: Conversation,
        user: Optional[User] = None,
        tools_enabled: bool = True
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Process a message with streaming response.

        Yields chunks as they arrive from Claude.
        When Claude requests tool use, executes the tools, sends results
        back to Claude, and streams the final response.
        """
        # Store user message
        ConversationMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message
        )

        # Build message history
        messages = self._build_message_history(conversation)

        # Detect user role and get role-specific prompt/tools
        role = get_user_role(user)
        system_prompt = get_prompt_for_role_and_channel(role, conversation.channel)
        tools = tool_registry.get_claude_tools(role=role) if tools_enabled else None

        user_id = user.id if user else None
        business_id = conversation.business_id if conversation.business else None

        iterations = 0

        while iterations < self.MAX_TOOL_ITERATIONS:
            iterations += 1
            full_response = ''
            tool_calls = []

            for chunk in self.claude_service.chat_stream(
                messages=messages,
                system=system_prompt,
                tools=tools,
                conversation=conversation,
                user_id=user_id,
                business_id=business_id
            ):
                if chunk.get('type') == 'text':
                    full_response += chunk.get('text', '')
                    yield {
                        'type': 'text',
                        'content': chunk.get('text', ''),
                    }

                elif chunk.get('type') == 'tool_start':
                    yield {
                        'type': 'tool_start',
                        'tool_name': chunk.get('tool_name'),
                    }

                elif chunk.get('type') == 'tool_end':
                    tool = chunk.get('tool')
                    if tool:
                        tool_calls.append(tool)
                        # Execute tool
                        result = self._execute_tool(
                            tool_call=tool,
                            conversation=conversation,
                            user=user
                        )
                        yield {
                            'type': 'tool_result',
                            'tool_name': tool['name'],
                            'result': result['result'],
                        }

                elif chunk.get('type') == 'error':
                    yield {
                        'type': 'error',
                        'error': chunk.get('message'),
                    }

            # If no tool calls, Claude gave a final text answer — we're done
            if not tool_calls:
                if full_response:
                    ConversationMessage.objects.create(
                        conversation=conversation,
                        role='assistant',
                        content=full_response,
                    )
                yield {
                    'type': 'complete',
                    'conversation_id': str(conversation.conversation_id),
                    'tokens_used': {'input': 0, 'output': 0},
                }
                return

            # Tool calls happened — send results back to Claude for next turn
            # Build the assistant message with tool_use blocks
            assistant_content = []
            if full_response:
                assistant_content.append({'type': 'text', 'text': full_response})
            for tc in tool_calls:
                assistant_content.append({
                    'type': 'tool_use',
                    'id': tc['id'],
                    'name': tc['name'],
                    'input': tc['input'],
                })
            messages.append({'role': 'assistant', 'content': assistant_content})

            # Build tool_result messages for each tool call
            tool_results_content = []
            for tc in tool_calls:
                # Fetch the stored result from conversation messages
                tool_msg = ConversationMessage.objects.filter(
                    conversation=conversation,
                    role='tool',
                    tool_name=tc['name'],
                ).order_by('-created_at').first()
                result_data = tool_msg.tool_output if tool_msg else {'error': 'Tool result not found'}
                tool_results_content.append({
                    'type': 'tool_result',
                    'tool_use_id': tc['id'],
                    'content': json.dumps(result_data, default=str),
                })
            messages.append({'role': 'user', 'content': tool_results_content})

            # Reset full_response for next iteration — Claude will now
            # respond with the formatted answer using tool data
            full_response = ''

        # Max iterations reached
        yield {
            'type': 'complete',
            'conversation_id': str(conversation.conversation_id),
            'tokens_used': {'input': 0, 'output': 0},
        }

    def _build_message_history(
        self,
        conversation: Conversation,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Build message history for Claude from conversation."""
        messages = []

        recent_messages = conversation.messages.order_by('-created_at')[:limit]

        for msg in reversed(list(recent_messages)):
            if msg.role == 'user':
                messages.append({
                    'role': 'user',
                    'content': msg.content
                })
            elif msg.role == 'assistant':
                messages.append({
                    'role': 'assistant',
                    'content': msg.content
                })
            # Skip tool messages - they're handled separately

        return messages

    def _execute_tool(
        self,
        tool_call: Dict[str, Any],
        conversation: Conversation,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """Execute a tool call and store result."""
        tool_name = tool_call['name']
        tool_input = tool_call['input']

        logger.info(f"Executing tool: {tool_name}")

        # Execute tool
        result = tool_registry.execute_tool(
            tool_name=tool_name,
            params=tool_input,
            user=user,
            business=conversation.business
        )

        # Sanitise result so Decimal/date values don't break the JSONField or psycopg2
        safe_result = json.loads(json.dumps(result, default=str))
        ConversationMessage.objects.create(
            conversation=conversation,
            role='tool',
            content=json.dumps(safe_result),
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=safe_result
        )

        return {
            'tool_name': tool_name,
            'tool_call_id': tool_call.get('id'),
            'input': tool_input,
            'result': safe_result,
        }

    def execute_single_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        user: Optional[User] = None,
        business=None
    ) -> Dict[str, Any]:
        """
        Execute a single tool directly without conversation.

        Useful for direct API endpoints like /tools/parse-address/
        """
        return tool_registry.execute_tool(
            tool_name=tool_name,
            params=params,
            user=user,
            business=business
        )

    def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 50,
        user=None,
    ) -> Dict[str, Any]:
        """Get conversation history for display.

        ``user`` scopes the lookup. A conversation id is a UUID, but an
        unguessable id is not authorization — ids are handed back in chat and
        webhook responses, so without an owner filter anyone holding one could
        read another tenant's conversation. Staff are exempt.
        """
        try:
            conversation = Conversation.objects.get(conversation_id=conversation_id)
        except Conversation.DoesNotExist:
            return {
                'success': False,
                'error': 'Conversation not found'
            }

        if user is not None and not getattr(user, 'is_staff', False):
            owner_id = getattr(conversation, 'user_id', None)
            if owner_id is not None and owner_id != user.pk:
                # Same shape as "not found" — never confirm the id exists.
                return {'success': False, 'error': 'Conversation not found'}

        messages = conversation.messages.order_by('created_at')[:limit]

        history = []
        for msg in messages:
            history.append({
                'role': msg.role,
                'content': msg.content,
                'tool_name': msg.tool_name if msg.role == 'tool' else None,
                'created_at': msg.created_at.isoformat(),
            })

        return {
            'success': True,
            'conversation_id': str(conversation.conversation_id),
            'channel': conversation.channel,
            'status': conversation.status,
            'started_at': conversation.started_at.isoformat(),
            'messages': history,
            'total_tokens': conversation.total_tokens,
        }

    def close_conversation(self, conversation_id: str) -> bool:
        """Close/archive a conversation."""
        try:
            conversation = Conversation.objects.get(conversation_id=conversation_id)
            conversation.status = 'closed'
            conversation.save()
            return True
        except Conversation.DoesNotExist:
            return False


_agent_service_cache: dict = {}


def get_agent_service(purpose: str = 'chat') -> AgentService:
    """Get AgentService for the given purpose ('chat' or 'wa')."""
    global _agent_service_cache
    if purpose not in _agent_service_cache:
        _agent_service_cache[purpose] = AgentService(purpose=purpose)
    return _agent_service_cache[purpose]
