"""Input validation and response shapes for the student Essay Lab API."""

from rest_framework import serializers

from ..models import Essay, EssayCheckpoint, EssayDepthCheck, EssayFolder, EssayTab
from .doc import BID_PATTERN, tab_doc
from .tabs import MAX_TAB_TITLE

SUMMARY_FIELDS = (
    'id', 'title', 'essay_type', 'prompt', 'university_name', 'word_limit', 'folder',
    'word_count', 'preview', 'last_edited_at', 'updated_at', 'trashed_at', 'status', 'page_size',
    'shared_with_counselor', 'shared_at', 'counselor_access',
)
MAX_WORD_LIMIT = 20000


class EssaySummarySerializer(serializers.ModelSerializer):
    folder = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Essay
        fields = SUMMARY_FIELDS
        read_only_fields = SUMMARY_FIELDS


TAB_META_FIELDS = (
    'id', 'parent', 'title', 'position', 'word_count', 'char_count', 'char_count_no_spaces', 'save_seq',
    'last_edited_at',
)


class TabMetaSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = EssayTab
        fields = TAB_META_FIELDS
        read_only_fields = fields


class TabDetailSerializer(TabMetaSerializer):
    doc = serializers.SerializerMethodField()

    class Meta(TabMetaSerializer.Meta):
        fields = TAB_META_FIELDS + ('doc', 'last_cursor')
        read_only_fields = fields

    def get_doc(self, obj) -> dict:
        return tab_doc(obj)


class EssayDetailSerializer(EssaySummarySerializer):
    """The document: its metadata, every tab's metadata in reading order, and
    the open tab with its doc (`context['tabs']`, `context['tab']`). Other tabs'
    docs load when they are opened."""

    tabs = serializers.SerializerMethodField()
    tab = serializers.SerializerMethodField()

    class Meta(EssaySummarySerializer.Meta):
        fields = SUMMARY_FIELDS + ('tabs', 'tab')
        read_only_fields = fields

    def get_tabs(self, obj) -> list:
        return TabMetaSerializer(self.context.get('tabs', ()), many=True).data

    def get_tab(self, obj) -> dict | None:
        tab = self.context.get('tab')
        return TabDetailSerializer(tab).data if tab is not None else None


class StudentFolderField(serializers.PrimaryKeyRelatedField):
    """A folder id that must belong to the requesting student (404-safe: others look missing)."""

    def get_queryset(self):
        student_id = self.context['student_id']
        return EssayFolder.objects.filter(student_id=student_id)


class EssayMetadataSerializer(serializers.Serializer):
    """Create and PATCH body. The essay text itself only moves through autosave."""

    title = serializers.CharField(max_length=220, required=False, allow_blank=True, trim_whitespace=True)
    essay_type = serializers.ChoiceField(choices=Essay.EssayType.choices, required=False)
    prompt = serializers.CharField(max_length=5000, required=False, allow_blank=True, trim_whitespace=True)
    university_name = serializers.CharField(max_length=220, required=False, allow_blank=True, trim_whitespace=True)
    word_limit = serializers.IntegerField(min_value=1, max_value=MAX_WORD_LIMIT, required=False, allow_null=True)
    folder = StudentFolderField(required=False, allow_null=True)
    page_size = serializers.ChoiceField(choices=Essay.PageSize.choices, required=False)
    # Create only: the first tab's name in the student's language.
    first_tab_title = serializers.CharField(max_length=MAX_TAB_TITLE, required=False, allow_blank=True,
                                            trim_whitespace=True)


class EssayDuplicateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=220, required=False, allow_blank=True, trim_whitespace=True)
    university_name = serializers.CharField(max_length=220, required=False, allow_blank=True, trim_whitespace=True)
    folder = StudentFolderField(required=False, allow_null=True)


MAX_DELTA_OPS = 1000


