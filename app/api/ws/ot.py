from typing import List, Tuple
from app.schemas.events import OTDelta


def apply_op(text: str, op: OTDelta) -> str:
    """
    Applies a single OTDelta operation to a string and returns the new string.
    """
    pos = op.pos
    if op.op == "insert":
        if pos < 0:
            pos = 0
        elif pos > len(text):
            pos = len(text)
        return text[:pos] + op.chars + text[pos:]
    
    elif op.op == "delete":
        del_len = len(op.chars) if op.chars else 0
        if del_len == 0:
            return text
        if pos < 0:
            pos = 0
        end_pos = min(pos + del_len, len(text))
        return text[:pos] + text[end_pos:]
    
    return text


def transform_single(op_a: OTDelta, op_b: OTDelta) -> List[OTDelta]:
    """
    Transforms operation A against operation B (which has already been applied).
    Returns a list of operations (0, 1, or 2 operations) equivalent to A applied after B.
    """
    # If A is a no-op, return empty list
    if op_a.op == "delete" and (not op_a.chars or len(op_a.chars) == 0):
        return []

    # Extract positions and content
    pa, pb = op_a.pos, op_b.pos
    ca, cb = op_a.chars, op_b.chars
    la, lb = len(ca), len(cb)

    # CASE 1: Both are insertions
    if op_a.op == "insert" and op_b.op == "insert":
        if pa < pb:
            # A is before B, position remains the same
            return [OTDelta(op="insert", pos=pa, chars=ca, revision=op_a.revision + 1)]
        elif pa > pb:
            # A is after B, shift A's position by B's length
            return [OTDelta(op="insert", pos=pa + lb, chars=ca, revision=op_a.revision + 1)]
        else:
            # Tie-breaker at same position: deterministic choice.
            # We insert A after B (shift A by B's length)
            return [OTDelta(op="insert", pos=pa + lb, chars=ca, revision=op_a.revision + 1)]

    # CASE 2: Both are deletions
    elif op_a.op == "delete" and op_b.op == "delete":
        # A wants to delete [pa, pa + la)
        # B has already deleted [pb, pb + lb)
        if pa + la <= pb:
            # A is fully before B, no shift needed
            return [OTDelta(op="delete", pos=pa, chars=ca, revision=op_a.revision + 1)]
        elif pb + lb <= pa:
            # A is fully after B, shift left by B's deleted length
            return [OTDelta(op="delete", pos=pa - lb, chars=ca, revision=op_a.revision + 1)]
        else:
            # Overlapping deletes. Calculate what remains of A after B deleted its part.
            # Range of A in old coordinates: [pa, pa + la)
            # Range of B in old coordinates: [pb, pb + lb)
            # We want to delete what is in A's range but NOT in B's range.
            
            # Sub-case A: A is completely inside B
            if pa >= pb and pa + la <= pb + lb:
                return []  # Everything A wanted to delete is already gone

            # Sub-case B: B is completely inside A
            if pb >= pa and pb + lb <= pa + la:
                # B deleted a middle portion. We must delete the left and right portions.
                # Left portion: [pa, pb) -> maps to new pos `pa`
                left_chars = ca[:pb - pa]
                # Right portion: [pb + lb, pa + la) -> maps to new pos `pb`
                right_chars = ca[pb + lb - pa:]
                
                res = []
                if left_chars:
                    res.append(OTDelta(op="delete", pos=pa, chars=left_chars, revision=op_a.revision + 1))
                if right_chars:
                    # After left delete, the right portion is shifted left by left_chars length.
                    # In B's coordinate system, B has already deleted, so the position is `pb`.
                    # Since left portion was deleted, the new position is still `pa`!
                    # Wait, let's verify. After deleting left_chars, the right portion starts at `pa`.
                    # So the position for the second delete is indeed `pa`.
                    res.append(OTDelta(op="delete", pos=pa, chars=right_chars, revision=op_a.revision + 1))
                return res

            # Sub-case C: Overlap on the right side of A (A starts before B, but ends inside or after B)
            if pa < pb:
                # Keep only the part of A that is before B: [pa, pb)
                left_chars = ca[:pb - pa]
                if left_chars:
                    return [OTDelta(op="delete", pos=pa, chars=left_chars, revision=op_a.revision + 1)]
                return []

            # Sub-case D: Overlap on the left side of A (A starts inside B, but ends after B)
            if pa >= pb:
                # Keep only the part of A that is after B: [pb + lb, pa + la)
                # Shifted position is `pb` (since B and everything before B's end is deleted)
                right_chars = ca[pb + lb - pa:]
                if right_chars:
                    return [OTDelta(op="delete", pos=pb, chars=right_chars, revision=op_a.revision + 1)]
                return []

    # CASE 3: Insert A vs Delete B
    elif op_a.op == "insert" and op_b.op == "delete":
        # A wants to insert at pa. B deleted [pb, pb + lb)
        if pa <= pb:
            # Insert is before the deleted range. Position unchanged.
            return [OTDelta(op="insert", pos=pa, chars=ca, revision=op_a.revision + 1)]
        elif pa > pb + lb:
            # Insert is after the deleted range. Shift left by B's deleted length.
            return [OTDelta(op="insert", pos=pa - lb, chars=ca, revision=op_a.revision + 1)]
        else:
            # Insert is inside the deleted range. Since B deleted it, the insert happens at pb.
            return [OTDelta(op="insert", pos=pb, chars=ca, revision=op_a.revision + 1)]

    # CASE 4: Delete A vs Insert B
    elif op_a.op == "delete" and op_b.op == "insert":
        # A wants to delete [pa, pa + la). B inserted `cb` at pb.
        if pa + la <= pb:
            # Delete is fully before the insert. Position unchanged.
            return [OTDelta(op="delete", pos=pa, chars=ca, revision=op_a.revision + 1)]
        elif pa >= pb:
            # Delete is after the insert. Shift right by B's inserted length.
            return [OTDelta(op="delete", pos=pa + lb, chars=ca, revision=op_a.revision + 1)]
        else:
            # Insert B happens in the middle of Delete A range.
            # B's insert splits A's delete range.
            # Left portion of A: [pa, pb) -> unaffected by B's insert
            left_chars = ca[:pb - pa]
            # Right portion of A: [pb, pa + la) -> shifted right by B's insert length
            right_chars = ca[pb - pa:]
            
            res = []
            if left_chars:
                res.append(OTDelta(op="delete", pos=pa, chars=left_chars, revision=op_a.revision + 1))
            if right_chars:
                # The right portion is shifted by B's insert length `lb`
                res.append(OTDelta(op="delete", pos=pb + lb, chars=right_chars, revision=op_a.revision + 1))
            return res

    return [op_a]


def transform_list(ops_a: List[OTDelta], op_b: OTDelta) -> List[OTDelta]:
    """
    Transforms a list of operations (derived from a client operation A)
    against a single server-applied operation B.
    """
    transformed = []
    for op in ops_a:
        transformed.extend(transform_single(op, op_b))
    return transformed


def transform_against_history(op: OTDelta, history: List[OTDelta]) -> List[OTDelta]:
    """
    Transforms a single incoming client operation `op` against a list of concurrent
    server operations `history` (operations applied after the client's base revision).
    """
    current_ops = [op]
    for hist_op in history:
        current_ops = transform_list(current_ops, hist_op)
    
    # Update revision numbers of all resulting operations to match new server revision
    new_rev = history[-1].revision + 1 if history else op.revision + 1
    for final_op in current_ops:
        final_op.revision = new_rev
        
    return current_ops
