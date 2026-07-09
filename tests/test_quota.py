"""Minimal smoke test for quota logic (import + basic)."""

def test_quota_imports():
    from slacathon import job_manager
    from slacathon.settings import settings
    assert hasattr(job_manager, "charge_validation_quota")
    assert hasattr(settings, "max_validations_per_user")
    assert settings.max_validations_per_user > 0
