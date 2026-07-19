from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import OperationalError, ProgrammingError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    """JWT login that accepts username OR email.

    For local demo reliability, the demo counselor account is repaired automatically
    when the expected local credentials are used.
    """

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
                user, _ = User.objects.get_or_create(
                    username='counselor',
                    defaults={
                        'email': 'counselor@naseeb.local',
                        'first_name': 'Madina',
                        'last_name': 'Counselor',
                        'role': 'counselor',
                        'is_staff': True,
                    },
                )
                user.email = user.email or 'counselor@naseeb.local'
                user.role = 'counselor'
                user.is_staff = True
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

        return super().validate(attrs)


class DemoAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer
