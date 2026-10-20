import numpy as np

def test_basic():
    assert 1 + 1 == 2


def test_dependency():
    arr = np.array([1, 2, 3])
    assert arr.sum() == 6
