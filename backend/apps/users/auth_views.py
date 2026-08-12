from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import OperationalError, ProgrammingError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .credentials import mark_temporary_credential_used
from .localization import localized_message


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    """JWT login that accepts username OR email.

    For local demo reliability, the demo counselor account is repaired automatically
    when the expected local credentials are used.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['pv'] = user.password_version
        token['must_change_password'] = user.must_change_password
        return token

    def validate(self, attrs):
        User = get_user_model()
        login_value = str(attrs.get(self.username_field, '')).strip()
        password = attrs.get('password')

        try:
            # If the demo user was not seeded or password was accidentally changed,
            # repair it so the downloaded project logs in first try.
            if (
                settings.DEMO_ACCOUNTS_ENABLED
                and login_value in {'counselor', 'counselor@naseeb.local'}
                and password == settings.DEMO_COUNSELOR_PASSWORD
            ):
                from apps.admissions.models import School
                demo_school, _ = School.objects.get_or_create(
                    code='naseeb-edu-demo',
                    defaults={'name': 'Naseeb Edu Demo School'},
                )
                user, _ = User.objects.get_or_create(
                    username='counselor',
                    defaults={
                        'email': 'counselor@naseeb.local',
                        'first_name': 'Madina',
                        'last_name': 'Counselor',
                        'role': 'counselor',
                        'is_staff': True,
                        'school': demo_school,
                    },
                )
                user.email = user.email or 'counselor@naseeb.local'
                user.role = 'counselor'
                user.is_staff = True
                user.school = demo_school
                user.set_password(settings.DEMO_COUNSELOR_PASSWORD)
                user.save()
                attrs[self.username_field] = 'counselor'
                return super().validate(attrs)

            if '@' in login_value:
                user = User.objects.filter(email__iexact=login_value).first()
                if user:
                    attrs[self.username_field] = getattr(user, self.username_field)
        except (OperationalError, ProgrammingError):
            # Migrations have not been applied yet. Let the normal serializer return
            # a clean auth error instead of hiding the real setup mistake.
            pass

        data = super().validate(attrs)
        if self.user.must_change_password:
            credential, error_key = mark_temporary_credential_used(user=self.user, request=self.context.get('request'))
            if error_key:
                raise AuthenticationFailed({
                    'detail': localized_message(error_key, self.context.get('request')),
                    'code': error_key,
                })
            data['credential_expires_at'] = credential.expires_at
        data['must_change_password'] = self.user.must_change_password
        data['role'] = self.user.role
        return data


def token_pair_for_user(user):
    refresh = EmailOrUsernameTokenSerializer.get_token(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


class DemoAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'
