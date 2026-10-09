"""An API error with a stable machine-readable code in its body: {"detail": ..., "code": ...}.

Clients key their (translated) message on ``code``; ``detail`` stays a readable
English sentence for anything that does not know the code.
"""
from rest_framework import exceptions, status


class CodedError(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'error'

    def __init__(self, detail, code, status_code=None):
        if status_code:
            self.status_code = status_code
        super().__init__({'detail': detail, 'code': code}, code)
