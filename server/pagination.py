from collections import OrderedDict
from rest_framework import response
from rest_framework import pagination


class ProductsPagination(pagination.LimitOffsetPagination):
    def get_paginated_response(self, data):
        return response.Response(OrderedDict([
            ('count', self.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('Products', data)
        ]))
