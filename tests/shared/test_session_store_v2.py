"""Tests for SessionStore V2 — UnifiedSessionInfo, SessionStatus, SessionStoreConfig,
and public Redis key builders.

TDD RED phase: all tests designed to fail before implementation.
"""

import warnings

import pytest
from pydantic import ValidationError

from shared.constants import (
    history_key,
    inbox_key,
    session_cleanup_key,
    session_key,
    session_pattern,
    streaming_lookup_key,
    subscribers_key,
)
from shared.session_store import (
    SessionStatus,
    SessionStoreConfig,
    UnifiedSessionInfo,
)

# ---------------------------------------------------------------------------
# Helper — complete sample with all 21 fields
# ---------------------------------------------------------------------------


def _all_fields_dict() -> dict:
    """Return a dict covering ALL 21 fields from SessionInfo + StreamingSessionData."""
    return {
        "session_id": "abc",
        "repo": "owner/repo",
        "thread_type": "issue",
        "thread_id": "1",
        "workflow_name": "test-workflow",
        "ref": "main",
        "worktree_path": "/tmp/worktree",
        "created_at": "2024-01-01T00:00:00Z",
        "last_run": "2024-01-01T00:00:00Z",
        "turn_count": 0,
        "status": "active",
        "summary": None,
        "streaming_token": "tok-123",
        "installation_id": "123",
        "initial_query": "hello",
        "conversation_config": "{}",
        "transcript_path": "/tmp/t.jsonl",
        "run_count": 1,
        "session_proxy_url": "http://x",
        "issue_number": "1",
        "user": "test",
    }


# ---------------------------------------------------------------------------
# SessionStatus enum
# ---------------------------------------------------------------------------


class TestSessionStatus:
    """Validate the SessionStatus enum values."""

    def test_all_status_values_exist(self):
        """Every documented status value must be in the enum."""
        assert SessionStatus.active == "active"
        assert SessionStatus.running == "running"
        assert SessionStatus.completed == "completed"
        assert SessionStatus.error == "error"
        assert SessionStatus.expired == "expired"

    def test_status_enum_is_string_enum(self):
        """Status enum must be string-comparable."""
        assert SessionStatus("active") == SessionStatus.active


# ---------------------------------------------------------------------------
# UnifiedSessionInfo model
# ---------------------------------------------------------------------------


class TestUnifiedModelAllFields:
    """Create UnifiedSessionInfo with ALL 21 fields — verify no silent drops."""

    def test_all_fields_accepted_and_roundtrip(self):
        """Every field from both original stores must survive a round-trip."""
        data = _all_fields_dict()
        obj = UnifiedSessionInfo(**data)
        dumped = obj.model_dump()

        # Count: SessionInfo (13) + StreamingSessionData unique (8) = 21
        assert len(dumped) == 21, (
            f"Expected 21 fields, got {len(dumped)}. "
            f"Missing: {set(data) - set(dumped)}. Extra: {set(dumped) - set(data)}"
        )

    @pytest.mark.parametrize(
        "field_name",
        [
            "session_id",
            "repo",
            "thread_type",
            "thread_id",
            "workflow_name",
            "ref",
            "worktree_path",
            "created_at",
            "last_run",
            "turn_count",
            "status",
            "streaming_token",
            "installation_id",
            "initial_query",
            "conversation_config",
            "transcript_path",
            "run_count",
            "session_proxy_url",
            "issue_number",
            "user",
        ],
    )
    def test_every_explicit_field_present_in_output(self, field_name):
        """Each named field must appear in model_dump() output."""
        data = _all_fields_dict()
        obj = UnifiedSessionInfo(**data)
        dumped = obj.model_dump()
        assert field_name in dumped, f"Field '{field_name}' missing from output"

    def test_summary_nullable(self):
        """summary must accept None."""
        data = _all_fields_dict()
        data["summary"] = None
        obj = UnifiedSessionInfo(**data)
        assert obj.summary is None

    def test_streaming_token_nullable(self):
        """streaming_token must accept None."""
        data = _all_fields_dict()
        data["streaming_token"] = None
        obj = UnifiedSessionInfo(**data)
        assert obj.streaming_token is None

    def test_default_values(self):
        """turn_count, run_count default to 0 and 1 respectively."""
        minimal = {
            "session_id": "abc",
            "repo": "owner/repo",
            "thread_type": "issue",
            "thread_id": "1",
            "workflow_name": "test",
            "ref": "main",
            "worktree_path": "/tmp",
            "created_at": "2024-01-01T00:00:00Z",
            "last_run": "2024-01-01T00:00:00Z",
            "status": "active",
            "installation_id": "123",
            "initial_query": "hello",
            "conversation_config": "{}",
            "session_proxy_url": "http://x",
            "issue_number": "1",
            "user": "test",
        }
        obj = UnifiedSessionInfo(**minimal)
        assert obj.turn_count == 0
        assert obj.run_count == 1
        assert obj.transcript_path == ""
        assert obj.streaming_token is None
        assert obj.summary is None

    def test_model_dump_json_includes_all_fields(self):
        """JSON serialization must include every field."""
        data = _all_fields_dict()
        obj = UnifiedSessionInfo(**data)
        json_str = obj.model_dump_json()
        for field_name in _all_fields_dict():
            if field_name in ("summary",):
                continue  # None fields may serialize differently
            assert (
                field_name in json_str
            ), f"Field '{field_name}' missing from JSON output"


