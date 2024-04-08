import pytest
from app.schemas.events import OTDelta
from app.api.ws.ot import apply_op, transform_single, transform_against_history


def test_apply_op():
    # Insert operations
    assert apply_op("abc", OTDelta(op="insert", pos=1, chars="X", revision=0)) == "aXbc"
    assert apply_op("abc", OTDelta(op="insert", pos=0, chars="X", revision=0)) == "Xabc"
    assert apply_op("abc", OTDelta(op="insert", pos=3, chars="X", revision=0)) == "abcX"
    assert apply_op("abc", OTDelta(op="insert", pos=10, chars="X", revision=0)) == "abcX"

    # Delete operations
    assert apply_op("abcde", OTDelta(op="delete", pos=1, chars="bc", revision=0)) == "ade"
    assert apply_op("abcde", OTDelta(op="delete", pos=0, chars="a", revision=0)) == "bcde"
    assert apply_op("abcde", OTDelta(op="delete", pos=3, chars="de", revision=0)) == "abc"


def test_transform_inserts():
    # A inserts before B
    op_a = OTDelta(op="insert", pos=2, chars="A", revision=0)
    op_b = OTDelta(op="insert", pos=5, chars="B", revision=0)
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 2  # Unchanged because it's before pb
    
    # A inserts after B
    op_a = OTDelta(op="insert", pos=5, chars="A", revision=0)
    op_b = OTDelta(op="insert", pos=2, chars="B", revision=0)  # length of "B" = 1
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 6  # Shifted by 1 (length of "B")


def test_transform_inserts_at_same_position():
    # Tie-breaker logic: B went first, A must be shifted by B's length
    op_a = OTDelta(op="insert", pos=3, chars="AAA", revision=0)
    op_b = OTDelta(op="insert", pos=3, chars="B", revision=0)  # len(B) = 1
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 4  # Shifted by 1 because pb = pa


def test_transform_deletes_no_overlap():
    # A deletes before B
    op_a = OTDelta(op="delete", pos=1, chars="xy", revision=0)  # len 2
    op_b = OTDelta(op="delete", pos=5, chars="z", revision=0)   # len 1
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 1  # Unchanged
    
    # A deletes after B
    op_a = OTDelta(op="delete", pos=5, chars="z", revision=0)
    op_b = OTDelta(op="delete", pos=1, chars="xy", revision=0)  # len 2
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 3  # Shifted left by 2 (length of B)


def test_transform_deletes_overlapping():
    # Sub-case A: A is completely inside B
    op_a = OTDelta(op="delete", pos=3, chars="cd", revision=0)   # cd at 3-5
    op_b = OTDelta(op="delete", pos=2, chars="bcde", revision=0) # bcde at 2-6
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 0  # cd is already deleted by B

    # Sub-case B: B is completely inside A (splits A)
    op_a = OTDelta(op="delete", pos=1, chars="bcde", revision=0) # bcde at 1-5
    op_b = OTDelta(op="delete", pos=2, chars="cd", revision=0)   # cd at 2-4
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 2
    assert transformed[0].pos == 1
    assert transformed[0].chars == "b"
    assert transformed[1].pos == 1  # Positioned at B's start coordinate in new text
    assert transformed[1].chars == "e"

    # Sub-case C: Overlap on the right side of A (A starts before B, ends inside B)
    op_a = OTDelta(op="delete", pos=2, chars="cde", revision=0)  # cde at 2-5
    op_b = OTDelta(op="delete", pos=4, chars="efgh", revision=0) # efgh at 4-8
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 2
    assert transformed[0].chars == "cd"

    # Sub-case D: Overlap on the left side of A (A starts inside B, ends after B)
    op_a = OTDelta(op="delete", pos=4, chars="efgh", revision=0) # efgh at 4-8
    op_b = OTDelta(op="delete", pos=2, chars="cde", revision=0)  # cde at 2-5 (len 3)
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 2  # pb is 2, since B deleted up to end
    assert transformed[0].chars == "fgh"


def test_transform_insert_vs_delete():
    # Insert before delete
    op_a = OTDelta(op="insert", pos=2, chars="X", revision=0)
    op_b = OTDelta(op="delete", pos=4, chars="abc", revision=0)
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 2

    # Insert after delete
    op_a = OTDelta(op="insert", pos=8, chars="X", revision=0)
    op_b = OTDelta(op="delete", pos=2, chars="abc", revision=0)  # len 3
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 5  # Shifted left by 3

    # Insert inside deleted region
    op_a = OTDelta(op="insert", pos=4, chars="X", revision=0)
    op_b = OTDelta(op="delete", pos=2, chars="abcd", revision=0) # len 4
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 1
    assert transformed[0].pos == 2  # Adjusted to the deletion start


def test_transform_delete_vs_insert_split():
    # Insert B splits Delete A
    op_a = OTDelta(op="delete", pos=1, chars="abcdef", revision=0)  # pos 1-7
    op_b = OTDelta(op="insert", pos=4, chars="XYZ", revision=0)     # splits at original pos 4
    
    transformed = transform_single(op_a, op_b)
    assert len(transformed) == 2
    
    # Left portion: [1, 4) -> maps to delete "abc" at pos 1
    assert transformed[0].pos == 1
    assert transformed[0].chars == "abc"
    
    # Right portion: [4, 7) -> maps to delete "def" at pos 4 + len("XYZ") = 7
    assert transformed[1].pos == 7
    assert transformed[1].chars == "def"


def test_transform_against_history():
    # Multiple sequential transformations
    op = OTDelta(op="insert", pos=5, chars="A", revision=1)
    
    # History: 
    # H1: Insert "X" at 2 (revision 1)
    # H2: Delete "yz" (len 2) at 6 (revision 2)
    history = [
        OTDelta(op="insert", pos=2, chars="X", revision=1),
        OTDelta(op="delete", pos=6, chars="yz", revision=2)
    ]
    
    transformed = transform_against_history(op, history)
    assert len(transformed) == 1
    # 1. After H1 (insert X at 2): pos 5 -> 6
    # 2. After H2 (delete yz at 6): pos 6 is exactly at deletion boundary -> shifts to pb = 6
    assert transformed[0].pos == 6
    assert transformed[0].revision == 3
