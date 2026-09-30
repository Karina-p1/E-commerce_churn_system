import logging
# adjust import path to match your project
from apps.notifications.models import Notification
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from apps.orders.models import Order
from .forms import ComplaintFeedbackForm, ComplaintForm
from .models import Complaint
from django.core.paginator import Paginator
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Q, Case, When, Value, IntegerField


logger = logging.getLogger(__name__)


@login_required
def complaint_list(request):
    complaints = Complaint.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return render(
        request,
        "complaints/complaint_list.html",
        {
            "complaints": complaints
        }
    )


@login_required
def complaint_create(request):

    if request.method == "POST":

        form = ComplaintForm(request.POST, request.FILES)

        form.fields["order"].queryset = Order.objects.filter(
            user=request.user
        )

        if form.is_valid():

            complaint = form.save(commit=False)
            complaint.user = request.user

            # --------------------------------------------------
            # LOYALTY TIER SUPPORT PRIORITY
            # --------------------------------------------------
            # Customers do not choose complaint priority themselves.
            # Their current loyalty tier determines the initial priority.
            #
            # Loyalty support priority -> Complaint priority:
            # NORMAL -> MEDIUM
            # HIGH   -> HIGH
            # URGENT -> URGENT
            loyalty_account = getattr(request.user, "loyalty_account", None)
            current_tier = (
                loyalty_account.current_tier
                if loyalty_account
                else None
            )

            if current_tier:
                priority_map = {
                    "NORMAL": "MEDIUM",
                    "HIGH": "HIGH",
                    "URGENT": "URGENT",
                }

                complaint.priority = priority_map.get(
                    current_tier.support_priority,
                    "MEDIUM",
                )
            else:
                complaint.priority = "MEDIUM"

            complaint.save()

            messages.success(
                request,
                "Complaint submitted successfully."
            )

            return redirect("complaints:list")

    else:

        form = ComplaintForm()

        form.fields["order"].queryset = Order.objects.filter(
            user=request.user
        )

    return render(
        request,
        "complaints/complaint_form.html",
        {
            "form": form
        }
    )


@login_required
def complaint_detail(request, pk):

    complaint = get_object_or_404(
        Complaint,
        pk=pk,
        user=request.user
    )

    return render(
        request,
        "complaints/complaint_detail.html",
        {
            "complaint": complaint
        }
    )


@login_required
def complaint_edit(request, pk):

    complaint = get_object_or_404(
        Complaint,
        pk=pk,
        user=request.user
    )

    if complaint.status != "PENDING":

        messages.warning(
            request,
            "You cannot edit this complaint."
        )

        return redirect("complaints:detail", pk=pk)

    if request.method == "POST":

        form = ComplaintForm(
            request.POST,
            request.FILES,
            instance=complaint
        )

        form.fields["order"].queryset = Order.objects.filter(
            user=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Complaint updated successfully."
            )

            return redirect(
                "complaints:detail",
                pk=pk
            )

    else:

        form = ComplaintForm(instance=complaint)

        form.fields["order"].queryset = Order.objects.filter(
            user=request.user
        )

    return render(
        request,
        "complaints/complaint_form.html",
        {
            "form": form,
            "edit": True
        }
    )


@login_required
def complaint_feedback(request, pk):

    complaint = get_object_or_404(
        Complaint,
        pk=pk,
        user=request.user,
        status="RESOLVED"
    )

    if request.method == "POST":

        form = ComplaintFeedbackForm(
            request.POST,
            instance=complaint
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Thank you for your feedback."
            )

            return redirect(
                "complaints:detail",
                pk=pk
            )

    else:

        form = ComplaintFeedbackForm(instance=complaint)

    return render(
        request,
        "complaints/feedback_form.html",
        {
            "form": form,
            "complaint": complaint
        }
    )


@staff_member_required
def complaint_list_admin(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', 'all')
    priority = request.GET.get('priority', 'all')

    complaints = Complaint.objects.select_related('user', 'order').all()

    if query:
        complaints = complaints.filter(
            Q(subject__icontains=query) |
            Q(description__icontains=query) |
            Q(user__username__icontains=query) |
            Q(user__email__icontains=query) |
            Q(order__id__icontains=query)
        )

    if status != 'all':
        complaints = complaints.filter(status=status.upper())

    if priority != 'all':
        complaints = complaints.filter(priority=priority.upper())

    # Loyalty-backed support priority comes first in the staff queue.
    # Newest complaints are shown first within the same priority.
    complaints = complaints.annotate(
        priority_rank=Case(
            When(priority="URGENT", then=Value(4)),
            When(priority="HIGH", then=Value(3)),
            When(priority="MEDIUM", then=Value(2)),
            When(priority="LOW", then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by("-priority_rank", "-created_at")

    paginator = Paginator(complaints, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'priority': priority,
        'now': timezone.now(),
        'pending_count': Complaint.objects.filter(status='PENDING').count(),
        'in_progress_count': Complaint.objects.filter(status='IN_PROGRESS').count(),
        'resolved_count': Complaint.objects.filter(status='RESOLVED').count(),
    }
    return render(request, 'admin/manage_complaints.html', context)


@staff_member_required
def complaint_detail_admin(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)

    if request.method == 'POST':
        old_status = complaint.status

        complaint.status = request.POST.get(
            'status',
            complaint.status
        )

        complaint.priority = request.POST.get(
            'priority',
            complaint.priority
        )

        complaint.admin_reply = request.POST.get(
            'admin_reply',
            complaint.admin_reply
        ).strip()

        if complaint.status == 'RESOLVED' and complaint.resolved_at is None:
            complaint.resolved_at = timezone.now()

        complaint.save()

        # --------------------------------------------------
        # IMMEDIATE CHURN RE-SCORE
        # --------------------------------------------------
        # Only re-score when the complaint status actually changed.
        # This makes the churn dashboard reflect complaint changes
        # immediately instead of waiting for the daily Celery run or
        # the manual "Refresh scores" action.
        if old_status != complaint.status:
            try:
                # Local import avoids an unnecessary import cycle while
                # the complaints app is loading.
                from apps.churn.services import score_customer

                churn_outcome = score_customer(
                    complaint.user,
                    debug=False,
                )

                result = churn_outcome['result']

                logger.info(
                    "Complaint #%s changed %s -> %s. "
                    "Customer %s re-scored: %s (%.3f)",
                    complaint.id,
                    old_status,
                    complaint.status,
                    complaint.user.username,
                    result['risk_level'],
                    result['score'],
                )

            except Exception:
                # The complaint update should still succeed even if churn
                # scoring temporarily fails. Log the traceback so the
                # scoring problem can be diagnosed separately.
                logger.exception(
                    "Failed to re-score customer %s after "
                    "complaint #%s status change.",
                    complaint.user_id,
                    complaint.id,
                )

        messages.success(
            request,
            f"Complaint #{complaint.id} updated successfully."
        )

        return redirect(
            'complaints:complaint_detail',
            pk=complaint.pk
        )

    return render(
        request,
        'admin/complaint_detail.html',
        {
            'complaint': complaint
        }
    )

@staff_member_required
def complaint_delete_confirm(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)
    if request.method == 'POST':
        complaint.delete()
        messages.success(request, "Complaint deleted successfully.")
        return redirect('complaints:complaint_list')
    return render(request, 'admin/complaint_delete_confirm.html', {'complaint': complaint})
