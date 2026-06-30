from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from .models import Address
from .forms import AddressForm


@login_required
def address_list(request):

    addresses = Address.objects.filter(
        user=request.user
    ).order_by("-is_default", "-created_at")

    return render(
        request,
        "addresses/address_list.html",
        {
            "addresses": addresses
        }
    )


@login_required
def add_address(request):
    print(request.method)
    if request.method == "POST":

        form = AddressForm(request.POST)

        if form.is_valid():

            print("FORM IS VALID")

            address = form.save(commit=False)

            address.user = request.user

            if not request.user.addresses.exists():
                address.is_default = True

            address.save()

            print("ADDRESS SAVED:", address.id)

            messages.success(
                request,
                "Address added successfully."
            )

            return redirect("addresses:address_list")

        else:

            print("FORM ERRORS:")
            print(form.errors)

    else:

        form = AddressForm()

    return render(
        request,
        "addresses/address_form.html",
        {
            "form": form,
            "title": "Add Address"
        }
    )


@login_required
def edit_address(request, pk):

    address = get_object_or_404(
        Address,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        form = AddressForm(
            request.POST,
            instance=address
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Address updated."
            )

            return redirect(
                "addresses:address_list"
            )

    else:

        form = AddressForm(instance=address)

    return render(
        request,
        "addresses/address_form.html",
        {
            "form": form,
            "title": "Edit Address"
        }
    )


@login_required
def delete_address(request, pk):

    address = get_object_or_404(
        Address,
        pk=pk,
        user=request.user
    )

    address.delete()

    messages.success(
        request,
        "Address deleted."
    )

    return redirect(
        "addresses:address_list"
    )


@login_required
def set_default(request, pk):

    address = get_object_or_404(
        Address,
        pk=pk,
        user=request.user
    )

    Address.objects.filter(
        user=request.user
    ).update(
        is_default=False
    )

    address.is_default = True

    address.save()

    return redirect(
        "addresses:address_list"
    )