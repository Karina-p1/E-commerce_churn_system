def unread_notification_count(request):
    """
    Available in every template as:
      {{ unread_notification_count }}  -> int, for the badge
      {{ recent_notifications }}       -> queryset of the 5 latest, for the dropdown
    """
    if request.user.is_authenticated:
        notifications = request.user.notifications.all()
        return {
            'unread_notification_count': notifications.filter(is_read=False).count(),
            'recent_notifications': notifications[:5],
        }
    return {'unread_notification_count': 0, 'recent_notifications': []}