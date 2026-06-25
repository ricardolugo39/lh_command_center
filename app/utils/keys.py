import hashlib


def build_customer_site_id(
    nit: str,
    city: str,
    address: str,
) -> str:

    key = f"{nit}|{city}|{address}"

    return hashlib.md5(
        key.encode("utf-8")
    ).hexdigest()