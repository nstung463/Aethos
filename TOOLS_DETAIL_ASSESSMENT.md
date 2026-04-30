# 📋 Detailed Tools Assessment vs Claude Code

**Focus**: Task, Interaction, Shell, Session, MCP, Orchestration  
**Date**: 2026-04-19  
**Objective**: Identify gaps and prioritize improvements to match Claude Code implementation

---

## 🎯 Priority Matrix

| Priority | Tool | Category | Gap | Effort | Impact | Recommended |
|----------|------|----------|-----|--------|--------|-------------|
| 🔴 P0 | **AskUser** | Interaction | Preview + Annotations | 2-3d | **CRITICAL** | ✅ NEXT |
| 🔴 P0 | **Bash** | Shell | Semantic analysis + Collapsing | 2-3d | **HIGH** | ✅ NEXT |
| 🟠 P1 | **TaskCreate/Get/List/Update** | Task | Blocking/dependencies + Metadata | 2-3d | HIGH | ✅ Soon |
| 🟠 P1 | **SendMessage** | Interaction | Async + Streaming | 1-2d | HIGH | ✅ Soon |
| 🟠 P1 | **Skill** | Orchestration | Validation + Error handling | 1-2d | Medium | Later |
| 🟡 P2 | **Config** | Session | Settings schema validation | 1d | Medium | Later |
| 🟡 P2 | **PowerShell** | Shell | Command semantics (Windows) | 1-2d | Low | Later |
| 🟡 P2 | **MCP Tools** | MCP | Error handling + Async | 2-3d | Medium | Later |

---

## 1️⃣ INTERACTION TOOLS

### 📌 AskUser (Ask User Question Tool)

#### Current Status (Ethos)
```python
# ✅ Working Features
- Basic question/option structure
- Multi-select support (basic)
- stdin input fallback for tests

# ❌ Missing Features
- Preview options (for visual comparison)
  * Cannot show mockups, code snippets, UI variants
  * Users can't compare visually before answering
  
- Annotations/notes per question
  * Cannot capture user notes on selections
  * Cannot track which preview was selected
  
- Metadata tracking
  * No source tracking (e.g., "remember" command)
  * No analytics/telemetry support
  
- Validation
  * No uniqueness checking (duplicate questions/options)
  * No option label validation
  
- API Response format
  * Missing annotations field in response
  * No way to return selected preview content
```

#### Claude Code Implementation
```typescript
// Key features
✅ Preview field per option (optional)
   - Renders as monospace box in side-by-side layout
   - Supports ASCII mockups, code snippets, diagrams
   
✅ Annotations tracking
   - Per-question: preview content + free-text notes
   - Keyed by question text
   - Returned in response payload
   
✅ Metadata tracking
   - source: "remember" | "command" | etc
   - Used for analytics + feature tracking
   
✅ Validation
   - Question text uniqueness check
   - Option labels unique within question
   - 2-4 options per question requirement
   
✅ Output schema
   {
     questions: [...],
     answers: {question_text: answer_string},
     annotations: {
       question_text: {
         preview?: string,
         notes?: string
       }
     }
   }
```

#### Implementation Roadmap (AskUser)
```python
# Step 1: Extend schema
class QuestionOption(BaseModel):
    label: str
    description: str
    preview: Optional[str] = None  # ← NEW

class Question(BaseModel):
    question: str
    header: str
    options: List[QuestionOption]
    multi_select: bool = False

class AskUserInput(BaseModel):
    questions: List[Question]
    annotations: Optional[dict] = None  # ← NEW
    metadata: Optional[dict] = None     # ← NEW

# Step 2: Validation logic
def validate_questions(questions):
    # Check unique question texts
    # Check unique option labels per question
    # Check 2-4 options per question
    
# Step 3: Update response format
class AskUserOutput(BaseModel):
    questions: List[Question]
    answers: dict[str, str]          # question_text -> answer
    annotations: dict[str, dict]      # question_text -> {preview, notes}
    
# Step 4: Frontend integration
# - Side-by-side layout when preview exists
# - Text input for notes
# - Display selected preview + notes in result
```

**Effort**: 2-3 days (schema + validation + response handling)  
**Impact**: CRITICAL - blocks visual decision workflows

---

### SendMessage (Send User Message Tool)

#### Current Status
```python
# ✅ Working
- Basic message sending
- Text content only

# ❌ Missing
- Async/background mode
- Streaming capabilities
- Metadata/annotations
- Message classification (status, error, info)
```

