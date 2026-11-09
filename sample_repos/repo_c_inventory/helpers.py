def calculate_reorder_point(avg_daily_usage, lead_time_days, safety_stock):
    return (avg_daily_usage * lead_time_days) + safety_stock


def format_sku(prefix, number):
    return f"{prefix}-{number:05d}"
