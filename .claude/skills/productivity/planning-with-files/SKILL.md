---
name: planning-with-files
description: File-based planning with persistent working memory on disk. Creates task_plan.md, findings.md, and progress.md for complex multi-step tasks.
---

# Planning with Files

Use persistent markdown files as "working memory on disk" for complex, multi-step tasks. Never start a complex task without a plan file.

## Core Rules

1. **Before any complex task** (3+ steps or 5+ tool calls): create `task_plan.md` in the project root
2. **Save findings** after every 2 significant operations to `findings.md`
3. **Re-read the plan** before making major decisions
4. **Update status** after completing each phase
5. **Log all errors** in `progress.md`

## File Structure

### `task_plan.md` — The Master Plan

```markdown
# Task Plan: [Goal]

## Phases
- [ ] Phase 1: [Name] — [Brief description]
- [ ] Phase 2: [Name] — [Brief description]
- [ ] Phase 3: [Name] — [Brief description]

## Key Decisions
- [Date] Decision: [What was decided and why]

## Current Status
**Phase**: [X] | **Step**: [Y] | **State**: [in_progress | blocked | complete]
```

### `findings.md` — Research & Discoveries

Document every discovery:
- File locations and their purposes
- Configuration settings found
- Dependencies and versions
- Gotchas and edge cases
- API behavior observations

Format:
```markdown
# Findings

## [Date/Time] — [Topic]
- Finding: [What was discovered]
- Source: [File/URL/command]
- Impact: [How this affects the plan]
```

### `progress.md` — Session Log

Log every significant action:
```
## Session: [Date] [Start Time]
- [Timestamp] Started Phase 1
- [Timestamp] Created file: src/feature.py
- [Timestamp] Test: 5/5 passed
- [Timestamp] ERROR: Connection refused (resolved by...)
- [Timestamp] Completed Phase 1
- [Timestamp] Started Phase 2
```

## Workflow

### Starting a Task
1. Read the user's request carefully
2. Create `task_plan.md` with concrete, testable phases
3. Begin `progress.md` with the session start
4. Execute Phase 1

### During Execution
1. Before each major action: glance at `task_plan.md`
2. After every 2 significant operations: save to `findings.md`
3. After each phase: update `task_plan.md` status
4. Keep `progress.md` up to date as you go

### Handling Problems
- When you hit an error: log it in `progress.md` BEFORE investigating
- When you discover something surprising: add to `findings.md` immediately
- When the plan needs to change: update `task_plan.md` and note the decision
- When you're uncertain: re-read the plan, then ask the user

### Completion
1. Mark all phases as `[x]` complete in `task_plan.md`
2. Add a final entry to `progress.md`
3. Ask the user if they want to keep or delete the planning files
