from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        COUNSELOR = 'counselor', 'Counselor'
        TEACHER = 'teacher', 'Teacher'
        ORGANIZATION = 'organization', 'Organization School'
        STUDENT = 'student', 'Student'
        PARENT = 'parent', 'Parent'

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=32, blank=True)
    position = models.CharField(max_length=120, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    school = models.ForeignKey(
        'admissions.School',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.role})'

    @property
    def is_counselor_like(self):
        return self.is_staff or self.role in {self.Role.ADMIN, self.Role.COUNSELOR}

    @property
    def is_task_manager(self):
        return self.is_counselor_like or self.role == self.Role.TEACHER

    @property
    def is_organization(self):
        return self.role == self.Role.ORGANIZATION
