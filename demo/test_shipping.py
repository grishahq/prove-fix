from shipping import free_shipping


def test_weak():
    assert free_shipping(150) is True


def test_boundary():
    assert free_shipping(100) is True
