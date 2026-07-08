

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0011_merge_0009_refundrequest_0010_order_refund_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='payment_status',
            field=models.CharField(choices=[('UNPAID', 'Unpaid'), ('INITIATED', 'Payment Initiated'), ('PAID', 'Paid'), ('FAILED', 'Failed'), ('REFUND_PENDING', 'Refund Requested'), ('REFUNDED', 'Refunded')], default='UNPAID', max_length=20),
        ),
    ]
