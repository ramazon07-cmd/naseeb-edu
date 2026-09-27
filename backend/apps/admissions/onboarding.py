"""Student-owned profile input, independent of counselor administration."""
import datetime

from django.utils import timezone
from rest_framework import serializers

from .exam_scores import EXAM_KEYS, IELTS_FIELDS, IELTS_SECTIONS, MAX_ATTEMPTS, SAT_FIELDS, ielts_overall, sat_sent_total
from .progress import percent

COUNTRIES = ['US', 'UK', 'Canada', 'Turkey', 'Vietnam', 'Hong Kong', 'China']

TEST_STATUSES = ['not_taken', 'planning', 'scheduled', 'taken', 'not_required']
EARLIEST_TEST_DATE = datetime.date(2015, 1, 1)


class SubjectScoreSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['AP', 'IB'], error_messages={'invalid_choice': 'Choose AP or IB.'})
    subject = serializers.CharField(max_length=160, error_messages={'blank': 'Enter the subject.'})
    score = serializers.IntegerField(min_value=1, max_value=7, error_messages={
        'min_value': 'Scores start at 1.', 'max_value': 'IB scores go from 1 to 7.', 'invalid': 'Enter a whole number.',
    })

    def validate(self, attrs):
        if attrs['type'] == 'AP' and attrs['score'] > 5:
            raise serializers.ValidationError({'score': 'AP scores go from 1 to 5.'})
        return attrs


HALF_BAND = 'Use whole or half bands, like 6 or 6.5.'
SAT_STEP = 'SAT scores go up in steps of 10, like 650 or 660.'


def validate_half_band(value):
    if value is not None and value * 2 % 1:
        raise serializers.ValidationError(HALF_BAND)


def validate_sat_step(value):
    if value is not None and value % 10:
        raise serializers.ValidationError(SAT_STEP)


def band_field(**kwargs):
    return serializers.DecimalField(max_digits=2, decimal_places=1, min_value=0, max_value=9, required=False, allow_null=True, error_messages={
        'min_value': 'IELTS bands go from 0 to 9.', 'max_value': 'IELTS bands go from 0 to 9.', 'invalid': 'Enter a band like 6.5.',
        'max_decimal_places': HALF_BAND,
    }, **kwargs)


def sat_total_field(**kwargs):
    """The SAT total written on its own (profile edit): 400 to 1600 in steps of 10."""
    return serializers.IntegerField(min_value=400, max_value=1600, required=False, allow_null=True, error_messages={
        'min_value': 'SAT totals go from 400 to 1600.', 'max_value': 'SAT totals go from 400 to 1600.',
        'invalid': 'Enter a whole number.',
    }, validators=[validate_sat_step], **kwargs)


def sat_section_field():
    return serializers.IntegerField(min_value=200, max_value=800, required=False, allow_null=True, error_messages={
        'min_value': 'SAT section scores go from 200 to 800.', 'max_value': 'SAT section scores go from 200 to 800.',
        'invalid': 'Enter a whole number.',
    })


def attempts_field():
    return serializers.IntegerField(min_value=0, max_value=MAX_ATTEMPTS, required=False, allow_null=True, error_messages={
        'max_value': f'Enter a number from 1 to {MAX_ATTEMPTS}.', 'min_value': f'Enter a number from 1 to {MAX_ATTEMPTS}.',
    })

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

SAT_INPUTS = frozenset(name for name in SAT_FIELDS if name != 'sat_score')
# Rules that read several answers. A partial edit that touches one member is
# checked against the stored values of the others.
CROSS_FIELD_GROUPS = (
    frozenset({'gpa', 'gpa_scale'}),
    frozenset({'class_size', 'class_rank'}),
    frozenset(IELTS_FIELDS),
    SAT_INPUTS,
)


def current_answers(profile):
    """The stored answers of a profile, in the shape OnboardingSerializer validates."""
    answers = {key: value for key, value in (profile.application_profile or {}).items() if key not in EXAM_KEYS}
    answers.update(
        first_name=profile.user.first_name, last_name=profile.user.last_name, grade=profile.grade,
        school_name=profile.school_name, gpa=profile.gpa, target_countries=profile.target_countries,
        gpa_scale=str(profile.gpa_scale) if profile.gpa_scale else None,
        guardian_name=profile.guardian_name, guardian_relation=profile.guardian_relation,
        guardian_contact=profile.parent_contact,
    )
    answers.update({name: getattr(profile, name) for name in EXAM_KEYS})
    return answers


class OnboardingSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    middle_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150)
    gender = serializers.ChoiceField(choices=['Male', 'Female', 'Prefer not to say'])
    grade = serializers.ChoiceField(choices=['8', '9', '10', '11', 'gap'])
    graduation_year = serializers.IntegerField(min_value=2000, max_value=2100)
    first_generation = serializers.ChoiceField(choices=['', 'Yes', 'No', 'Not sure'], required=False)
    # Optional: many students are minors and may not know or want to share it.
    family_income = serializers.ChoiceField(
        choices=['Under $10,000', '$10,000–$25,000', '$25,000–$50,000', '$50,000–$100,000', '$100,000+', 'Prefer not to say'],
        required=False,
        allow_blank=True,
    )
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
    ielts_status = serializers.ChoiceField(choices=TEST_STATUSES)
    ielts_score = band_field()
    ielts_listening = band_field()
    ielts_reading = band_field()
    ielts_writing = band_field()
    ielts_speaking = band_field()
    ielts_test_date = serializers.DateField(required=False, allow_null=True)
    ielts_attempts = attempts_field()
    sat_status = serializers.ChoiceField(choices=TEST_STATUSES, required=False)
    sat_reading = sat_section_field()
    sat_math = sat_section_field()
    sat_test_date = serializers.DateField(required=False, allow_null=True)
    sat_attempts = attempts_field()
    sat_superscore = serializers.BooleanField(required=False, allow_null=True)
    sat_superscore_reading = sat_section_field()
    sat_superscore_math = sat_section_field()
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
        if self.partial:
            if not attrs:
                raise serializers.ValidationError({'detail': 'There is nothing to save.'})
            self._fill_related(attrs)
        errors = {}
        if attrs.get('gpa') is not None and attrs.get('gpa_scale') and attrs['gpa'] > int(attrs['gpa_scale']):
            errors['gpa'] = 'GPA cannot exceed its scale.'
        if attrs.get('class_rank') and attrs.get('class_size') is not None and attrs['class_rank'] > attrs['class_size']:
            errors['class_rank'] = 'Rank cannot exceed class size.'
        if not self.partial or 'ielts_status' in attrs:
            self._validate_ielts(attrs, errors)
        if not self.partial or attrs.keys() & SAT_INPUTS:
            self._validate_sat(attrs, errors)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _fill_related(self, attrs):
        current = self.context.get('current') or {}
        for group in CROSS_FIELD_GROUPS:
            if attrs.keys() & group:
                for name in group - attrs.keys():
                    if name in current:
                        attrs[name] = current[name]

    def answers_representation(self):
        """Validated answers as JSON for application_profile, without test scores.

        Only the answers present are included, so a partial edit merges into
        the stored answers instead of replacing them.
        """
        out = {}
        for key, value in self.validated_data.items():
            if key in EXAM_KEYS or key not in self.fields:
                continue
            out[key] = None if value is None else self.fields[key].to_representation(value)
        return out

    @staticmethod
    def _check_date(attrs, errors, key, status):
        value = attrs.get(key)
        today = timezone.localdate()
        if status == 'taken':
            if value is None:
                errors[key] = 'Enter the date you took the test.'
            elif value > today:
                errors[key] = 'This date is in the future. If the test has not happened yet, choose "I have booked a test date".'
        elif status == 'scheduled' and value is None:
            errors[key] = 'Enter the date of your booked test.'
        if value is not None and key not in errors:
            if value < EARLIEST_TEST_DATE:
                errors[key] = 'Enter a date from 2015 or later.'
            elif value > today + datetime.timedelta(days=3 * 366):
                errors[key] = 'Enter a date within the next three years.'

    @staticmethod
    def _check_attempts(attrs, errors, key):
        if attrs.get(key) is None:
            attrs[key] = 1
        elif attrs[key] < 1:
            errors[key] = f'Enter a number from 1 to {MAX_ATTEMPTS}.'

    def _validate_ielts(self, attrs, errors):
        status = attrs['ielts_status']
        if status != 'taken':
            # Only a booked or planned test keeps a date; nothing else applies.
            test_date = attrs.get('ielts_test_date') if status in ('planning', 'scheduled') else None
            attrs.update({name: None for name in IELTS_FIELDS if name != 'ielts_status'}, ielts_test_date=test_date)
            if status in ('planning', 'scheduled'):
                self._check_date(attrs, errors, 'ielts_test_date', status)
            return
        for name in ('ielts_score', *IELTS_SECTIONS):
            value = attrs.get(name)
            if value is not None and value * 2 % 1:
                errors[name] = HALF_BAND
        if attrs.get('ielts_score') is None:
            errors['ielts_score'] = 'Enter your overall band score.'
        sections = [attrs.get(name) for name in IELTS_SECTIONS]
        given = [value is not None for value in sections]
        if any(given) and not all(given):
            for name, present in zip(IELTS_SECTIONS, given):
                if not present:
                    errors[name] = 'Enter all four section scores, or leave all four empty.'
        elif all(given) and not errors.keys() & {'ielts_score', *IELTS_SECTIONS}:
            overall = ielts_overall(sections)
            if overall != attrs['ielts_score']:
                errors['ielts_score'] = f'With these section scores your overall band is {overall:g}. Check your test report.'
        self._check_date(attrs, errors, 'ielts_test_date', status)
        self._check_attempts(attrs, errors, 'ielts_attempts')

    def _validate_sat(self, attrs, errors):
        status = attrs.setdefault('sat_status', 'taken' if attrs.get('sat_reading') or attrs.get('sat_math') else 'not_taken')
        if status != 'taken':
            test_date = attrs.get('sat_test_date') if status in ('planning', 'scheduled') else None
            attrs.update({name: None for name in SAT_FIELDS if name != 'sat_status'}, sat_test_date=test_date)
            if status in ('planning', 'scheduled'):
                self._check_date(attrs, errors, 'sat_test_date', status)
            return
        sections = ('sat_reading', 'sat_math', 'sat_superscore_reading', 'sat_superscore_math')
        for name in sections:
            if attrs.get(name) is not None and attrs[name] % 10:
                errors[name] = SAT_STEP
        for name in ('sat_reading', 'sat_math'):
            if attrs.get(name) is None:
                errors[name] = 'Enter this section score.'
        self._check_date(attrs, errors, 'sat_test_date', status)
        self._check_attempts(attrs, errors, 'sat_attempts')
        if attrs['sat_attempts'] < 2:
            # A superscore combines several test days; with one there is nothing to combine.
            attrs.update(sat_superscore=None, sat_superscore_reading=None, sat_superscore_math=None)
        elif attrs.get('sat_superscore') is None:
            errors['sat_superscore'] = 'Choose Yes or No.'
        elif not attrs['sat_superscore']:
            attrs.update(sat_superscore_reading=None, sat_superscore_math=None)
        else:
            for best, day in (('sat_superscore_reading', 'sat_reading'), ('sat_superscore_math', 'sat_math')):
                if attrs.get(best) is None:
                    errors.setdefault(best, 'Enter your highest score for this section.')
                elif attrs.get(day) is not None and attrs[best] < attrs[day]:
                    errors.setdefault(best, 'Your highest score cannot be lower than your best test day score.')
        if not errors.keys() & set(SAT_FIELDS):
            attrs['sat_score'] = sat_sent_total(
                attrs['sat_reading'], attrs['sat_math'], attrs.get('sat_superscore'),
                attrs.get('sat_superscore_reading'), attrs.get('sat_superscore_math'),
            )


