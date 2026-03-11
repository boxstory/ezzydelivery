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
)

from ai_agent.tools.order_tools import (
    LookupOrderTool,
)

from ai_agent.tools.delivery_tools import (
    GetDriverStatusTool,
)

from ai_agent.tools.business_tools import (
    GetBusinessDashboardTool,
    SearchBusinessOrdersTool,
    GetBusinessDeliveriesTool,
    GetBusinessCODSummaryTool,
    GetBusinessCustomersTool,
)

from ai_agent.tools.import_tools import (
    ListImportSourcesTool,
    ImportFromOneDriveTool,
    ImportFromApiTool,
    ParseTextToOrdersTool,
    GetImportHistoryTool,
    GetTempOrdersTool,
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
    # Order tools
    'LookupOrderTool',
    # Delivery tools
    'GetDriverStatusTool',
    # Business tools
    'GetBusinessDashboardTool',
    'SearchBusinessOrdersTool',
    'GetBusinessDeliveriesTool',
    'GetBusinessCODSummaryTool',
    'GetBusinessCustomersTool',
    # Import tools
    'ListImportSourcesTool',
    'ImportFromOneDriveTool',
    'ImportFromApiTool',
    'ParseTextToOrdersTool',
    'GetImportHistoryTool',
    'GetTempOrdersTool',
]
