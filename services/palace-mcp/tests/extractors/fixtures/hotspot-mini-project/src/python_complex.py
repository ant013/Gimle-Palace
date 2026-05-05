def classify(n):
    if n < 0:
        return "neg"
    elif n == 0:
        return "zero"
    elif n < 10:
        return "small"
    elif n < 100:
        return "medium"
    else:
        if n < 1000:
            return "large"
        return "huge"



