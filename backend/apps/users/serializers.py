from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone', 'position', 'avatar', 'school', 'school_name',
        )
        read_only_fields = ('id', 'full_name')

    def get_full_name(self, obj) -> str | None:
        return obj.get_full_name() or obj.username

    def validate_role(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like:
            current_role = getattr(self.instance, 'role', User.Role.STUDENT)
            if value != current_role:
                raise serializers.ValidationError('Only a counselor can change user roles.')
        return value

    def validate_school(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like:
            current_school = getattr(self.instance, 'school', request.user.school)
            if value != current_school:
                raise serializers.ValidationError('Only a counselor can change school membership.')
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
