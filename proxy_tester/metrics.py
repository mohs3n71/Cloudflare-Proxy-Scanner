FAILED_METRIC = -1


def normalize_failed_metric(value):
    if value in (None, ""):
        return value
    try:
        if float(value) == FAILED_METRIC:
            return FAILED_METRIC
    except (TypeError, ValueError):
        pass
    return value
