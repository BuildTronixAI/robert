import pytest


def add(a: int | float, b: int | float) -> int | float:
    """Return the arithmetic sum of a and b."""
    return a + b


class TestAdd:
    """Test suite for the add function."""

    def test_add_positive_integers(self):
        """Happy path: adding two positive integers."""
        assert add(2, 3) == 5
        assert add(10, 20) == 30

    def test_add_mixed_types(self):
        """Happy path: adding integers and floats."""
        assert add(1.5, 2.5) == 4.0
        assert add(5, 2.5) == 7.5
        assert add(1, 1.0) == 2.0

    def test_add_edge_cases(self):
        """Edge cases: zero, negative numbers, and boundary values."""
        assert add(0, 0) == 0
        assert add(-1, 1) == 0
        assert add(-5, -3) == -8
        assert add(0, 100) == 100
        assert add(-0.5, 0.5) == 0.0

    def test_add_large_numbers(self):
        """Edge case: very large numbers."""
        assert add(10**15, 10**15) == 2 * 10**15
        assert add(1e100, 1e100) == 2e100

    def test_add_type_error(self):
        """Error condition: invalid argument types."""
        with pytest.raises(TypeError):
            add("5", 3)
        with pytest.raises(TypeError):
            add(5, None)
        with pytest.raises(TypeError):
            add([1], [2])


if __name__ == "__main__":
    # Inline verification without pytest runner
    print("Running inline assertions...")
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
    assert add(1.5, 2.5) == 4.0
    assert add(10, -5) == 5
    print("✓ All inline assertions passed!")
    print("\nRun with: pytest <filename> -v")