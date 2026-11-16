def detection_priority(customer_importance: int, signature_priority: int) -> int:
    """
    Detection priority = customer importance (1-5) x signature priority (1-5), giving 1-25.
    A product (not a sum) makes "critical customer + critical signature" (25) stand far above
    the middle of the range, while either factor at 1 keeps the detection low.
    """
    return customer_importance * signature_priority
