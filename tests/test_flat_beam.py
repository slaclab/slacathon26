"""Minimal smoke test for flat_beam task (import + basic)."""

def test_flat_beam_imports_and_run():
    from slacathon.tasks.flat_beam import validate, Input
    res = validate(Input(q1=0, q2=0, q3=0, d2=0, d3=0))
    assert hasattr(res, "score")
    assert res.score > 0
    assert hasattr(res, "solved")
