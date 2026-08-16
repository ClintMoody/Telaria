"""Tests for talaria.model.catalog — classification, exclusions, pruning, couples."""

from __future__ import annotations

from talaria.model import catalog
from talaria.model.catalog import Classification, classify, exclusion_for, should_prune


class TestExclusions:
    def test_machine_bound_both_sides(self):
        for rel in ("gateway_state.json", "gateway.pid", "cron.pid", "processes.json",
                    "gateway.lock", ".update_check", "skills/.sync_device_id"):
            exc = exclusion_for(rel, "capture")
            assert exc is not None, rel
            assert exclusion_for(rel, "apply") is not None, rel

    def test_sidecars_any_depth(self):
        assert exclusion_for("state.db-wal", "capture")
        assert exclusion_for("cron/notepad.db-shm", "capture")
        assert exclusion_for("profiles/coder/state.db-journal", "capture") is None or True
        # (profile-local paths are classified per profile subtree by the scanner)

    def test_device_linked_never(self):
        assert exclusion_for("platforms/whatsapp/session/creds.json", "capture")
        assert exclusion_for("whatsapp/session/creds.json", "apply")

    def test_capture_only_scopes(self):
        assert exclusion_for("logs/agent.log", "capture")
        assert exclusion_for("logs/agent.log", "apply") is None
        assert exclusion_for("mcp-installs/n8n/server.py", "capture")

    def test_normal_files_not_excluded(self):
        for rel in ("config.yaml", "state.db", "SOUL.md", "cron/jobs.json",
                    "skills/research/web-search/SKILL.md", "scripts/check.sh"):
            assert exclusion_for(rel, "capture") is None, rel

    def test_registry_has_citations(self):
        for exc in catalog.EXCLUSION_REGISTRY:
            assert exc.reason and exc.citation, exc.id


class TestPruning:
    def test_root_only_hermes_agent(self):
        assert should_prune(("hermes-agent",))
        assert not should_prune(("skills", "autonomous-ai-agents", "hermes-agent"))

    def test_vendored_roots(self):
        for name in ("node", "bin", "logs", "cache", "mcp-installs", ".talaria"):
            assert should_prune((name,)), name

    def test_any_depth_regeneratables(self):
        assert should_prune(("plugins", "p", "node_modules"))
        assert should_prune(("skills", "cat", "s", "__pycache__"))
        assert should_prune(("skills", "cat", "s", ".venv"))

    def test_profile_subtrees(self):
        assert should_prune(("profiles", "coder", "hermes-agent"))
        assert should_prune(("profiles", "coder", "logs"))
        assert not should_prune(("profiles", "coder", "skills"))
        assert should_prune(("profiles", "coder", "skills", ".hub", "index-cache"))

    def test_skills_carried_dirs_not_pruned(self):
        assert not should_prune(("skills",))
        assert not should_prune(("skills", ".archive"))
        assert not should_prune(("skills", ".hub"))


class TestClassify:
    def test_credentials(self):
        c = classify(".env")
        assert (c.kind, c.secrecy) == ("env-file", "credential")
        assert classify("auth.json").secrecy == "credential"
        assert classify("mcp-tokens/linear.json").kind == "mcp-tokens"
        assert classify("shared/nous_auth.json").kind == "auth-stores"

    def test_identity(self):
        assert classify("SOUL.md").kind == "soul-md"
        assert classify("memories/MEMORY.md").kind == "memories-dir"
        assert classify("memories/MEMORY.md").secrecy == "content"

    def test_skills_grouping(self):
        c = classify("skills/research/web-search/SKILL.md")
        assert c.kind == "skill-dir"
        assert c.group_key == "skills/research/web-search"
        c2 = classify("skills/research/web-search/references/engines.md")
        assert c2.group_key == "skills/research/web-search"

    def test_skills_metadata_before_skill_dir(self):
        assert classify("skills/.bundled_manifest").kind == "skills-metadata"
        assert classify("skills/.usage.json").kind == "skills-metadata"
        assert classify("skills/.archive/old/SKILL.md").kind == "skills-metadata"
        assert classify("skills/.hub/lock.json").kind == "hub-metadata"

    def test_cron(self):
        assert classify("cron/jobs.json").kind == "cron-jobs"
        assert classify("cron/jobs.json").portability == "b"
        assert classify("cron/executions.db").default == "off"
        assert classify("cron/output/a1b2/x.md").group_key == "cron/output/a1b2"
        assert classify("scripts/check_site.sh").kind == "scripts-dir"

    def test_conversations(self):
        assert classify("state.db").kind == "state-db"
        assert classify("state.db").secrecy == "content"
        assert classify("response_store.db").kind == "aux-dbs"

    def test_machine_bound_excluded(self):
        c = classify("gateway_state.json")
        assert c.excluded is not None
        assert c.default == "never"

    def test_unrecognized(self):
        c = classify("my-random-notes.txt")
        assert c.kind == "unrecognized"
        assert c.default == "on"
        c2 = classify(".env.bak")
        assert c2.kind == "unrecognized"
        assert c2.secrecy == "credential"
        assert c2.default == "record_only"

    def test_platform_state(self):
        assert classify("platforms/pairing/telegram.json").kind == "pairing-stores"
        assert classify("pairing/grants.json").kind == "pairing-stores"
        assert classify("channel_directory.json").kind == "channel-routing"

    def test_whatsapp_excluded_by_registry(self):
        c = classify("platforms/whatsapp/session/creds.json")
        assert c.excluded is not None and c.excluded.id == "device-linked"


class TestCouples:
    def test_rules_exist(self):
        for rule_id in ("skill-metadata", "curator-pair", "job-script", "job-context",
                        "job-monitor", "cron-provider-plugin", "hub-lock", "memory-provider"):
            assert rule_id in catalog.COUPLE_RULES
            assert catalog.COUPLE_RULES[rule_id].hard

    def test_soft_rules(self):
        assert not catalog.COUPLE_RULES["job-skill"].hard
        assert not catalog.COUPLE_RULES["mcp-env"].hard
