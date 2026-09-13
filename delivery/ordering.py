# Purpose: Order task lists by the trailing global sequence code of a task number (AOP067-1395-AB759 -> AB759).
# Used by: every delivery-task list screen — driver PWA tabs, staff Delivery Tasks / follow-up / sheets, client task and charge ledgers, exports.
# Notes: The sequence is fixed-width (2 letters + 3 digits) so plain string ordering is chronological; rows with no dash sort on the whole number.

from django.db.models import CharField, F, Func, Value

__all__ = ['TaskSequenceCode', 'annotate_task_sequence', 'TASK_SEQ_DESC', 'TASK_SEQ_ASC']

# The annotation name every list view uses, so templates and further ordering
# can reference it without each caller inventing its own alias.
TASK_SEQ_FIELD = 'task_seq'
TASK_SEQ_DESC = (f'-{TASK_SEQ_FIELD}', '-id')
TASK_SEQ_ASC = (TASK_SEQ_FIELD, 'id')


class TaskSequenceCode(Func):
    """Strip everything up to the last dash: AOP067-1395-AB759 -> AB759.

    The business code leads the task number, so ordering on the raw
    `dl_task_number` groups by client instead of by when the job was issued.
    """

    function = 'regexp_replace'
    output_field = CharField()

    def __init__(self, field='dl_task_number', **extra):
        super().__init__(
            F(field) if isinstance(field, str) else field,
            Value('^.*-'),
            Value(''),
            **extra,
        )


def annotate_task_sequence(queryset, field='dl_task_number'):
    """Add the `task_seq` annotation used by TASK_SEQ_DESC / TASK_SEQ_ASC."""
    return queryset.annotate(**{TASK_SEQ_FIELD: TaskSequenceCode(field)})


def order_by_task_sequence(queryset, descending=True, field='dl_task_number'):
    """Annotate + order a task queryset newest-code-first (the default)."""
    ordering = TASK_SEQ_DESC if descending else TASK_SEQ_ASC
    return annotate_task_sequence(queryset, field).order_by(*ordering)
