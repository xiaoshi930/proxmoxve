def to_pecent(value, ndigits = 2):
    if value is None:
        return None
    pecent = round(value * 100, 2)
    if pecent < 0:
        return 0
    if pecent > 100:
        return 100
    return pecent