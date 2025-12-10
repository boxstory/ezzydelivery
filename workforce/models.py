"""
Workforce Models Module
=======================

This module is for internal staff/workforce management models.

Note:
    Currently this module has no custom models. Workforce functionality
    is handled through:
    - core.models.Profile (is_staff flag)
    - Django's built-in User and permission system
    - Views that check staff permissions

Future Models (planned):
    - StaffRole: Custom roles beyond Django permissions
    - WorkShift: Staff shift scheduling
    - StaffPerformance: KPI tracking

Related:
    - workforce.views: Staff dashboard and management views
    - core.models.Profile: User profile with is_staff flag
"""

from django.db import models