def _is_index(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000


def _clean_op(op):
    """Shape check only; whether an op fits the stored doc is decided under the row lock."""
    if not isinstance(op, dict) or not _is_index(op.get('at')):
        raise serializers.ValidationError('Every op needs an "at" index.')
    if set(op) == {'at', 'patch'}:
        patch = op['patch']
        if (not isinstance(patch, list) or len(patch) != 3 or not _is_index(patch[0]) or not _is_index(patch[1])
                or not isinstance(patch[2], str)):
            raise serializers.ValidationError('A patch is [prefix, suffix, text].')
        return {'at': op['at'], 'patch': patch}
    if set(op) == {'at', 'delete', 'insert'}:
        if not _is_index(op['delete']) or not isinstance(op['insert'], list):
            raise serializers.ValidationError('A splice needs a "delete" count and an "insert" list.')
        return {'at': op['at'], 'delete': op['delete'], 'insert': op['insert']}
    raise serializers.ValidationError('Unknown op.')


HASH = r'^[0-9a-f]{64}$'


def _is_bid(value):
    return isinstance(value, str) and BID_PATTERN.fullmatch(value) is not None


def _is_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(char in '0123456789abcdef' for char in value)


def _clean_op_v2(op):
    """Shape check of an id-addressed op (see doc.apply_ops_v2)."""
    if not isinstance(op, dict):
        raise serializers.ValidationError('Every op must be an object.')
    keys = set(op)
    if keys == {'del', 'base'} and _is_bid(op['del']) and _is_hash(op['base']):
        return {'del': op['del'], 'base': op['base']}
    if keys == {'set', 'base', 'block'} and _is_bid(op['set']) and _is_hash(op['base']) and isinstance(op['block'], dict):
        return {'set': op['set'], 'base': op['base'], 'block': op['block']}
    if keys == {'ins', 'after'} and isinstance(op['ins'], dict) and (op['after'] is None or _is_bid(op['after'])):
        return {'ins': op['ins'], 'after': op['after']}
    raise serializers.ValidationError('Unknown op.')


class AutosaveSerializer(serializers.Serializer):
    """The whole `doc`; or `ops` (v1: by block index) or `ops_v2` (by block id)
    over the saved doc's top-level blocks, plus the sha256 (`doc_hash`) of the
    resulting doc in canonical JSON.

    v1 needs the saved version (`base_seq`) to be the latest. v2 may start
    from an older one: changes to other paragraphs are merged."""

    doc = serializers.JSONField(required=False)
    ops = serializers.JSONField(required=False)
    ops_v2 = serializers.JSONField(required=False)
    doc_hash = serializers.RegexField(r'^[0-9a-f]{64}$', required=False)
    base_seq = serializers.IntegerField(min_value=0)
    # Optional only for one-tab documents (older clients); see resolve_tab().
    tab = serializers.IntegerField(min_value=1, required=False)
    client_save_id = serializers.RegexField(r'^[A-Za-z0-9._:-]{1,64}$', max_length=64)
    cursor = serializers.IntegerField(min_value=0, max_value=10_000_000, required=False, allow_null=True)

    def validate_ops(self, value):
        if not isinstance(value, list) or len(value) > MAX_DELTA_OPS:
            raise serializers.ValidationError(f'ops must be a list of at most {MAX_DELTA_OPS} edits.')
        return [_clean_op(op) for op in value]

    def validate_ops_v2(self, value):
        if not isinstance(value, list) or len(value) > MAX_DELTA_OPS:
            raise serializers.ValidationError(f'ops must be a list of at most {MAX_DELTA_OPS} edits.')
        return [_clean_op_v2(op) for op in value]

    def validate(self, attrs):
        if sum(key in attrs for key in ('doc', 'ops', 'ops_v2')) != 1:
            raise serializers.ValidationError({'doc': 'Send either the whole doc or ops.'})
        if ('ops' in attrs or 'ops_v2' in attrs) and 'doc_hash' not in attrs:
            raise serializers.ValidationError({'doc_hash': 'ops need the hash of the resulting doc.'})
        return attrs


class BaseSeqSerializer(serializers.Serializer):
    base_seq = serializers.IntegerField(min_value=0)
    tab = serializers.IntegerField(min_value=1, required=False)


class CheckpointCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    tab = serializers.IntegerField(min_value=1, required=False)


class TabQuerySerializer(serializers.Serializer):
    tab = serializers.IntegerField(min_value=1, required=False)


class TabCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=MAX_TAB_TITLE, required=False, allow_blank=True, trim_whitespace=True)
    # A sub-tab of this (top-level) tab; ids are checked against the essay in the view.
    parent = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class TabRenameSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=MAX_TAB_TITLE, trim_whitespace=True)


