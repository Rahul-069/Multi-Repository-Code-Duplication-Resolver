import re


def is_valid_email(address):
    rule = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not address:
        return False
    if not re.match(rule, address):
        return False
    return True


def validate_shipping_address(address, zip_code):
    if not address or not zip_code:
        return False
    return len(zip_code) == 5
