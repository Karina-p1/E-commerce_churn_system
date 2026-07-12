from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Notification


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')

    filter_type = request.GET.get('filter')
    if filter_type == 'unread':
        notifications = notifications.filter(is_read=False)

    return render(request, 'notifications/list.html', {
        'notifications': notifications,
        'filter_type': filter_type,
    })


@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user
    )
    notification.is_read = True
    notification.save(update_fields=['is_read'])

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    return redirect('notifications:list')


@login_required
def mark_all_read(request):
    Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).update(is_read=True)
    return redirect('notifications:list')


@login_required
def poll_notifications(request):
    """
    Lightweight JSON endpoint polled every ~20s from base.html.
    Returns the current unread count plus the single newest notification
    (id/title/message) so the client can detect "is this new since I last
    checked" and pop a toast without a full page reload.
    """
    unread_count = request.user.notifications.filter(is_read=False).count()
    latest_qs = request.user.notifications.order_by('-created_at')[:1]

    latest = None
    if latest_qs:
        n = latest_qs[0]
        latest = {
            'id': n.id,
            'title': n.title,
            'message': n.message,
        }

    return JsonResponse({
        'unread_count': unread_count,
        'latest': latest,
    })