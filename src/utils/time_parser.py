def parse_time(time_str: str) -> int:
    """
    Converts a time string in format SS, MM:SS, or HH:MM:SS to seconds.
    If parsing fails, returns None.
    """
    try:
        parts = time_str.split(':')
        if len(parts) == 1:
            return int(parts[0])
        elif len(parts) == 2:
            m, s = map(int, parts)
            return m * 60 + s
        elif len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        return None
    except ValueError:
        return None