class TabOrderSerializer(serializers.Serializer):
    parent = serializers.IntegerField(min_value=1, allow_null=True)
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=200)


def person_name(user):
    if user is None:
        return None
    return user.get_full_name() or user.username


class CheckpointSummarySerializer(serializers.ModelSerializer):
    # Who made the version: null for the student's own older versions.
    author_name = serializers.SerializerMethodField()
    by_me = serializers.SerializerMethodField()

    class Meta:
        model = EssayCheckpoint
        fields = ('id', 'tab', 'reason', 'label', 'word_count', 'created_at', 'kind', 'detail', 'author_name', 'by_me')
        read_only_fields = fields

    def get_author_name(self, obj) -> str | None:
        return person_name(obj.author) if obj.author_id else None

    def get_by_me(self, obj) -> bool:
        viewer = self.context.get('viewer_id')
        return obj.author_id is None or obj.author_id == viewer


class CheckpointDetailSerializer(CheckpointSummarySerializer):
    class Meta(CheckpointSummarySerializer.Meta):
        fields = CheckpointSummarySerializer.Meta.fields + ('doc',)
        read_only_fields = fields


class DepthCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = EssayDepthCheck
        fields = ('id', 'tab', 'save_seq', 'created_at', 'model', 'result')
        read_only_fields = fields


class FolderSerializer(serializers.ModelSerializer):
    essay_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = EssayFolder
        fields = ('id', 'name', 'parent', 'position', 'essay_count')
        read_only_fields = ('id', 'parent', 'position', 'essay_count')


class FolderWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, trim_whitespace=True)
    parent = StudentFolderField(required=False, allow_null=True)


class FolderOrderSerializer(serializers.Serializer):
    parent = StudentFolderField(allow_null=True)
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=500)


class ShareSerializer(serializers.Serializer):
    access = serializers.ChoiceField(choices=Essay.CounselorAccess.choices, required=False)


class ChangesQuerySerializer(serializers.Serializer):
    tab = serializers.IntegerField(min_value=1)
    # The save_seq the client already shows; the doc is sent only when it differs.
    since = serializers.IntegerField(min_value=0, required=False)


class CommentBodySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000, trim_whitespace=True)


class DecisionSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    accept = serializers.BooleanField()


class DecideSerializer(serializers.Serializer):
    tab = serializers.IntegerField(min_value=1)
    decisions = DecisionSerializer(many=True, allow_empty=False, max_length=200)

    def validate_decisions(self, value):
        ids = [item['id'] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('Decide each suggestion once.')
        return value


class BidField(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(BID_PATTERN.pattern, max_length=32, **kwargs)


class ThreadCreateSerializer(serializers.Serializer):
    tab = serializers.IntegerField(min_value=1)
    bid = BidField()
    start = serializers.IntegerField(min_value=0)
    end = serializers.IntegerField(min_value=1)
    body = serializers.CharField(max_length=2000, trim_whitespace=True)


class SuggestionItemSerializer(serializers.Serializer):
    bid = BidField()
    start = serializers.IntegerField(min_value=0)
    end = serializers.IntegerField(min_value=0)
    # Text to put after the range (empty: only delete the range).
    text = serializers.CharField(max_length=2000, required=False, allow_blank=True, trim_whitespace=False, default='')

    def validate(self, attrs):
        if attrs['end'] < attrs['start']:
            raise serializers.ValidationError('The range ends before it starts.')
        if attrs['end'] == attrs['start'] and not attrs['text']:
            raise serializers.ValidationError('Suggest new text, a deletion, or both.')
        return attrs


class SuggestionCreateSerializer(serializers.Serializer):
    tab = serializers.IntegerField(min_value=1)
    items = SuggestionItemSerializer(many=True, allow_empty=False, max_length=50)
