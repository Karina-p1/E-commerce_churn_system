from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from apps.orders.models import Order
from .forms import ComplaintFeedbackForm, ComplaintForm
from .models import Complaint


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