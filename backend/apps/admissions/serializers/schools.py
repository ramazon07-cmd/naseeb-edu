"""Admissions API serializers — schools."""
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from apps.users import entitlements
from apps.users.models import User
from apps.users.credentials import issue_temporary_credential
from ..models import School


class SchoolSerializer(serializers.ModelSerializer):
    students_count = serializers.IntegerField(read_only=True)
    owner_counselor_name = serializers.SerializerMethodField()
    organization_account_id = serializers.SerializerMethodField()
    organization_account_username = serializers.SerializerMethodField()
    organization_credential_status = serializers.SerializerMethodField()
    organization_credential_expires_at = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()
    seat_usage = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = '__all__'

    IMMUTABLE_AFTER_CREATE = ('workspace_type', 'owner_counselor')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            changed = [
                field for field in self.IMMUTABLE_AFTER_CREATE
                if field in attrs and attrs[field] != getattr(self.instance, field)
            ]
            if changed:
                raise serializers.ValidationError({
                    field: 'This workspace setting cannot be changed after creation.' for field in changed
                })
        return attrs

    def get_subscription(self, obj):
        # Every school gets a subscription on creation; a missing row means a
        # fresh instance that was not loaded through the annotated queryset.
        try:
            subscription = obj.subscription
        except School.subscription.RelatedObjectDoesNotExist:
            return None
        return entitlements.workspace_summary(subscription)

    def get_seat_usage(self, obj):
        if not hasattr(obj, 'max_counselors_used'):
            return None
        return {key: getattr(obj, f'{key}_used') for key in entitlements.SEAT_ROLES}

    def get_owner_counselor_name(self, obj):
        if not obj.owner_counselor:
            return None
        return obj.owner_counselor.get_full_name() or obj.owner_counselor.username

    def _organization_account(self, obj):
        if not hasattr(obj, '_organization_account'):
            prefetched = getattr(obj, 'prefetched_organization_accounts', None)
            if prefetched is not None:
                obj._organization_account = prefetched[0] if prefetched else None
            else:
                obj._organization_account = obj.users.filter(role=User.Role.ORGANIZATION).order_by('pk').first()
        return obj._organization_account

    def _organization_credential(self, obj):
        account = self._organization_account(obj)
        if not account:
            return None
        if not hasattr(obj, '_organization_credential'):
            prefetched = getattr(account, '_prefetched_objects_cache', {}).get('temporary_credentials')
            if prefetched is not None:
                ordered = sorted(prefetched, key=lambda item: (item.issued_at, item.id), reverse=True)
                obj._organization_credential = ordered[0] if ordered else None
            else:
                obj._organization_credential = account.temporary_credentials.order_by('-issued_at', '-id').first()
        return obj._organization_credential

    def get_organization_account_id(self, obj):
        account = self._organization_account(obj)
        return account.id if account else None

    def get_organization_account_username(self, obj):
        account = self._organization_account(obj)
        return account.username if account else None

    def get_organization_credential_status(self, obj):
        credential = self._organization_credential(obj)
        if not credential:
            return 'none'
        return 'expired' if credential.is_expired else credential.status

    def get_organization_credential_expires_at(self, obj):
        credential = self._organization_credential(obj)
        return credential.expires_at if credential else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('organization_credential_status', None)
            data.pop('organization_credential_expires_at', None)
        return data


class OrganizationAccountSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already in use.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already in use.')
        return value.lower()

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(
            **validated_data,
            password=None,
            role=User.Role.ORGANIZATION,
            school=self.context['school'],
        )
        user, _, _, _ = issue_temporary_credential(
            user=user,
            issued_by=self.context['request'].user,
            raw_password=password,
            request=self.context['request'],
        )
        return user
