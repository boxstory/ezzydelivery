"""
Business Team Permission System
================================
Separate from Django's is_staff/is_superuser (internal workforce).
This is for client-side business team access control.

The team system has two access types:
- Owner: The user who created the business (Business.user)
- Team Member: Users added to BusinessTeamProfile with a role

Roles:
- Manager: Full operational access (orders, products, customers, reports, team view)
- Staff: Can create/edit orders and products, view customers
- Viewer: Read-only access to orders, products, customers, reports
"""


class BusinessPermissions:
    """Permission constants for business operations"""

    # Order Management
    ORDER_VIEW = 'orders_view'
    ORDER_CREATE = 'orders_create'
    ORDER_EDIT = 'orders_edit'
    ORDER_DELETE = 'orders_delete'
    ORDER_PUBLISH = 'orders_publish'  # Publish orders for delivery

    # Product Management
    PRODUCT_VIEW = 'products_view'
    PRODUCT_CREATE = 'products_create'
    PRODUCT_EDIT = 'products_edit'
    PRODUCT_DELETE = 'products_delete'

    # Customer Management
    CUSTOMER_VIEW = 'customers_view'
    CUSTOMER_MANAGE = 'customers_manage'

    # Reports & Analytics
    REPORTS_VIEW = 'reports_view'
    REPORTS_EXPORT = 'reports_export'

    # Team Management
    TEAM_VIEW = 'team_view'
    TEAM_MANAGE = 'team_manage'

    # Business Settings
    SETTINGS_VIEW = 'settings_view'
    SETTINGS_MANAGE = 'settings_manage'

    # Pickup Locations
    LOCATION_VIEW = 'locations_view'
    LOCATION_MANAGE = 'locations_manage'

    # API Management
    API_VIEW = 'api_view'
    API_MANAGE = 'api_manage'

    # All permissions as a list of (code, label) tuples
    ALL_PERMISSIONS = [
        (ORDER_VIEW, 'View Orders'),
        (ORDER_CREATE, 'Create Orders'),
        (ORDER_EDIT, 'Edit Orders'),
        (ORDER_DELETE, 'Delete Orders'),
        (ORDER_PUBLISH, 'Publish Orders'),
        (PRODUCT_VIEW, 'View Products'),
        (PRODUCT_CREATE, 'Create Products'),
        (PRODUCT_EDIT, 'Edit Products'),
        (PRODUCT_DELETE, 'Delete Products'),
        (CUSTOMER_VIEW, 'View Customers'),
        (CUSTOMER_MANAGE, 'Manage Customers'),
        (REPORTS_VIEW, 'View Reports'),
        (REPORTS_EXPORT, 'Export Reports'),
        (TEAM_VIEW, 'View Team'),
        (TEAM_MANAGE, 'Manage Team'),
        (SETTINGS_VIEW, 'View Settings'),
        (SETTINGS_MANAGE, 'Manage Settings'),
        (LOCATION_VIEW, 'View Locations'),
        (LOCATION_MANAGE, 'Manage Locations'),
        (API_VIEW, 'View API Settings'),
        (API_MANAGE, 'Manage API Settings'),
    ]

    # Permission choices for forms
    PERMISSION_CHOICES = tuple(ALL_PERMISSIONS)

    # Group permissions by category for UI display
    PERMISSION_GROUPS = {
        'Orders': [
            (ORDER_VIEW, 'View Orders'),
            (ORDER_CREATE, 'Create Orders'),
            (ORDER_EDIT, 'Edit Orders'),
            (ORDER_DELETE, 'Delete Orders'),
            (ORDER_PUBLISH, 'Publish Orders'),
        ],
        'Products': [
            (PRODUCT_VIEW, 'View Products'),
            (PRODUCT_CREATE, 'Create Products'),
            (PRODUCT_EDIT, 'Edit Products'),
            (PRODUCT_DELETE, 'Delete Products'),
        ],
        'Customers': [
            (CUSTOMER_VIEW, 'View Customers'),
            (CUSTOMER_MANAGE, 'Manage Customers'),
        ],
        'Reports': [
            (REPORTS_VIEW, 'View Reports'),
            (REPORTS_EXPORT, 'Export Reports'),
        ],
        'Team': [
            (TEAM_VIEW, 'View Team'),
            (TEAM_MANAGE, 'Manage Team'),
        ],
        'Settings': [
            (SETTINGS_VIEW, 'View Settings'),
            (SETTINGS_MANAGE, 'Manage Settings'),
            (API_VIEW, 'View API Settings'),
            (API_MANAGE, 'Manage API Settings'),
        ],
        'Locations': [
            (LOCATION_VIEW, 'View Locations'),
            (LOCATION_MANAGE, 'Manage Locations'),
        ],
    }


class TeamRoles:
    """Predefined team roles"""
    OWNER = 'owner'      # Business.user - not stored in BusinessTeamProfile
    MANAGER = 'manager'  # Full operational access
    STAFF = 'staff'      # Create/edit access
    VIEWER = 'viewer'    # Read-only access

    # Choices for team members (excludes owner - that's determined by Business.user)
    ROLE_CHOICES = [
        (MANAGER, 'Manager'),
        (STAFF, 'Staff'),
        (VIEWER, 'Viewer'),
    ]

    # All roles including owner (for display purposes)
    ALL_ROLES = [
        (OWNER, 'Owner'),
        (MANAGER, 'Manager'),
        (STAFF, 'Staff'),
        (VIEWER, 'Viewer'),
    ]


# Role-to-permission mappings
ROLE_PERMISSIONS = {
    TeamRoles.OWNER: [
        # Owners have ALL permissions
        BusinessPermissions.ORDER_VIEW,
        BusinessPermissions.ORDER_CREATE,
        BusinessPermissions.ORDER_EDIT,
        BusinessPermissions.ORDER_DELETE,
        BusinessPermissions.ORDER_PUBLISH,
        BusinessPermissions.PRODUCT_VIEW,
        BusinessPermissions.PRODUCT_CREATE,
        BusinessPermissions.PRODUCT_EDIT,
        BusinessPermissions.PRODUCT_DELETE,
        BusinessPermissions.CUSTOMER_VIEW,
        BusinessPermissions.CUSTOMER_MANAGE,
        BusinessPermissions.REPORTS_VIEW,
        BusinessPermissions.REPORTS_EXPORT,
        BusinessPermissions.TEAM_VIEW,
        BusinessPermissions.TEAM_MANAGE,
        BusinessPermissions.SETTINGS_VIEW,
        BusinessPermissions.SETTINGS_MANAGE,
        BusinessPermissions.LOCATION_VIEW,
        BusinessPermissions.LOCATION_MANAGE,
        BusinessPermissions.API_VIEW,
        BusinessPermissions.API_MANAGE,
    ],

    TeamRoles.MANAGER: [
        # Managers: Full operational access (no settings/API management)
        BusinessPermissions.ORDER_VIEW,
        BusinessPermissions.ORDER_CREATE,
        BusinessPermissions.ORDER_EDIT,
        BusinessPermissions.ORDER_DELETE,
        BusinessPermissions.ORDER_PUBLISH,
        BusinessPermissions.PRODUCT_VIEW,
        BusinessPermissions.PRODUCT_CREATE,
        BusinessPermissions.PRODUCT_EDIT,
        BusinessPermissions.PRODUCT_DELETE,
        BusinessPermissions.CUSTOMER_VIEW,
        BusinessPermissions.CUSTOMER_MANAGE,
        BusinessPermissions.REPORTS_VIEW,
        BusinessPermissions.REPORTS_EXPORT,
        BusinessPermissions.TEAM_VIEW,
        BusinessPermissions.TEAM_MANAGE,
        BusinessPermissions.SETTINGS_VIEW,
        BusinessPermissions.LOCATION_VIEW,
        BusinessPermissions.LOCATION_MANAGE,
    ],

    TeamRoles.STAFF: [
        # Staff: Create/edit orders and products, view customers/reports
        BusinessPermissions.ORDER_VIEW,
        BusinessPermissions.ORDER_CREATE,
        BusinessPermissions.ORDER_EDIT,
        BusinessPermissions.PRODUCT_VIEW,
        BusinessPermissions.PRODUCT_CREATE,
        BusinessPermissions.PRODUCT_EDIT,
        BusinessPermissions.CUSTOMER_VIEW,
        BusinessPermissions.REPORTS_VIEW,
        BusinessPermissions.LOCATION_VIEW,
    ],

    TeamRoles.VIEWER: [
        # Viewer: Read-only access
        BusinessPermissions.ORDER_VIEW,
        BusinessPermissions.PRODUCT_VIEW,
        BusinessPermissions.CUSTOMER_VIEW,
        BusinessPermissions.REPORTS_VIEW,
        BusinessPermissions.LOCATION_VIEW,
    ],
}


def get_role_permissions(role):
    """
    Get default permissions for a role.

    Args:
        role: Role string from TeamRoles

    Returns:
        list: List of permission codes for the role
    """
    return ROLE_PERMISSIONS.get(role, [])


def get_all_permission_codes():
    """
    Get list of all permission codes.

    Returns:
        list: List of all permission code strings
    """
    return [perm[0] for perm in BusinessPermissions.ALL_PERMISSIONS]


def get_permission_label(permission_code):
    """
    Get human-readable label for a permission code.

    Args:
        permission_code: Permission code string

    Returns:
        str: Human-readable label or the code itself if not found
    """
    permission_dict = dict(BusinessPermissions.ALL_PERMISSIONS)
    return permission_dict.get(permission_code, permission_code)


def get_role_label(role):
    """
    Get human-readable label for a role.

    Args:
        role: Role string from TeamRoles

    Returns:
        str: Human-readable label or the role itself if not found
    """
    role_dict = dict(TeamRoles.ALL_ROLES)
    return role_dict.get(role, role)
