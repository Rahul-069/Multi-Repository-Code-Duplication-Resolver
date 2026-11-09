import re


def validate_email(email):
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not email:
        return False
    if not re.match(pattern, email):
        return False
    return True


def validate_amount(amount):
    if amount is None:
        return False
    if amount <= 0:
        return False
    return True
