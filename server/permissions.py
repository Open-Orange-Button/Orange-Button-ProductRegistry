import django
from django.conf import settings
from rest_framework import permissions


class IsSunSpecMember(permissions.BasePermission):
    message = settings.SUNSPEC['API_PERMISSION_DENIED_MESSAGE']

    def has_permission(self, request, view):
        return request.user.groups.filter(name=settings.SUNSPEC['MEMBERSHIP_GROUP_NAME']).exists()


class IsAPITokenActive(permissions.BasePermission):
    message = settings.SUNSPEC['API_PERMISSION_DENIED_MESSAGE']

    def has_permission(self, request, view):
        return request.auth.is_active


class IsAPITokenNotExpired(permissions.BasePermission):
    message = settings.SUNSPEC['API_PERMISSION_DENIED_MESSAGE']

    def has_permission(self, request, view):
        return request.auth.expires is None or request.auth.expires >= django.utils.timezone.now()
