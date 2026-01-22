"""
AI Agent Tools

All tools are automatically registered via the @register_tool decorator.
Import this module to ensure all tools are available.
"""

from ai_agent.tools.base import (
    BaseTool,
    ToolError,
    ToolRegistry,
    tool_registry,
    register_tool,
)

# Import tools to trigger registration
from ai_agent.tools.address_tools import (
    ParseAddressTool,
    LookupZoneTool,
    ValidateAddressTool,
    SuggestZoneTool,
)

from ai_agent.tools.order_tools import (
    LookupOrderTool,
    VerifyOrderTool,
    AssessCODRiskTool,
    SearchOrdersTool,
)

from ai_agent.tools.delivery_tools import (
    EstimateDeliveryTool,
    SuggestDriverTool,
    GetDriverStatusTool,
)

__all__ = [
    'BaseTool',
    'ToolError',
    'ToolRegistry',
    'tool_registry',
    'register_tool',
    # Address tools
    'ParseAddressTool',
    'LookupZoneTool',
    'ValidateAddressTool',
    'SuggestZoneTool',
    # Order tools
    'LookupOrderTool',
    'VerifyOrderTool',
    'AssessCODRiskTool',
    'SearchOrdersTool',
    # Delivery tools
    'EstimateDeliveryTool',
    'SuggestDriverTool',
    'GetDriverStatusTool',
]