#### Claude Code Implementation
```typescript
// Key features
✅ Async mode (doesn't block agent execution)
✅ Streaming support (for real-time updates)
✅ Message type classification (notification, status, error)
✅ Attachments/metadata support
```

**Effort**: 1-2 days  
**Impact**: HIGH - needed for background task notifications

---

## 2️⃣ SHELL TOOLS

### 📌 Bash Tool

#### Current Status (Ethos)
```python
# ✅ Working Features
- Command execution in sandbox
- Basic timeout support
- Permission checking (basic)
- Background flag (reserved, not implemented)

# ❌ Missing Features (Critical gaps)
- Command semantic analysis
  * No distinction between search/read/write
  * Cannot auto-collapse output (UI optimization)
  * Cannot provide smart summaries
  
- Progress display
  * No progress indicator for long-running commands
  * Threshold-based display missing
  
- Output optimization
  * Cannot intelligently collapse search results
  * Cannot summarize directory listings
  * Cannot format complex output (images, tables)
  
- Command validation
  * Missing sed/edit parser
  * No destructive command warnings
  * Limited path validation
  
- Error handling
  * Basic error messages
  * Missing helpful context
```

#### Claude Code Implementation (BashTool.tsx)
```typescript
// Advanced features
✅ Command semantic analysis
   - SEARCH_COMMANDS: find, grep, rg, ag, ack, locate
   - READ_COMMANDS: cat, head, tail, wc, jq, awk, sort
   - LIST_COMMANDS: ls, tree, du
   - SEMANTIC_NEUTRAL: echo, printf, true, false
   
   → isSearchOrReadBashCommand() returns {isSearch, isRead, isList}
   → Used to auto-collapse output in UI
   
✅ Progress display
   - PROGRESS_THRESHOLD_MS = 2000
   - Show spinner after 2 seconds
   - ASSISTANT_BLOCKING_BUDGET_MS = 15_000
   
✅ Output optimization
   - Collapse search results > N lines
   - Summarize: "Found X matches in Y files"
   - Resize/crop image output
   - Preserve colored output with striping
   
✅ Semantic validation
   - sed parser: detect -i (in-place edit)
   - Destructive command warnings
   - Path validation (inside workspace)
   
✅ Error context
   - Command failed: "errno: 2, No such file"
   - Suggest remediation
```

#### Implementation Roadmap (Bash)

**Phase 1: Command Semantic Analysis** (1 day)
```python
# Build command classifiers
BASH_SEARCH_COMMANDS = {"find", "grep", "rg", "ag", "ack", "locate"}
BASH_READ_COMMANDS = {"cat", "head", "tail", "wc", "stat", "jq", "awk", "sort"}
BASH_LIST_COMMANDS = {"ls", "tree", "du"}
BASH_SEMANTIC_NEUTRAL = {"echo", "printf", "true", "false", ":"}

def classify_bash_command(command: str) -> BashCommandType:
    """
    Returns: {
        is_search: bool,
        is_read: bool,
        is_list: bool,
        should_collapse: bool,  # UI optimization
        summary_template: str   # e.g., "Found {count} matches"
    }
    """
    # Parse command with shell lexer
    # Classify each part (handle pipes, redirects)
    # Return compound classification
```

**Phase 2: Progress Display** (0.5 day)
```python
# Add progress indicators
PROGRESS_THRESHOLD_MS = 2000

def _bash(command: str, timeout: int = None, ...):
    start_time = time.time()
    proc = subprocess.Popen(...)
    
    while proc.poll() is None:
        elapsed = time.time() - start_time
        if elapsed > PROGRESS_THRESHOLD_MS and not shown_progress:
            emit_progress_indicator()
            shown_progress = True
        time.sleep(0.1)
```

**Phase 3: Output Optimization** (1 day)
```python
# Smart output formatting
def format_bash_output(
    command: str,
    stdout: str,
    stderr: str,
    classification: BashCommandType
) -> FormattedOutput:
    if classification.is_search and line_count > 100:
        return {
            "summary": f"Found {len(matches)} matches in {len(files)} files",
            "collapsed": True,
            "details_on_click": stdout
        }
    elif classification.is_list:
        return {
            "summary": f"Listed {dir_count} directories, {file_count} files",
            "collapsed": True,
            "details_on_click": stdout
        }
    # ... more cases
```

**Phase 4: Enhanced Validation** (0.5 day)
```python
# Add sed parser + destructive warnings
def validate_bash_command(command: str, permission_context: PermissionContext):
    if "--no-verify" in command:
        warn("Skipping git hooks")
    if "-i" in command and "sed" in command:
        warn("In-place file edit — cannot be undone")
    if "rm -rf" in command:
        warn("Destructive: will delete recursively")
```

