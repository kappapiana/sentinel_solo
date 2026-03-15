# Sentinel Solo - Implementation Roadmap

**Last Updated:** 2026-03-15  
**Current Version:** v0.4.0

---

## Current State

Sentinel Solo is a production-ready time-tracking application with:
- Multi-user support with PostgreSQL Row Level Security (RLS)
- Hierarchical matter structure (clients → projects → subprojects)
- Timer functionality and manual time entry
- Hourly rate resolution with 4-level precedence
- Budget tracking and invoicing support
- JSON export for timesheets

---

## Active Plans

### 1. CSV Export Implementation ✅ (Plan Ready)
**Status:** Fully documented, not yet implemented  
**Priority:** High  
**Effort:** Medium (2-4 hours)  
**Impact:** High - Spreadsheet compatibility for users

**Description:** Add CSV export functionality to complement the existing JSON export. This provides users with an alternative export format optimized for spreadsheet compatibility.

**Implementation Steps:**
1. Add CSV export handler in `_build_timesheet_tab()` (main.py)
2. Create CSV formatting helper in utils.py
3. Add "Export timesheet (CSV)" button alongside existing JSON export
4. Format: UTF-8 with BOM, CRLF line endings, RFC 4180 compliant
5. Include enhanced columns: `duration_hhmm`, `date`

**Files:**
- [`plans/csv_export_implementation_plan.md`](csv_export_implementation_plan.md) - Complete implementation plan

---

### 2. Test Optimization ✅ (Plan Ready)
**Status:** Fully documented, not yet implemented  
**Priority:** Medium  
**Effort:** Medium (3-5 hours)  
**Impact:** High - Faster CI/CD feedback loops

**Description:** Optimize the test suite for parallel execution and selective test runs to improve development velocity.

**Implementation Steps:**
1. Add `pytest-xdist` for parallel execution
2. Implement session-scoped fixtures for database templates
3. Add pytest markers (unit, integration, regression, slow)
4. Optimize database isolation for parallel tests

**Files:**
- [`plans/test_optimization_plan.md`](test_optimization_plan.md) - Complete optimization plan

---

### 3. Codebase Analysis & Enhancements ✅ (Analysis Complete)
**Status:** Analysis document exists  
**Priority:** Low (Ongoing)  
**Effort:** Varies  
**Impact:** Varies

**Description:** Comprehensive analysis of the codebase with feature enhancement opportunities identified.

**Key Findings:**
- Architecture is solid and extensible
- Test coverage is comprehensive
- Enhancement opportunities identified for future development

**Files:**
- [`plans/sentinel_solo_analysis_and_enhancements.md`](sentinel_solo_analysis_and_enhancements.md) - Feature suggestions and architectural improvements

---

## Implementation Priority

### Phase 1: CSV Export (Immediate)
- **Why:** User-facing feature, well-documented plan, minimal risk
- **Delegation:** Code mode implementation
- **Dependencies:** None

### Phase 2: Test Optimization (After CSV Export)
- **Why:** Improves development velocity, enables better CI
- **Delegation:** Code mode with debug mode for test issues
- **Dependencies:** CSV export implementation (optional - can run in parallel)

### Phase 3: Enhancement Prioritization (Ongoing)
- **Why:** Long-term roadmap based on user needs
- **Delegation:** Architect mode for detailed planning
- **Dependencies:** None - can be done at any time

---

## Documentation Files

| File | Purpose | Status |
|------|---------|--------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System architecture documentation | Current |
| [`README.md`](README.md) | User documentation | Current |
| [`plans/csv_export_implementation_plan.md`](csv_export_implementation_plan.md) | CSV export implementation plan | Ready |
| [`plans/test_optimization_plan.md`](test_optimization_plan.md) | Test optimization plan | Ready |
| [`plans/sentinel_solo_analysis_and_enhancements.md`](sentinel_solo_analysis_and_enhancements.md) | Codebase analysis | Current |
| [`plans/sentinel_solo_codebase_summary.md`](sentinel_solo_codebase_summary.md) | Codebase summary | Current |

---

## Quick Start for New Developers

1. Review [`ARCHITECTURE.md`](ARCHITECTURE.md) for system overview
2. Read [`README.md`](README.md) for user-facing features
3. Check [`plans/IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for current priorities
4. Review specific implementation plans in [`plans/`](.) directory

---

## How to Contribute

1. Pick a task from the Implementation Priority list
2. Review the corresponding plan document
3. Implement in Code mode
4. Run tests: `pytest tests/ -v`
5. Update documentation as needed
