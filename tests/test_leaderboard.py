"""Minimal smoke test for leaderboard logic (import + basic)."""

def test_leaderboard_imports():
    from slacathon import middleware
    assert hasattr(middleware, "add_to_leaderboard")
    assert hasattr(middleware, "get_leaderboard")
    assert middleware.LEADERBOARD_SIZE > 0
