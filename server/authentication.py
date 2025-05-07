from rest_framework import authentication

from server import models


class APIToken(authentication.TokenAuthentication):
    model = models.APIToken
