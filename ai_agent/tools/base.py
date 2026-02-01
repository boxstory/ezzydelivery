"""
Base Tool Class

Provides the foundation for all AI agent tools with consistent
interface, error handling, and logging.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ai_agent.models import AgentTool

logger = logging.getLogger(__name__)


def get_user_role(user) -> str:
    """
    Detect user role from Profile flags.

    Priority: staff > business > driver > anonymous
    """
    if user is None:
        return 'anonymous'
    # Staff/workforce takes priority
    if user.is_staff:
        return 'staff'
    try:
        profile = user.profile
        if profile.is_staff:
            return 'staff'
        if profile.is_business:
            return 'business'
        if profile.is_driver:
            return 'driver'
    except Exception:
        pass
    return 'anonymous'


class ToolError(Exception):
    """Exception raised when a tool execution fails."""

    def __init__(self, message: str, code: str = 'TOOL_ERROR'):
        self.message = message
        self.code = code
        super().__init__(self.message)


class BaseTool(ABC):
    """
    Abstract base class for AI agent tools.

    All tools must implement:
    - name: Tool identifier
    - description: What the tool does (shown to Claude)
    - parameters_schema: JSON Schema for input parameters
    - execute(): The actual tool logic

    Usage:
        class MyTool(BaseTool):
            name = 'my_tool'
            description = 'Does something useful'
            parameters_schema = {
                'type': 'object',
                'properties': {'arg1': {'type': 'string'}},
                'required': ['arg1']
            }

            def execute(self, arg1: str) -> Dict[str, Any]:
                return {'result': arg1}
    """

    name: str = ''
    description: str = ''
    parameters_schema: Dict[str, Any] = {}
    requires_auth: bool = False
    allowed_roles: list = ['staff', 'business', 'driver']

    def __init__(self):
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define 'name'")
        if not self.description:
            raise ValueError(f"{self.__class__.__name__} must define 'description'")

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool with the given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Dict containing the tool result

        Raises:
            ToolError: If execution fails
        """
        pass

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate input parameters against the schema.

        Override this method for custom validation logic.
        """
        # Basic required field check
        required = self.parameters_schema.get('required', [])
        for field in required:
            if field not in params:
                raise ToolError(f"Missing required parameter: {field}", 'MISSING_PARAM')

        return params

    def run(self, params: Dict[str, Any], user=None, business=None) -> Dict[str, Any]:
        """
        Run the tool with full error handling and logging.

        Args:
            params: Tool input parameters
            user: Optional user for auth check
            business: Optional business context

        Returns:
            Dict with 'success', 'data' or 'error' keys
        """
        start_time = time.time()

        try:
            # Auth check
            if self.requires_auth and not user:
                return {
                    'success': False,
                    'error': 'Authentication required',
                    'code': 'AUTH_REQUIRED'
                }

            # Validate parameters
            validated_params = self.validate_params(params)

            # Execute tool
            result = self.execute(**validated_params)

            # Log success
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Tool {self.name} executed in {latency_ms}ms")

            # Update tool stats
            self._update_stats(latency_ms, success=True)

            return {
                'success': True,
                'data': result
            }

        except ToolError as e:
            logger.warning(f"Tool {self.name} error: {e.message}")
            self._update_stats(0, success=False)
            return {
                'success': False,
                'error': e.message,
                'code': e.code
            }

        except Exception as e:
            logger.exception(f"Tool {self.name} unexpected error")
            self._update_stats(0, success=False)
            return {
                'success': False,
                'error': str(e),
                'code': 'INTERNAL_ERROR'
            }

    def _update_stats(self, latency_ms: int, success: bool) -> None:
        """Update tool statistics in database."""
        try:
            tool_record, _ = AgentTool.objects.get_or_create(
                name=self.name,
                defaults={
                    'description': self.description,
                    'schema': self.to_claude_schema(),
                }
            )

            tool_record.total_calls += 1
            if not success:
                tool_record.total_errors += 1

            # Update running average latency
            if latency_ms > 0 and tool_record.total_calls > 1:
                prev_avg = tool_record.avg_latency_ms
                n = tool_record.total_calls
                tool_record.avg_latency_ms = int(prev_avg + (latency_ms - prev_avg) / n)

            tool_record.save()

        except Exception as e:
            logger.error(f"Failed to update tool stats: {e}")

    def to_claude_schema(self) -> Dict[str, Any]:
        """
        Convert tool to Claude's tool format.

        Returns:
            Dict in Claude's expected tool schema format
        """
        return {
            'name': self.name,
            'description': self.description,
            'input_schema': self.parameters_schema
        }


class ToolRegistry:
    """
    Registry for managing available tools.

    Provides tool lookup and schema generation for Claude.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} already registered, overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_claude_tools(self, tool_names: Optional[list] = None, role: Optional[str] = None) -> list:
        """
        Get tool schemas for Claude API.

        Args:
            tool_names: Optional list of tool names to include.
                       If None, includes all tools.
            role: Optional user role to filter tools by allowed_roles.

        Returns:
            List of tool schemas in Claude format
        """
        if tool_names is None:
            tools = list(self._tools.values())
        else:
            tools = [self._tools[name] for name in tool_names if name in self._tools]

        if role:
            tools = [t for t in tools if role in t.allowed_roles]

        return [tool.to_claude_schema() for tool in tools]

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        user=None,
        business=None
    ) -> Dict[str, Any]:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters
            user: Optional user context
            business: Optional business context

        Returns:
            Tool execution result
        """
        tool = self.get(tool_name)
        if not tool:
            return {
                'success': False,
                'error': f"Unknown tool: {tool_name}",
                'code': 'UNKNOWN_TOOL'
            }

        # Role enforcement
        role = get_user_role(user)
        if role not in tool.allowed_roles:
            logger.warning(f"Role {role} denied access to tool {tool_name}")
            return {
                'success': False,
                'error': 'Access denied for your role',
                'code': 'ROLE_DENIED'
            }

        return tool.run(params, user=user, business=business)


# Global registry instance
tool_registry = ToolRegistry()


def register_tool(tool_class):
    """
    Decorator to register a tool class.

    Usage:
        @register_tool
        class MyTool(BaseTool):
            ...
    """
    tool_instance = tool_class()
    tool_registry.register(tool_instance)
    return tool_class
