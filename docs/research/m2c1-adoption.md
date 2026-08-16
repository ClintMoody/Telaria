# m2c1 Framework — What We Adopt, What We Adapt

The user pointed us at grandamenium/m2c1, a 12-phase meta-orchestration framework for autonomous
software development, with the instruction "use this skill, but only if and when and where it helps."
This document records how its process was applied to this build.

## Adopted directly

| m2c1 idea | How it shows up here |
|-----------|----------------------|
| Parallel research wave before design | Five subsystem research agents swept hermes-agent (state layout, skills, cron, integrations, install mechanics) before any design work; outputs live in `docs/research/` |
| Every artifact has a template / file-based state | All planning state is in-repo: research digests, proposals, committee critiques, binding spec, phase plan — nothing lives only in conversation |
| PRD before implementation | `docs/design/SPEC.md` is the PRD-equivalent: binding, numbered requirements (R-numbers) traceable to tests |
| Task sharding with self-contained specs | Implementation proceeded module-by-module against numbered spec sections; each engine has its own test file mapping to its requirements |
| Synergy review before execution | The adversarial committee pass is exactly this: cross-proposal coherence check, contradiction hunting, scope arbitration — with the added teeth of adversarial framing |
| Multi-angle testing at every level | Unit per engine, integration round-trips, cross-platform simulation, GUI endpoint tests, and human-emulating browser testing via Playwright |
| Human-emulating testing via Playwright | The GUI is exercised in a real Chromium via Playwright: wizard walk-through, screenshots captured for docs |
| 3-tier failure handling | Engine-level recovery (rollback), orchestrator-level (verification failures fail loudly with remediation), user-level (report flags anything needing human action) |

## Adapted (with reasons)

| m2c1 phase | Adaptation | Reason |
|------------|-----------|--------|
| Phase 3: Discovery Questions (interactive Q&A with user) | Replaced by (a) the user's brief itself, (b) research-grounded assumptions logged in the spec's Decisions table, (c) an adversarial committee empowered to arbitrate | The brief mandates a zero-involvement build; blocking on Q&A is prohibited. Every assumption is written down and reviewable after the fact |
| Phase 5–6: Tool setup via Playwright browser automation | Not needed | No external SaaS to configure; the product is local-first by design |
| Phase 7: Skill creation for execution agents | Inverted: the *product* generates a skill (the Deep-Scan skill handed to the user's Hermes agent) | The skill concept was more valuable inside the product than inside the build process |
| 12-phase strict sequence | Compressed to: research wave → proposals → adversarial committee → binding spec → TDD implementation → adversarial verification → ship | Single-owner build with subagent fan-out at the two points where independent perspectives pay: design and final review |

## Explicitly not used

- The `/start` orchestrator loop and PROGRESS.md polling — the harness's own task tracking covers it.
- Playwright MCP as a hard prerequisite gate — Playwright is used where it helps (GUI verification), not as a gate.