class TestUnifiedModelValidation:
    """Validation rules for UnifiedSessionInfo."""

    def test_invalid_status_rejected(self):
        """Status must be a valid SessionStatus value."""
        data = _all_fields_dict()
        data["status"] = "invalid_status"
        with pytest.raises(ValidationError) as exc_info:
            UnifiedSessionInfo(**data)
        # Error should mention the status field
        errors = exc_info.value.errors()
        status_errors = [e for e in errors if "status" in str(e.get("loc", []))]
        assert len(status_errors) > 0, "Expected validation error on 'status' field"

    def test_invalid_thread_type_rejected(self):
        """thread_type must be one of pr/issue/discussion."""
        data = _all_fields_dict()
        data["thread_type"] = "chat"
        with pytest.raises(ValidationError):
            UnifiedSessionInfo(**data)

    def test_missing_required_field_raises(self):
        """Omitting session_id (required) must raise ValidationError."""
        data = _all_fields_dict()
        del data["session_id"]
        with pytest.raises(ValidationError):
            UnifiedSessionInfo(**data)


class TestUnifiedModelDocstrings:
    """Field-level docstrings documenting which original store each field came from."""

    def test_docstrings_present_for_key_fields(self):
        """Fields that bridge the two stores must have descriptive docstrings."""
        key_fields = [
            "streaming_token",
            "installation_id",
            "session_proxy_url",
            "issue_number",
            "user",
        ]
        for fname in key_fields:
            field = UnifiedSessionInfo.model_fields.get(fname)
            assert field is not None, f"Field '{fname}' missing"
            assert (
                field.description is not None
            ), f"Field '{fname}' missing docstring/description"
            assert (
                len(field.description) > 10
            ), f"Field '{fname}' docstring too short: {field.description!r}"


# ---------------------------------------------------------------------------
# SessionStoreConfig model
# ---------------------------------------------------------------------------


class TestSessionStoreConfig:
    """SessionStoreConfig extends ConversationConfig with streaming settings."""

    def test_inherits_from_conversation_config(self):
        """SessionStoreConfig must be a Pydantic model with persist, ttl_hours, etc."""
        cfg = SessionStoreConfig()
        # Base ConversationConfig fields
        assert hasattr(cfg, "persist")
        assert hasattr(cfg, "ttl_hours")
        assert hasattr(cfg, "max_turns")
        assert hasattr(cfg, "auto_continue")
        assert hasattr(cfg, "summary_fallback")

    def test_default_values(self):
        """Defaults must match existing ConversationConfig behavior."""
        cfg = SessionStoreConfig()
        assert cfg.persist is False
        assert cfg.ttl_hours > 0
        assert cfg.max_turns == 50
        assert cfg.auto_continue is False
        assert cfg.summary_fallback is True

    def test_custom_values(self):
        """All fields must accept custom values."""
        cfg = SessionStoreConfig(
            persist=True,
            ttl_hours=24,
            max_turns=100,
            auto_continue=True,
            summary_fallback=False,
        )
        assert cfg.persist is True
        assert cfg.ttl_hours == 24
        assert cfg.max_turns == 100
        assert cfg.auto_continue is True
        assert cfg.summary_fallback is False


# ---------------------------------------------------------------------------
# Public Redis key builders
# ---------------------------------------------------------------------------


class TestPublicKeyBuilders:
    """Verify all key builders are public functions returning correct format strings."""

    def test_session_key(self):
        """session_key() returns the canonical session:map:* key."""
        key = session_key("test/repo", "issue", "42", "my-workflow")
        assert key.startswith("session:map:"), f"Unexpected key format: {key}"
        assert "test--repo" in key
        assert "issue" in key
        assert "42" in key
        assert "my-workflow" in key

    def test_session_pattern(self):
        """session_pattern() returns a SCAN pattern for a repo."""
        pattern = session_pattern("test/repo")
        assert pattern.startswith("session:map:"), f"Unexpected pattern: {pattern}"
        assert pattern.endswith(":*"), f"Pattern must end with scan wildcard: {pattern}"
        assert "test--repo" in pattern

    def test_history_key(self):
        """history_key() returns session:history:{token}."""
        key = history_key("my-token-123")
        assert key == "session:history:my-token-123"

    def test_inbox_key(self):
        """inbox_key() returns session:inbox:{token}."""
        key = inbox_key("my-token-456")
        assert key == "session:inbox:my-token-456"

    def test_subscribers_key(self):
        """subscribers_key() returns session:subscribers:{token}."""
        key = subscribers_key("my-token-789")
        assert key == "session:subscribers:my-token-789"

    def test_streaming_lookup_key(self):
        """streaming_lookup_key() (from constants) returns correct lookup key."""
        key = streaming_lookup_key(
            "test/repo", "42", "my-workflow", thread_type="issue"
        )
        assert key.startswith("session:stream:lookup:"), f"Unexpected: {key}"
        assert "test--repo" in key
        assert "issue" in key
        assert "42" in key
        assert "my-workflow" in key

    def test_session_cleanup_key(self):
        """session_cleanup_key() returns a coordination key for worktree cleanup."""
        key = session_cleanup_key("test/repo", "issue", "42")
        assert "test--repo" in key
        assert "issue" in key
        assert "42" in key


class TestDeprecatedKeyBuilders:
    """Backward-compatible deprecated wrappers produce DeprecationWarning."""

    def test_deprecated_session_key_emits_warning(self):
        """Calling _session_key() must emit DeprecationWarning."""
        from shared.session_store import _session_key

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _session_key("test/repo", "issue", "42", "wf")
            deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert (
                len(deprecations) > 0
            ), "Expected DeprecationWarning from _session_key()"
            assert result == session_key("test/repo", "issue", "42", "wf")

    def test_deprecated_session_pattern_emits_warning(self):
        """Calling _session_pattern() must emit DeprecationWarning."""
        from shared.session_store import _session_pattern

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _session_pattern("test/repo")
            deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert (
                len(deprecations) > 0
            ), "Expected DeprecationWarning from _session_pattern()"
            assert result == session_pattern("test/repo")
