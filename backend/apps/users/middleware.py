from collections.abc import Mapping, Sequence

from .localization import localized_api_error, request_language


def _first_error(value):
    if isinstance(value, Mapping):
        if value.get('detail'):
            return _first_error(value['detail'])
        for item in value.values():
            result = _first_error(item)
            if result:
                return result
        return ''
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            result = _first_error(item)
            if result:
                return result
        return ''
    return str(value or '').strip()


def _localized_data(value, status_code, request, language):
    if isinstance(value, Mapping):
        return {
            key: item if key == 'code' else _localized_data(item, status_code, request, language)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_localized_data(item, status_code, request, language) for item in value]
    return localized_api_error(value, status_code, request=request, language=language)


class ApiErrorLocalizationMiddleware:
    """Localize every JSON/DRF error response from one enforced boundary."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(response, 'is_rendered', False):
            self._localize(request, response)
        return response

    def process_template_response(self, request, response):
        self._localize(request, response)
        return response

    @staticmethod
    def _localize(request, response):
        if getattr(response, '_naseeb_error_localized', False):
            return
        status_code = getattr(response, 'status_code', 200)
        language = request_language(request)
        data = getattr(response, 'data', None)
        if status_code < 400 or data is None:
            return
        if language == 'en':
            # Every error body carries a human-readable top-level
            # "detail" (field errors stay alongside it), so clients never have
            # to stitch raw field names into a message.
            if isinstance(data, Mapping) and 'detail' not in data:
                response.data = {'detail': _first_error(data), **data}
            elif not isinstance(data, Mapping):
                response.data = {'detail': _first_error(data), 'errors': data}
            response._naseeb_error_localized = True
            return

        detail = localized_api_error(_first_error(data), status_code, request=request, language=language)
        localized = _localized_data(data, status_code, request, language)
        if isinstance(localized, Mapping):
            response.data = {'detail': detail, **localized}
        else:
            response.data = {'detail': detail, 'errors': localized}
        response._naseeb_error_localized = True


class StripNulQueryParamsMiddleware:
    """Drop NUL bytes from query-string values.

    PostgreSQL text columns cannot hold NUL (0x00), so `?search=a%00b` would fail
    with DataError (500). Request bodies are covered by DRF's ProhibitNullCharacters.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '\x00' in request.META.get('QUERY_STRING', '') or '%00' in request.META.get('QUERY_STRING', ''):
            cleaned = request.GET.copy()
            for key in list(cleaned.keys()):
                cleaned.setlist(key, [value.replace('\x00', '') for value in cleaned.getlist(key)])
            cleaned._mutable = False
            request.GET = cleaned
        return self.get_response(request)
