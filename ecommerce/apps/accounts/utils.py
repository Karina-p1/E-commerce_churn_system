def get_device_type(request) -> str:
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    if any(x in ua for x in ['iphone', 'android', 'mobile']):
        return 'Mobile Phone'
    elif any(x in ua for x in ['tablet', 'ipad']):
        return 'Mobile Phone'
    else:
        return 'Computer'


def update_device_info(user, request) -> None:
    """
    Updates preferred login device and counts unique device types used.
    Called on every login.
    """
    device = get_device_type(request)
    user.preferred_login_device = device

    # We only have two device types — track if user has used both
    if device == 'Mobile Phone':
        user._seen_mobile = True
    else:
        user._seen_computer = True

    # Count unique device types seen across all logins
    # Max 2 since we only distinguish Mobile Phone vs Computer
    devices_used = set()
    if device == 'Mobile Phone':
        devices_used.add('Mobile Phone')
        # If they previously logged in from computer, count that too
        if user.number_of_devices > 1:
            devices_used.add('Computer')
    else:
        devices_used.add('Computer')
        if user.number_of_devices > 1:
            devices_used.add('Mobile Phone')

    # If switching device type from what we have stored, increment
    if user.preferred_login_device != device:
        user.number_of_devices = min(2, user.number_of_devices + 1)

    user.save(update_fields=['preferred_login_device', 'number_of_devices'])