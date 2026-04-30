# 🚀 Tools Priority: Focus on Core Gaps

**Objective**: Align Ethos tools with Claude Code implementation  
**Focus Areas**: Task, Interaction, Shell, Session, MCP, Orchestration

---

## 📊 Quick Priority Matrix

```
SEVERITY │ TOOL                    │ CURRENT STATUS  │ EFFORT │ IMPACT
──────────────────────────────────────────────────────────────────────
🔴 CRIT  │ AskUser (Preview/Anno) │ ⚠️ Partial      │ 2-3d   │ CRITICAL
🔴 CRIT  │ Bash (Semantic Analy)  │ ⚠️ Partial      │ 2-3d   │ HIGH
🔴 CRIT  │ Task (Dependencies)    │ ⚠️ Partial      │ 2-3d   │ HIGH
──────────────────────────────────────────────────────────────────────
🟠 HIGH  │ SendMessage (Async)    │ ⚠️ Partial      │ 1-2d   │ HIGH
🟠 HIGH  │ Bash (Progress)        │ ❌ Missing      │ 0.5d   │ MEDIUM
──────────────────────────────────────────────────────────────────────
🟡 MED   │ Skill (Validation)     │ ⚠️ Basic        │ 1-2d   │ MEDIUM
🟡 MED   │ Config (Schema)        │ ⚠️ Basic        │ 1d     │ MEDIUM
🟡 MED   │ PowerShell (Semantic)  │ ❌ Missing      │ 1-2d   │ LOW
🟡 MED   │ MCP (Error handling)   │ ⚠️ Basic        │ 2-3d   │ MEDIUM
```

---

## 🎯 TOP 3 CRITICAL GAPS

### 1. **AskUser** - Preview Options + Annotations

**Current Gap**:
```python
# Ethos: Basic Q&A only
questions = [
    {"question": "Which?", "options": ["A", "B"]}
]

# Claude Code: Visual decision support
questions = [
    {
        "question": "Compare layouts",
        "options": [
            {
                "label": "Option A",
                "description": "Side-by-side layout",
                "preview": "┌──┬──┐\n│A │B │\n└──┴──┘"  # ← KEY
            },
            {
                "label": "Option B",
                "description": "Stacked layout",
                "preview": "┌────┐\n│ A  │\n├────┤\n│ B  │\n└────┘"  # ← KEY
            }
        ]
    }
]

# Response includes user's selected preview + notes
{
    "answers": {"question": "Option A"},
    "annotations": {
        "question": {
            "preview": "┌──┬──┐\n│A │B │\n└──┴──┘",  # ← KEY
            "notes": "More compact, easier to scan"
        }
    }
}
```

**Why Critical**:
- Blocks visual decision workflows (UI mockups, code variants)
- Users can't compare options before choosing
- Required for design/architecture discussions

**Files to Update**:
```
src/ai/tools/interaction/ask_user.py
├── Add preview field to QuestionOption
├── Add annotations to response
├── Add validation (uniqueness)
└── Wire into ask_user schema
```

**Effort**: 2-3 days  
**Expected Impact**: Unblocks 30% of decision workflows

---

### 2. **Bash** - Command Semantic Analysis + Smart Collapsing

**Current Gap**:
```python
# Ethos: All output dumped as-is
$ ls -la  # Output: 100+ lines, no collapse
$ grep -r "pattern"  # Output: all matches, raw text

# Claude Code: Smart classification + UI optimization
$ ls -la       # "Listed 12 directories, 48 files" [expand to see]
$ grep -r "p"  # "Found 156 matches in 23 files" [expand to see]
```

**Why Critical**:
- Search/list commands bloat chat history
- Users can't scan without collapsing
- Progress display missing for long commands

**Implementation Phases**:

**Phase 1: Command Classifier** (1 day)
```python
def classify_bash_command(command: str) -> dict:
    """
    Returns:
    {
        "is_search": True,      # find, grep, rg, locate
        "is_read": False,       # cat, head, tail, jq
        "is_list": False,       # ls, tree, du
        "should_collapse": True, # Auto-collapse in UI
        "summary_template": "Found {count} matches in {files} files"
    }
    """
```

**Phase 2: Output Formatting** (1 day)
```python
# Instead of raw output, return structured:
{
    "summary": "Found 156 matches in 23 files",
    "collapsed": True,
    "line_count": 500,
    "raw_output": "...",  # On-click expand
    "type": "search"
}
```

**Phase 3: Progress Display** (0.5 day)
```python
# After 2 seconds, show spinner
# Show: ⏳ Running for 3.2s...
```

**Files to Update**:
```
src/ai/tools/shell/bash.py
├── Add command_classifier module
├── Add output formatter
├── Add progress display
├── Add sed/destructive warnings
└── Update BashInput/Output schemas
```

**Effort**: 2-3 days  
**Expected Impact**: Reduces chat bloat by 40-60% on search/list commands

---

### 3. **Task** - Dependencies & Blocking

**Current Gap**:
```python
# Ethos: Flat task list
tasks = [
    TaskRecord(id="1", subject="Write tests"),
    TaskRecord(id="2", subject="Run tests"),
    TaskRecord(id="3", subject="Deploy")
]
# No way to express: "Task 2 blocked by Task 1"
# No way to prevent: starting Task 2 before Task 1 completes

# Claude Code: Dependency graph
tasks = [
    TaskRecord(
        id="1",
        subject="Write tests",
        blocks=["2"]  # This task blocks task 2
    ),
    TaskRecord(
        id="2",
        subject="Run tests",
        blocked_by=["1"]  # This task blocked by task 1
    ),
    TaskRecord(
        id="3",
        subject="Deploy",
        blocked_by=["2"]
    )
]

# TaskList shows: "Task 2 available: test_suite_ready" → can claim
#                 "Task 3 available: deploy_ready" → can claim
#                 "Task 2 unavailable: waiting for task 1"
```

