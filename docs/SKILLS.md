# Agent Skills

Skills are **progressive-disclosure instruction packages** for the agents (Strands
[`AgentSkills`](https://strandsagents.com/docs/user-guide/concepts/plugins/skills/) plugin). Only
each skill's `name` + `description` are front-loaded into the system prompt; the full `SKILL.md` is
pulled on demand when the model invokes the auto-registered `skills` tool. See **SPEC.md §5.4**.

> **Skills are instructions, never data.** Exact figures must always come from the tool layer
> (numbers-must-be-exact). A skill says *how* to compute / *where* to look — never a dollar amount.

## When to add a skill (vs. the alternatives)

| Mechanism | Use for |
|---|---|
| System prompt | Always-on identity / rules |
| **Steering** (`*/steering/*.md`) | The agent's core playbook |
| **Tools** (`*/tools/`) | Deterministic AWS execution |
| **Skill** (here) | A procedure needed only *sometimes* within one agent |
| Sub-agent | A genuinely different role |

## Layout

Skills live in per-agent folders; the cost agent cannot read another agent's skill files.

```
finops_core/skills/<agent>/<skill-name>/      # <agent> ∈ cost | optimize | anomaly
  ├── SKILL.md            # required
  └── references/         # optional; read via the scoped reader tool
devops_core/skills/estate/<skill-name>/        # devsecops estate agent
```

The machinery (discovery, gating, `attach_skills`, the scoped reader) lives in
`finops_core/skills/__init__.py`; `devops_core/skills` reuses it.

## Authoring a skill

1. Create `finops_core/skills/<agent>/<skill-name>/SKILL.md`. **`name` must equal the directory
   name** (lowercase, hyphenated).

   ```markdown
   ---
   name: my-skill
   description: One line on what it does and when to use it (this appears in the prompt).
   allowed-tools: read_skill_file
   metadata:
     version: "1.0"
   ---
   # Title
   Step-by-step procedure. Restate "read every number from a tool".
   ```

2. (Optional) Add `references/*.md` for deep-dive content; instruct the model to open them via the
   `read_skill_file` tool. Keep paths inside the skill folder — the reader rejects path-escape.

3. **Write the test first** (`tests/unit/test_skills.py`): add the new skill to the `SEED` map so
   `test_seed_skill_discovered` and `test_skill_name_matches_directory` cover it. `make test`.

## Enabling skills

Off by default. Turn on via any of:

- **Config:** `skills.enabled: true` in `config/finops.yaml`
- **Env:** `FINOPS_SKILLS=1`
- **CLI (per question):** `finops ask "…" --skills` / `--no-skills`; `devops ask "…" --skills`
- **Dashboard:** the **"Agent skills (beta)"** sidebar checkbox (FinOps + DevOps pages)
- **Programmatic:** `build_cost_agent(..., skills=True)` (every `build_*_agent` takes `skills`)

Precedence: an explicit `skills=`/CLI flag/toggle wins; otherwise `cfg.skills_enabled`.

## Security posture

- The lone filesystem capability skills add is a **per-agent directory-scoped reader**
  (`read_skill_file`) — paths resolving outside that agent's skills folder are rejected.
- `allowed-tools` documents a skill's intent; the agent is still only granted the scoped reader.
- Skills don't change the read-only/guarded-write posture; the `ReadOnlyGuard` hook still applies.