**Total Effort**: 2-3 days  
**Impact**: HIGH - improves UX with smart collapsing + progress display

---

## 3️⃣ TASK MANAGEMENT TOOLS

### 📌 Task Tools (Create, Get, List, Update, Stop, Output)

#### Current Status (Ethos)
```python
# ✅ Working Features
- Basic CRUD operations
- Task status tracking (pending, in_progress, completed)
- Metadata support
- TaskRecord model

# ❌ Missing Features
- Task dependencies/blocking
  * No way to mark "Task B blocked by Task A"
  * No dependency validation
  
- Enhanced metadata
  * No owner field (for subagent tracking)
  * No blockedBy/blocks relationships
  * No activeForm tracking (spinner text)
  
- Task relationship queries
  * Cannot find "tasks blocking this task"
  * Cannot find "tasks this task blocks"
  
- Background task tracking
  * No task output file handling
  * No streaming output support
  
- Status transitions
  * No validation (e.g., pending → completed without in_progress)
  * No lifecycle enforcement
```

#### Claude Code Implementation
```typescript
// Advanced features
✅ Task blocking relationships
   - addBlockedBy: string[]  // Tasks that must complete first
   - addBlocks: string[]     // Tasks waiting on this one
   - Prevents state transitions if dependencies unmet
   
✅ Extended metadata
   - owner: string           // Subagent ID
   - activeForm: string      // Spinner text "Running tests..."
   - metadata: Record        // Free-form data
   
✅ Relationship queries
   - TaskGet returns: { blockedBy: [], blocks: [] }
   - TaskList shows: which tasks are unblocked & available
   
✅ Background execution
   - TaskStop can kill running background jobs
   - TaskOutput returns file path for async task output
   
✅ State machine
   - Enforces: pending → in_progress → completed
   - Cannot skip states
   - Validation on transitions
```

#### Implementation Roadmap (Task Tools)

**Step 1: Extend TaskRecord** (0.5 day)
```python
class TaskRecord(BaseModel):
    id: str
    subject: str
    description: str
    status: str  # pending, in_progress, completed
    
    # ← NEW
    owner: Optional[str] = None        # Subagent ID
    active_form: Optional[str] = None  # "Running tests..."
    blocked_by: List[str] = []         # Task IDs
    blocks: List[str] = []             # Task IDs
    metadata: dict = {}
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
```

**Step 2: Add Validation** (0.5 day)
```python
class TaskUpdate(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = None
    active_form: Optional[str] = None
    add_blocked_by: List[str] = []     # ← NEW
    add_blocks: List[str] = []          # ← NEW
    metadata: Optional[dict] = None

def validate_task_update(task: TaskRecord, update: TaskUpdate):
    # Check state transitions
    if task.status == "completed":
        raise ValueError("Cannot update completed task")
    
    # Check dependencies before transitioning to completed
    if update.status == "completed" and task.blocked_by:
        unmet = [t for t in task.blocked_by if store.get_task(t).status != "completed"]
        if unmet:
            raise ValueError(f"Task blocked by: {unmet}")
```

**Step 3: Update TaskList** (0.5 day)
```python
def build_task_list_tool(store: ToolStore):
    def _list() -> str:
        all_tasks = store.get_all_tasks()
        unblocked = [t for t in all_tasks 
                     if t.status != "completed" and not t.blocked_by]
        blocked = [t for t in all_tasks 
                   if t.blocked_by]
        completed = [t for t in all_tasks 
                     if t.status == "completed"]
        
        return json.dumps({
            "available": unblocked,        # Can be claimed
            "blocked": blocked,            # Waiting for dependencies
            "completed": completed
        })
```

**Step 4: Update Output Tool** (0.5 day)
```python
class TaskOutputInput(BaseModel):
    task_id: str
    block: bool = True           # Wait for completion
    timeout_ms: int = 30000      # Max wait time

def build_task_output_tool(store: ToolStore):
    def _output(task_id: str, block: bool = True, timeout_ms: int = 30000) -> str:
        task = store.get_task(task_id)
        if task.status == "completed":
            # Read output file
            output_file = f"{store.workspace}/.tasks/{task_id}.output"
            if output_file.exists():
                return output_file.read_text()
        
        if block:
            # Wait for completion
            deadline = time.time() + timeout_ms/1000
            while task.status != "completed" and time.time() < deadline:
                time.sleep(0.1)
                task = store.get_task(task_id)
        
        return json.dumps({"status": task.status, "task_id": task_id})
```

