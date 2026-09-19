"""Student-owned profile input, independent of counselor administration."""
from rest_framework import serializers

COUNTRIES = ['US', 'UK', 'Canada', 'Turkey', 'Vietnam', 'Hong Kong', 'China']

class SubjectScoreSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['AP', 'IB'])
    subject = serializers.CharField(max_length=160)
    score = serializers.IntegerField(min_value=1, max_value=7)

    def validate(self, attrs):
        if attrs['type'] == 'AP' and attrs['score'] > 5:
            raise serializers.ValidationError({'score': 'AP scores must be between 1 and 5.'})
        return attrs

class HonorSerializer(serializers.Serializer):
    role = serializers.CharField(max_length=160)
    project = serializers.CharField(max_length=180)
    description = serializers.CharField(max_length=3000)
    grade = serializers.CharField(max_length=20, required=False, allow_blank=True)
    recognition = serializers.ChoiceField(choices=['School', 'State/Regional', 'National', 'International'])

class ActivitySerializer(serializers.Serializer):
    type = serializers.CharField(max_length=100)
    position = serializers.CharField(max_length=160)
    organization = serializers.CharField(max_length=180)
    description = serializers.CharField(max_length=3000)
    grades = serializers.CharField(max_length=50)
    hours = serializers.IntegerField(min_value=0, max_value=168)
    weeks = serializers.IntegerField(min_value=0, max_value=52)

class OnboardingSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    middle_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150)
    gender = serializers.ChoiceField(choices=['Male', 'Female', 'Prefer not to say'])
    grade = serializers.ChoiceField(choices=['8', '9', '10', '11', 'gap'])
    graduation_year = serializers.IntegerField(min_value=2000, max_value=2100)
    first_generation = serializers.ChoiceField(choices=['', 'Yes', 'No', 'Not sure'], required=False)
    family_income = serializers.ChoiceField(choices=['Under $10,000', '$10,000–$25,000', '$25,000–$50,000', '$50,000–$100,000', '$100,000+'])
    residency_status = serializers.CharField(max_length=160, required=False, allow_blank=True)
    guardian_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    guardian_relation = serializers.ChoiceField(choices=['', 'mother', 'father', 'guardian'], required=False, allow_blank=True)
    guardian_contact = serializers.CharField(max_length=120, required=False, allow_blank=True)
    school_name = serializers.CharField(max_length=180)
    country = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    class_size = serializers.IntegerField(min_value=1, max_value=100000, required=False, allow_null=True)
    class_rank = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    gpa_scale = serializers.ChoiceField(choices=['4', '5', '100'])
    gpa = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0)
    ielts_status = serializers.ChoiceField(choices=['not_taken', 'planning', 'scheduled', 'taken', 'not_required'])
    ielts_score = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=0, max_value=9, required=False, allow_null=True)
    sat_status = serializers.ChoiceField(choices=['not_taken', 'planning', 'scheduled', 'taken', 'not_required'], required=False)
    sat_reading = serializers.IntegerField(min_value=200, max_value=800, required=False, allow_null=True)
    sat_math = serializers.IntegerField(min_value=200, max_value=800, required=False, allow_null=True)
    sat_attempts = serializers.IntegerField(min_value=0, max_value=100, default=0)
    subjects = SubjectScoreSerializer(many=True, max_length=50, required=False)
    target_countries = serializers.CharField(max_length=255)
    interests = serializers.ListField(child=serializers.CharField(max_length=80), max_length=30, required=False)
    program_strengths = serializers.ListField(child=serializers.CharField(max_length=100), max_length=10, required=False)
    personal_story = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    honors = HonorSerializer(many=True, max_length=50, required=False)
    activities = ActivitySerializer(many=True, max_length=50, required=False)

    def validate_target_countries(self, value):
        countries = list(dict.fromkeys(country.strip() for country in value.split(',')))
        if not countries or any(country not in COUNTRIES for country in countries):
            raise serializers.ValidationError('Select one or more supported countries.')
        return ', '.join(countries)

    def validate(self, attrs):
        errors = {}
        if attrs['gpa'] > int(attrs['gpa_scale']):
            errors['gpa'] = 'GPA cannot exceed its scale.'
        if attrs.get('class_rank') and attrs.get('class_size') is not None and attrs['class_rank'] > attrs['class_size']:
            errors['class_rank'] = 'Rank cannot exceed class size.'
        if attrs['ielts_status'] == 'taken':
            if attrs.get('ielts_score') is None:
                errors['ielts_score'] = 'Enter your IELTS score.'
            elif attrs['ielts_score'] * 2 % 1:
                errors['ielts_score'] = 'Use increments of 0.5.'
        else:
            attrs['ielts_score'] = None
        sat_status = attrs.setdefault('sat_status', 'taken' if attrs.get('sat_reading') or attrs.get('sat_math') else 'not_taken')
        if sat_status != 'taken':
            attrs.update(sat_reading=None, sat_math=None, sat_attempts=0)
        elif not attrs.get('sat_reading') or not attrs.get('sat_math'):
            errors['sat_math'] = 'Enter both SAT section scores when a score is available.'
        if bool(attrs.get('sat_reading')) != bool(attrs.get('sat_math')):
            errors['sat_math'] = 'Enter both SAT sections or leave both blank.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
