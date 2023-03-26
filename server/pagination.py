from collections import OrderedDict

from django import conf
from rest_framework import response, pagination, utils


class ProductsPagination(pagination.LimitOffsetPagination):
    limit_query_param = 'limit_Products'
    offset_query_param = 'offset_Products'
    limit_SubstituteProducts_query_param = 'limit_SubstituteProducts'
    offset_SubstituteProducts_query_param = 'offset_SubstituteProducts'
    max_limit = conf.settings.REST_FRAMEWORK['MAX_LIMIT']

    def paginate_queryset(self, queryset, request, view=None, max_count_SubstituteProducts=0):
        page = super().paginate_queryset(queryset, request, view=view)

        self.max_count_SubstituteProducts = max_count_SubstituteProducts
        self.offset_SubstituteProducts = self.get_offset_SubstituteProducts(request)
        self.limit_SubstituteProducts = self.get_limit_SubstituteProducts(request)

        return page

    def get_offset_SubstituteProducts(self, request):
        try:
            offset = int(request.query_params[self.offset_SubstituteProducts_query_param])
            if offset <= 0:
                return 0
            return offset
        except (KeyError, ValueError):
            return 0

    def get_limit_SubstituteProducts(self, request):
        try:
            limit = int(request.query_params[self.limit_SubstituteProducts_query_param])
            if limit <= 0:
                return self.default_limit
            return limit
        except (KeyError, ValueError):
            return self.default_limit

    def get_next_Products_link(self):
        return super().get_next_link()

    def get_prev_Products_link(self):
        return super().get_previous_link()

    def get_next_SubstituteProducts_link(self):
        offset_SubstituteProducts = self.offset_SubstituteProducts + self.limit_SubstituteProducts
        if offset_SubstituteProducts >= self.max_count_SubstituteProducts:
            return None

        url = self.request.build_absolute_uri()

        url = utils.urls.replace_query_param(url, self.limit_SubstituteProducts_query_param, self.limit_SubstituteProducts)
        return utils.urls.replace_query_param(url, self.offset_SubstituteProducts_query_param, offset_SubstituteProducts)

    def get_prev_SubstituteProducts_link(self):
        if self.offset_SubstituteProducts <= 0:
            return None

        url = self.request.build_absolute_uri()

        url = utils.urls.replace_query_param(url, self.limit_SubstituteProducts_query_param, self.limit_SubstituteProducts)

        offset_SubstituteProducts = self.offset_SubstituteProducts - self.limit_SubstituteProducts
        if offset_SubstituteProducts <= 0:
            return utils.urls.remove_query_param(url, self.offset_SubstituteProducts_query_param)

        return utils.urls.replace_query_param(url, self.offset_SubstituteProducts_query_param, offset_SubstituteProducts)

    def get_paginated_response(self, data, debug_dict=None):
        res = OrderedDict(
            count_Products=self.count,
            next_Products=self.get_next_Products_link(),
            prev_Products=self.get_prev_Products_link(),
            max_count_SubstituteProducts=self.max_count_SubstituteProducts,
            next_SubstituteProducts=self.get_next_SubstituteProducts_link(),
            prev_SubstituteProducts=self.get_prev_SubstituteProducts_link(),
            Products=data
        )
        if self.request.query_params.get('debug', None) == 'true':
            res['debug'] = debug_dict
            res.move_to_end('debug', last=False)
        return response.Response(res)
