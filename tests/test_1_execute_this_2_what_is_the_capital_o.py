import pytest


def add_numbers(a: int | float, b: int | float) -> int | float:
    """Sum two numbers and return the result."""
    return a + b


class TestAddNumbers:
    """Test suite for add_numbers function."""

    def test_add_two_positive_integers(self):
        """Happy path: sum of two positive integers."""
        assert add_numbers(2, 3) == 5
        assert add_numbers(10, 20) == 30

    def test_add_two_positive_floats(self):
        """Happy path: sum of two positive floats."""
        assert add_numbers(2.5, 3.5) == 6.0
        assert add_numbers(0.1, 0.2) == pytest.approx(0.3)

    def test_add_negative_numbers(self):
        """Edge case: sum with negative numbers."""
        assert add_numbers(-5, 3) == -2
        assert add_numbers(-10, -20) == -30
        assert add_numbers(10, -10) == 0

    def test_add_zero(self):
        """Edge case: adding zero."""
        assert add_numbers(0, 5) == 5
        assert add_numbers(5, 0) == 5
        assert add_numbers(0, 0) == 0

    def test_add_mixed_int_and_float(self):
        """Edge case: mixed int and float operands."""
        assert add_numbers(5, 2.5) == 7.5
        assert add_numbers(2.5, 5) == 7.5

    def test_add_invalid_type_string(self):
        """Error condition: invalid type (string)."""
        with pytest.raises(TypeError):
            add_numbers("5", 3)

    def test_add_invalid_type_none(self):
        """Error condition: invalid type (None)."""
        with pytest.raises(TypeError):
            add_numbers(5, None)

    def test_add_invalid_type_list(self):
        """Error condition: invalid type (list)."""
        with pytest.raises(TypeError):
            add_numbers([1, 2], 3)