**Why Critical**:
- Complex workflows need dependencies
- Prevents state machine violations
- Enables multi-agent coordination

**Implementation Steps**:

**Step 1: Extend TaskRecord** (0.5 day)
```python
class TaskRecord(BaseModel):
    id: str
    subject: str
    description: str
    status: str
    
    # ← NEW
    owner: Optional[str] = None       # Subagent ID
    active_form: Optional[str] = None # "Running tests..."
    blocked_by: List[str] = []        # Dependency IDs
    blocks: List[str] = []            # Dependent task IDs
    metadata: dict = {}
    created_at: datetime
    updated_at: datetime
```

**Step 2: Add State Machine Validation** (0.5 day)
```python
def validate_task_update(task: TaskRecord, update: TaskUpdate):
    # Prevent completing task if dependencies unmet
    if update.status == "completed" and task.blocked_by:
        unmet = [t for t in task.blocked_by 
                 if store.get_task(t).status != "completed"]
        if unmet:
            raise ValueError(f"Cannot complete: task {unmet[0]} not done")
    
    # Prevent state skip (pending → completed without in_progress)
    if task.status == "pending" and update.status == "completed":
        raise ValueError("Must transition: pending → in_progress → completed")
```

**Step 3: Update TaskList** (0.5 day)
```python
# Return three groups:
{
    "available": [              # Can be claimed now
        {id: "1", subject: "...", blocked_by: []}
    ],
    "blocked": [                # Waiting for dependencies
        {id: "2", subject: "...", blocked_by: ["1"], blocker_status: "in_progress"}
    ],
    "completed": [
        {id: "3", subject: "...", completed_at: "..."}
    ]
}
```

**Step 4: Update TaskGet** (0.5 day)
```python
# Return dependency info
{
    "id": "2",
    "subject": "Run tests",
    "blocked_by": ["1"],
    "blocker_details": [
        {id: "1", subject: "Write tests", status: "in_progress"}
    ],
    "blocks": ["3"]
}
```

**Files to Update**:
```
src/ai/tools/task/
├── task_create.py     (add blocked_by, blocks)
├── task_get.py        (return dependency info)
├── task_list.py       (group by available/blocked/completed)
├── task_update.py     (validate dependencies)
└── _store.py          (extend TaskRecord)
```

**Effort**: 2-3 days  
**Expected Impact**: Enables 60% more complex workflows

---

## 📋 Implementation Order

### ✅ SPRINT 1 (This Week)
```
Day 1-2: AskUser (Preview + Annotations)
│
├─ Extend schema
├─ Add validation
├─ Update response format
└─ Frontend integration (modal layout)

Day 2-3: Bash (Semantic Analysis)
│
├─ Command classifier
├─ Output formatter (collapsing logic)
├─ Progress display
└─ Test with real commands
```

### 📌 SPRINT 2 (Next Week)
```
Day 1-2: Task (Dependencies)
│
├─ Extend TaskRecord
├─ Add state machine validation
├─ Update TaskList/TaskGet/TaskUpdate
└─ Test dependency graphs

Day 2-3: SendMessage (Async)
│
├─ Add async execution
├─ Add streaming support
└─ Test with background tasks
```

### 🔮 SPRINT 3+: Polish
```
- Skill (Validation + error handling)
- Config (Schema validation)
- PowerShell (Semantic analysis)
- MCP (Error handling + async)
```

---

## 💡 Quick Start: Pick One

**Want visual decision support?**  
→ Start with **AskUser** (Preview + Annotations)  
→ 2-3 days, ships with frontend UI

**Want cleaner chat output?**  
→ Start with **Bash** (Semantic analysis)  
→ 2-3 days, automatic collapsing saves tokens

**Want complex workflows?**  
→ Start with **Task** (Dependencies)  
→ 2-3 days, enables task graphs

---

## 📊 Expected Timeline

```
Week 1: AskUser + Bash              (4-6 days)
        ├─ AskUser: Preview, Annotations
        └─ Bash: Semantic analysis, Collapsing

Week 2: Task + SendMessage          (3-4 days)
        ├─ Task: Dependencies & Blocking
        └─ SendMessage: Async & Streaming

Week 3: Polish (Skill, Config, etc) (2-3 days)
        └─ Lower priority enhancements

TOTAL: ~10-13 days of focused work
```

---

## 🔑 Key Files to Modify

### AskUser
- `src/ai/tools/interaction/ask_user.py`
- Schema: add `preview`, `annotations`, `metadata`

### Bash
- `src/ai/tools/shell/bash.py`
- Add: `command_classifier.py`, `output_formatter.py`

### Task
- `src/ai/tools/task/_store.py` (extend TaskRecord)
- `src/ai/tools/task/task_*.py` (all 6 tools)

### SendMessage
- `src/ai/tools/interaction/send_user_message.py`

---

## ✨ Expected Impact

After completing top 3:

| Metric | Before | After |
|--------|--------|-------|
| Chat token bloat (searches) | 100% | 20-30% |
| Visual decision support | None | Full |
| Task workflow complexity | Simple linear | Dependency graphs |
| User UX improvements | Minimal | Significant |

---

## 🤔 Questions Before Starting

1. **AskUser Preview**: Should preview always render markdown as monospace?  
2. **Bash Collapsing**: Collapse on what threshold? (default: >50 lines)  
3. **Task Blocking**: Allow cycles (A→B→C→A), or only DAGs?  
4. **Frontend**: Use existing modal system, or build new?

