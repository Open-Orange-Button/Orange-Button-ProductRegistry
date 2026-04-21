from django.contrib import admin, messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path

from server.feedback import send_test_webhook
from server.models import FeedbackSubmission, SiteSettings


@admin.register(FeedbackSubmission)
class FeedbackSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'category',
        'email',
        'first_name',
        'last_name',
        'email_delivered_at',
        'webhook_delivered_at',
    )
    list_filter = ('category', 'created_at', 'email_delivered_at', 'webhook_delivered_at')
    search_fields = ('email', 'first_name', 'last_name', 'message')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = (
        'created_at', 'first_name', 'last_name', 'email', 'phone',
        'category', 'message', 'source_ip', 'user_agent',
        'email_delivered_at', 'webhook_delivered_at', 'delivery_notes',
    )

    def has_add_permission(self, request):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    change_form_template = 'admin/server/sitesettings/change_form.html'

    def has_add_permission(self, request):
        # Singleton: hide "Add" if a row already exists
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Auto-redirect the changelist to the single instance's change page
        SiteSettings.get()  # ensure pk=1 exists
        return redirect('admin:server_sitesettings_change', object_id=1)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'send-test-webhook/',
                self.admin_site.admin_view(self.send_test_webhook_view),
                name='server_sitesettings_send_test_webhook',
            ),
        ]
        return custom + urls

    def send_test_webhook_view(self, request):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        settings_row = SiteSettings.get()
        ok, detail = send_test_webhook(settings_row)
        if ok:
            messages.success(request, f'Test webhook sent successfully. {detail}')
        else:
            messages.error(request, f'Test webhook failed: {detail}')
        return redirect('admin:server_sitesettings_change', object_id=settings_row.pk)
