from django.contrib import admin
from business import models as business_models

from core import models as core_models

# Register your models here.


@admin.register(core_models.Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'email',
                    'whatsapp', 'is_business', 'is_driver', 'created_at', 'updated_at')
    list_filter = ('is_business', 'is_driver', 'created_at', 'updated_at')
    search_fields = ('user_number', 'username', 'first_name', 'last_name', 'zone_name', 'email',
                     'phone', 'whatsapp', 'address', 'verification_status', 'instagram',
                     'nationlity', 'rejection_reason', 'signup_source', 'signup_landing_path',
                     'signup_referrer', 'user__username', 'verified_by__username', 'user__email')
    search_help_text = ('Searches user number, name, username, email, phone, WhatsApp, '
                        'address, zone, verification status and signup source')
    list_select_related = ('user',)
    list_per_page = 10

@admin.register(core_models.ProfilePicture)
class ProfilePictureAdmin(admin.ModelAdmin):
    list_display = ( 'user', 'profile_picture')
    search_fields = ('user__username', 'user__email', 'profile__user_number',
                     'profile__first_name', 'profile__last_name')
    list_select_related = ('user', 'profile')
    raw_id_fields = ('user', 'profile')
    list_per_page = 10


@admin.register(business_models.Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'business_phone', 'business_whatsapp',
                     'business_since', 'business_product_category', 'business_code', 'created_at', 'updated_at')
    list_filter = ('business_status', 'created_at', 'updated_at')
    search_fields = ('business_code', 'business_name', 'business_phone', 'business_whatsapp',
                     'business_email', 'business_status', 'fulfillment_service_status',
                     'pod_kind', 'business_qid', 'business_bio', 'business_website',
                     'business_facebook_page', 'business_instagram', 'business_tiktok',
                     'business_product_category', 'business_languages', 'profile__user_number',
                     'user__username')
    search_help_text = ('Searches business name, code, phone, WhatsApp, email, QID, '
                        'website, socials, category and status')
    list_per_page = 10

@admin.register(business_models.BusinessLogo)
class BusinessLogoAdmin(admin.ModelAdmin):
    list_display = ('business', 'business_logo', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('business__business_name', 'business__business_code')
    list_select_related = ('business',)
    raw_id_fields = ('business',)
    list_per_page = 10

@admin.register(business_models.PickupLocation)
class PickupLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'pickup_location_title', 'pickup_zone_no', 'pickup_street_no',
                    'pickup_building_no', 'is_default')
    list_filter = ('pickup_status', 'is_p2p', 'is_fulfilment_center', 'is_default')
    search_fields = ('pickup_location_title', 'contact_name', 'contact_phone', 'locality',
                     'pickup_zone_no', 'pickup_street_no', 'pickup_building_no', 'pickup_status',
                     'warehouse__code', 'business__business_name')
    list_select_related = ('business',)
    raw_id_fields = ('business', 'warehouse')


@admin.register(business_models.DriverDirectory)
class DriverDirectoryAdmin(admin.ModelAdmin):
    list_display = ('business', 'driver', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('business__business_name', 'driver__driver_code', 'driver__driver_phone')
    list_select_related = ('business', 'driver')
    raw_id_fields = ('business', 'driver')
    list_per_page = 10

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(business_models.BrandedTrackingConfig)
class BrandedTrackingConfigAdmin(admin.ModelAdmin):
    list_display = ('business', 'primary_color', 'secondary_color', 'show_driver_name', 'show_driver_phone', 'show_eta', 'created_at')
    search_fields = ('custom_footer_text', 'primary_color', 'secondary_color',
                     'business__business_name')
    list_filter = ('show_driver_name', 'show_driver_phone', 'show_eta', 'is_active')
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(business_models.BusinessApiSettings)
class BusinessApiSettingsAdmin(admin.ModelAdmin):
    list_display = ('api_type', 'business', 'api_version', 'site_api_url', 'site_contry', 'order_api_endpoint', 'created_at')
    search_fields = ('google_sheet_tab_name', 'fetch_auth_name', 'api_type', 'fetch_status_path',
                     'fetch_status_include', 'api_version', 'site_api_url', 'site_contry',
                     'order_api_endpoint', 'product_api_endpoint', 'google_sheet_url',
                     'tiktok_shop_id', 'tiktok_shop_cipher', 'fetch_orders_url',
                     'fetch_auth_style', 'fetch_api_key', 'business__business_name')
    list_filter = ('api_type', 'fetch_auth_style', 'fetch_enabled', 'is_verify_api')
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(business_models.BusinessPoster)
class BusinessPosterAdmin(admin.ModelAdmin):
    list_display = ('business', 'poster_title', 'poster_order', 'is_active', 'created_at', 'updated_at')
    search_fields = ('poster_title', 'poster_description', 'business__business_name')
    list_filter = ('is_active',)
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(business_models.BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('business', 'business_address', 'business_city', 'business_state', 'business_zip_code', 'business_country', 'created_at')
    search_fields = ('business_zip_code', 'business_founters_name', 'business_uniqueness_title',
                     'business_email', 'business_phone', 'business_address', 'business_city',
                     'business_state', 'business_country', 'business_description',
                     'business_founters_bio', 'business_mision', 'business_mision_detailed',
                     'business_about_part_1', 'business_about_part_2',
                     'business_uniqueness_description', 'business__business_name')
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(business_models.BusinessSocialInfo)
class BusinessSocialInfoAdmin(admin.ModelAdmin):
    list_display = ('business', 'facebook', 'instagram', 'whatsapp', 'created_at', 'updated_at')
    search_fields = ('facebook', 'instagram', 'whatsapp', 'business__business_name')
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(business_models.BusinessTeamJoinRequest)
class BusinessTeamJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('business', 'user', 'desired_role_title', 'status', 'requested_at', 'responded_at', 'responded_by')
    search_fields = ('desired_role_title', 'message', 'status', 'business__business_name', 'user__username', 'responded_by__username')
    list_filter = ('status',)
    list_select_related = ('business', 'user', 'responded_by')
    raw_id_fields = ('business', 'user', 'responded_by')

@admin.register(business_models.BusinessTeamPermission)
class BusinessTeamPermissionAdmin(admin.ModelAdmin):
    list_display = ('team_member', 'permission_code', 'is_granted', 'granted_by', 'granted_at')
    search_fields = ('permission_code', 'team_member__team_code', 'granted_by__username')
    list_filter = ('is_granted',)
    list_select_related = ('team_member', 'granted_by')
    raw_id_fields = ('team_member', 'granted_by')

@admin.register(business_models.BusinessTeamProfile)
class BusinessTeamProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'profile', 'business', 'team_code', 'team_name', 'team_phone', 'created_at')
    search_fields = ('team_code', 'team_name', 'team_phone', 'team_email', 'team_status',
                     'team_bio', 'team_role', 'profile__user_number', 'user__username',
                     'business__business_name', 'invited_by__username')
    list_filter = ('team_role', 'team_status', 'team_verifed')
    list_select_related = ('user', 'profile', 'business')
    raw_id_fields = ('user', 'profile', 'business', 'invited_by')

@admin.register(business_models.WhatsAppNotificationTrigger)
class WhatsAppNotificationTriggerAdmin(admin.ModelAdmin):
    list_display = ('business', 'trigger_status', 'is_active', 'notification_phone', 'created_at', 'updated_at')
    search_fields = ('notification_phone', 'trigger_status', 'custom_message',
                     'business__business_name')
    list_filter = ('trigger_status', 'is_active')
    list_select_related = ('business',)
    raw_id_fields = ('business',)