**Total Effort**: 2-3 days  
**Impact**: HIGH - essential for multi-task workflows

---

## 4️⃣ SESSION TOOLS

### 📌 Config (Tool Configuration)

#### Current Status
```python
# ✅ Working
- Basic settings reading
- Environment variable access

# ❌ Missing
- Settings validation (schema)
- Supported settings documentation
- Settings change callbacks
- Real-time config updates
```

#### Claude Code Implementation
```typescript
✅ Settings schema validation (settings.json)
✅ Supported settings registry
✅ Settings change notifications
✅ Hotload capability
```

**Effort**: 1 day  
**Impact**: Medium

---

## 5️⃣ ORCHESTRATION TOOLS

### 📌 Skill Tool (Load & Execute Skills)

#### Current Status
```python
# ✅ Working
- Load skills from workspace/skills/
- Basic skill execution
- Skill listing

# ❌ Missing
- Skill validation (schema, required fields)
- Error handling + helpful messages
- Skill caching
- Version tracking
- Skill dependencies
```

#### Claude Code Implementation
```typescript
✅ Skill validation (required name, description, triggers)
✅ Error handling with remediation hints
✅ Caching for performance
✅ Dependency graph
✅ Enable/disable toggle
```

**Effort**: 1-2 days  
**Impact**: Medium - improves skill UX

---

## 6️⃣ MCP INTEGRATION

### 📌 MCP Tools (Full Integration)

#### Current Status
```python
# ✅ Working
- Basic MCP tool execution
- Auth tool creation
- Resource listing

# ❌ Missing
- Advanced error handling
- Async operations
- Streaming responses
- MCP server health checks
- Timeout handling
```

#### Claude Code Implementation
```typescript
✅ Rich error messages with suggestions
✅ Async/await for server calls
✅ Streaming resource downloads
✅ Server health monitoring
✅ Timeouts + retry logic
```

**Effort**: 2-3 days  
**Impact**: Medium - improves MCP reliability

---

## 📊 Summary: Gap Analysis

### By Severity

**🔴 CRITICAL (Block workflows)**
- AskUser: Preview + Annotations
- Bash: Semantic analysis + Output collapsing
- Task: Dependencies + Blocking

**🟠 HIGH (Improve UX)**
- SendMessage: Async + Streaming
- Task: Enhanced metadata + owner tracking
- Bash: Progress display

**🟡 MEDIUM (Polish)**
- Skill: Validation + Error handling
- Config: Schema validation
- MCP: Error handling + Async
- PowerShell: Command semantics

---

## 🎯 Recommended Implementation Order

### Sprint 1 (This Week): Critical Path
```
1. AskUser (Preview + Annotations)      ← FIRST
   - 2-3 days
   - Unblocks visual decision workflows
   
2. Bash (Semantic Analysis)              ← PARALLEL
   - 2-3 days
   - Improves output UX significantly
```

### Sprint 2 (Next Week): Dependencies
```
3. Task (Dependencies + Blocking)        ← AFTER Sprint 1
   - 2-3 days
   - Needed for complex workflows
   
4. SendMessage (Async)                   ← PARALLEL
   - 1-2 days
   - Supports background notifications
```

### Sprint 3+: Polish
```
5. Skill (Validation)
6. Config (Schema)
7. MCP (Error handling)
8. PowerShell (Semantics)
```

---

## 📋 Implementation Checklist

### AskUser (Preview + Annotations)
- [ ] Add `preview: Optional[str]` to QuestionOption
- [ ] Add `annotations` to response schema
- [ ] Add `metadata` tracking
- [ ] Implement uniqueness validation
- [ ] Update frontend to show preview side-by-side
- [ ] Update frontend for notes input
- [ ] Test with visual mockups
- [ ] Document preview format (markdown)

### Bash (Semantic Analysis)
- [ ] Create command classifier module
- [ ] Implement pipeline parser (handle pipes, redirects)
- [ ] Build SEARCH/READ/LIST command sets
- [ ] Add progress display logic
- [ ] Create output formatter (with collapsing)
- [ ] Add sed parser + destructive warnings
- [ ] Test with complex pipelines
- [ ] Update result message format

### Task (Dependencies)
- [ ] Extend TaskRecord with blocked_by, blocks
- [ ] Add owner + active_form fields
- [ ] Implement state machine validation
- [ ] Update TaskList to show available vs blocked
- [ ] Update TaskUpdate to handle dependencies
- [ ] Add TaskGet to return blocking info
- [ ] Test dependency graphs
- [ ] Document blocking workflow

