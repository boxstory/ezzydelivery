# Purpose: Tests for task-list ordering by the trailing sequence code of dl_task_number.
# Used by: python manage.py test delivery.tests_ordering
# Notes: The sequence is the last dash-segment (AOP067-1395-AB759 -> AB759) and is global, so it orders every client's tasks on one timeline.

from django.test import TestCase

from django.contrib.auth import get_user_model

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from orders import models as orders_models
from delivery.ordering import (
    TASK_SEQ_ASC,
    TASK_SEQ_DESC,
    annotate_task_sequence,
    order_by_task_sequence,
)

DeliveryTask = delivery_models.DeliveryTask
User = get_user_model()


class TaskSequenceOrderingTests(TestCase):
    """The raw dl_task_number leads with the business code, so ordering on it
    groups by client. These assert we order on the trailing sequence instead."""

    NUMBERS = [
        'ZZZ999-1000-AA001',   # last alphabetically, first sequence issued
        'AAA001-2000-AB760',   # first alphabetically, last sequence issued
        'MMM500-3000-AA999',
        'MMM500-3001-AB000',
    ]

    def setUp(self):
        owner = User.objects.create_user(username='seqbiz', password='x')
        profile = core_models.Profile.objects.create(
            user=owner, first_name='Seq', last_name='Biz', phone=77777777)
        self.business = business_models.Business.objects.create(
            business_id=910, user=owner, profile=profile,
            business_name='Sequence Biz', business_code='SEQ001',
            business_status='active',
        )
        for idx, number in enumerate(self.NUMBERS):
            self.make_task(number, idx)

    def make_task(self, number, idx):
        order = orders_models.Order.objects.create(
            business=self.business, order_number=number,
            client_order_code=f'SEQ{idx}', customer_name=f'Customer {idx}',
        )
        return DeliveryTask.objects.create(
            order=order, business=self.business,
            dl_task_number=number, dl_task_description=f'Task {idx}',
        )

    def sequences(self, queryset):
        return list(queryset.values_list('task_seq', flat=True))

    def test_annotation_extracts_trailing_segment(self):
        rows = dict(
            annotate_task_sequence(DeliveryTask.objects.all())
            .values_list('dl_task_number', 'task_seq')
        )
        self.assertEqual(rows['ZZZ999-1000-AA001'], 'AA001')
        self.assertEqual(rows['AAA001-2000-AB760'], 'AB760')

    def test_descending_is_newest_sequence_first(self):
        self.assertEqual(
            self.sequences(order_by_task_sequence(DeliveryTask.objects.all())),
            ['AB760', 'AB000', 'AA999', 'AA001'],
        )

    def test_ascending_is_oldest_sequence_first(self):
        self.assertEqual(
            self.sequences(order_by_task_sequence(DeliveryTask.objects.all(), descending=False)),
            ['AA001', 'AA999', 'AB000', 'AB760'],
        )

    def test_group_rollover_beats_plain_string_order(self):
        """AB000 follows AA999 — the letter pair carries the thousands, so the
        sequence still reads chronologically across a rollover."""
        ordered = self.sequences(order_by_task_sequence(DeliveryTask.objects.all(), descending=False))
        self.assertLess(ordered.index('AA999'), ordered.index('AB000'))

    def test_ordering_ignores_the_business_code(self):
        """Alphabetically ZZZ999 sorts last but it holds the FIRST sequence, so
        ordering on the raw number would put it in the opposite place."""
        by_seq = list(
            order_by_task_sequence(DeliveryTask.objects.all())
            .values_list('dl_task_number', flat=True)
        )
        by_raw = list(
            DeliveryTask.objects.order_by('-dl_task_number')
            .values_list('dl_task_number', flat=True)
        )
        self.assertEqual(by_seq[0], 'AAA001-2000-AB760')
        self.assertEqual(by_raw[0], 'ZZZ999-1000-AA001')

    def test_number_without_a_dash_falls_back_to_the_whole_value(self):
        self.make_task('NODASH', 99)
        rows = dict(
            annotate_task_sequence(DeliveryTask.objects.all())
            .values_list('dl_task_number', 'task_seq')
        )
        self.assertEqual(rows['NODASH'], 'NODASH')

    def test_order_constants_are_usable_directly(self):
        qs = annotate_task_sequence(DeliveryTask.objects.all())
        self.assertEqual(
            self.sequences(qs.order_by(*TASK_SEQ_DESC)),
            list(reversed(self.sequences(qs.order_by(*TASK_SEQ_ASC)))),
        )