# Profile readiness: the answers a counselor needs to plan with, in the order
# the hint suggests them. (key, section, done?)
PROFILE_READINESS_ITEMS = (
    ('photo', 'personal', lambda profile, answers: bool(profile.photo)),
    ('graduation_year', 'personal', lambda profile, answers: bool(answers.get('graduation_year'))),
    ('guardian', 'personal', lambda profile, answers: bool(profile.guardian_name and profile.parent_contact)),
    ('school', 'academics', lambda profile, answers: bool(profile.school_name and answers.get('country') and answers.get('city'))),
    ('gpa', 'academics', lambda profile, answers: profile.gpa is not None),
    ('ielts', 'tests', lambda profile, answers: profile.ielts_status != 'not_taken'),
    ('sat', 'tests', lambda profile, answers: profile.sat_status != 'not_taken'),
    ('countries', 'goal', lambda profile, answers: bool(profile.target_countries)),
    ('interests', 'goal', lambda profile, answers: bool(answers.get('interests'))),
    ('story', 'goal', lambda profile, answers: bool((answers.get('personal_story') or '').strip())),
    ('activities', 'activities', lambda profile, answers: bool(answers.get('activities'))),
    ('honors', 'honors', lambda profile, answers: bool(answers.get('honors'))),
)


def profile_readiness(profile):
    """Share of readiness items answered, plus the missing ones; reads only the profile row."""
    answers = profile.application_profile or {}
    missing = [
        {'key': key, 'section': section}
        for key, section, done in PROFILE_READINESS_ITEMS
        if not done(profile, answers)
    ]
    total = len(PROFILE_READINESS_ITEMS)
    return {'percent': percent(total - len(missing), total), 'missing': missing}
