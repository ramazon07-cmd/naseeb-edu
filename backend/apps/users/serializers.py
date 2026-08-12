from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from .models import ProductAuditEvent, User
from .services import audit_product_action, validate_counselor_capacity


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)
    school_workspace_type = serializers.CharField(source='school.workspace_type', read_only=True)
    credential_status = serializers.SerializerMethodField()
    credential_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone', 'position', 'avatar', 'school', 'school_name', 'school_workspace_type',
            'is_active',
            'must_change_password', 'password_changed_at', 'credential_status', 'credential_expires_at',
        )
        read_only_fields = (
            'id', 'full_name', 'must_change_password', 'password_changed_at',
            'credential_status', 'credential_expires_at',
        )

    def get_full_name(self, obj) -> str | None:
        return obj.get_full_name() or obj.username

    def _credential(self, obj):
        if not hasattr(obj, '_latest_temporary_credential'):
            obj._latest_temporary_credential = obj.temporary_credentials.order_by('-issued_at', '-id').first()
        return obj._latest_temporary_credential

    def get_credential_status(self, obj):
        credential = self._credential(obj)
        if not credential:
            return 'none'
        return 'expired' if credential.is_expired else credential.status

    def get_credential_expires_at(self, obj):
        credential = self._credential(obj)
        return credential.expires_at if credential else None

    def validate_role(self, value):
        request = self.context.get('request')
        if request and not request.user.is_product_admin:
            current_role = getattr(self.instance, 'role', User.Role.STUDENT)
            if value != current_role:
                raise serializers.ValidationError('Only a product admin can change user roles.')
        return value

    def validate_school(self, value):
        request = self.context.get('request')
        if request and not request.user.is_product_admin:
            current_school = getattr(self.instance, 'school', request.user.school)
            if value != current_school:
                raise serializers.ValidationError('Only a counselor can change school membership.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        role = attrs.get('role', getattr(self.instance, 'role', User.Role.STUDENT))
        school = attrs.get('school', getattr(self.instance, 'school', None))
        if role == User.Role.COUNSELOR and not school:
            raise serializers.ValidationError({'school': 'Counselors must be connected to a school.'})
        if request and request.user.role == User.Role.COUNSELOR:
            if not request.user.school_id:
                raise serializers.ValidationError({'school': 'Your counselor account is not connected to a school.'})
            if school and school.id != request.user.school_id:
                raise serializers.ValidationError({'school': 'Counselors can only manage users in their own school.'})
        return attrs

    def _save_with_capacity(self, save):
        role = self.validated_data.get('role', getattr(self.instance, 'role', User.Role.STUDENT))
        school = self.validated_data.get('school', getattr(self.instance, 'school', None))
        active = self.validated_data.get('is_active', getattr(self.instance, 'is_active', True))
        try:
            with transaction.atomic():
                if role == User.Role.COUNSELOR and school and active:
                    validate_counselor_capacity(school=school, exclude_user_id=getattr(self.instance, 'pk', None))
                return save()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc

    def create(self, validated_data):
        return self._save_with_capacity(lambda: super(UserSerializer, self).create(validated_data))

    def update(self, instance, validated_data):
        return self._save_with_capacity(lambda: super(UserSerializer, self).update(instance, validated_data))


class CounselorProvisionSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    position = serializers.CharField(max_length=120, required=False, allow_blank=True)
    school = serializers.IntegerField(min_value=1)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already in use.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already in use.')
        return value.lower()

    def create(self, validated_data):
        from apps.admissions.models import School

        request = self.context['request']
        school_id = validated_data.pop('school')
        password = validated_data.pop('password')
        try:
            with transaction.atomic():
                school = School.objects.filter(
                    pk=school_id,
                    is_active=True,
                    workspace_type=School.WorkspaceType.SCHOOL,
                ).first()
                if not school:
                    raise serializers.ValidationError({'school': 'Select an active organization school.'})
                validate_counselor_capacity(school=school)
                counselor = User.objects.create_user(
                    **validated_data,
                    password=password,
                    role=User.Role.COUNSELOR,
                    school=school,
                )
                audit_product_action(actor=request.user, action='counselor.created', target=counselor, metadata={'school': school.pk})
                return counselor
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc


class ProductAuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductAuditEvent
        fields = '__all__'
        read_only_fields = fields

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.username if obj.actor else None


class IndividualCounselorCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    position = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already in use.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already in use.')
        return value.lower()

    @staticmethod
    def unique_workspace_identity(School, display_name, username):
        base_name = f'{display_name or username} Workspace'
        base_code = slugify(f'individual-{username}')[:72] or 'individual-counselor'
        name = base_name
        code = base_code
        suffix = 1
        while School.objects.filter(name=name).exists() or School.objects.filter(code=code).exists():
            suffix += 1
            name = f'{base_name} {suffix}'
            code = f'{base_code[:72 - len(str(suffix)) - 1]}-{suffix}'
        return name, code

    def create(self, validated_data):
        from apps.admissions.models import School

        password = validated_data.pop('password')
        display_name = ' '.join(filter(None, [validated_data.get('first_name'), validated_data.get('last_name')])).strip()
        with transaction.atomic():
            workspace_name, workspace_code = self.unique_workspace_identity(
                School, display_name, validated_data['username']
            )
            workspace = School.objects.create(
                name=workspace_name,
                code=workspace_code,
                contact_email=validated_data['email'],
                contact_phone=validated_data.get('phone', ''),
                workspace_type=School.WorkspaceType.INDIVIDUAL,
            )
            counselor = User.objects.create_user(
                **validated_data,
                password=password,
                role=User.Role.COUNSELOR,
                school=workspace,
            )
            workspace.owner_counselor = counselor
            workspace.save(update_fields=['owner_counselor', 'updated_at'])
        return counselor


class CounselorTransferSerializer(serializers.Serializer):
    school = serializers.IntegerField(min_value=1)


class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class TemporaryCredentialIssueSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_password(self, value):
        if value:
            validate_password(value, user=self.context.get('target_user'))
        return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone', 'password')

    def create(self, validated_data):
        password = validated_data.pop('password')
        # Public registration can never grant privileged roles.
        validated_data['role'] = User.Role.STUDENT
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
