from collections import OrderedDict

from django import conf
from rest_framework import response
from rest_framework import pagination


class ProductsPagination(pagination.LimitOffsetPagination):
    limit_query_param = 'limit_Products'
    offset_query_param = 'offset_Products'
    max_limit = conf.settings.REST_FRAMEWORK['MAX_LIMIT']

    def get_paginated_response(self, data):
        return response.Response(OrderedDict([
            ('count', self.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('Products', data)
        ]))
