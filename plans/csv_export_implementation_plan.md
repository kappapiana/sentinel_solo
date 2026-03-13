# CSV Export Implementation Plan - Sentinel Solo Time-Tracking Application

## Executive Summary

This document outlines the implementation plan for adding CSV export functionality to the Sentinel Solo time-tracking application. This enhancement provides users with an alternative export format optimized for spreadsheet compatibility, complementing the existing JSON export feature.

---

## 1. Current Export Mechanism Analysis

### 1.1 Existing JSON Export Architecture

The current timesheet export system is implemented across two primary files:

**[`main.py`](main.py:3436-3900) - UI Layer:**
- Timesheet tab builder at [`_build_timesheet_tab()`](main.py:3436)
- Export controls include:
  - Matter selection checkboxes with parent/child hierarchy support
  - Search field for filtering matters
  - "Only not invoiced" checkbox (default: True)
  - "Export all users' time" checkbox (admin only)
  - Export directory text field with default to Downloads or `exports/` folder
  - Preview button and "Export timesheet" button

**[`database_manager.py`](database_manager.py:989-1065) - Data Layer:**
- [`get_time_entries_for_export()`](database_manager.py:989) method returns list of dicts with fields:
  - `id`: Time entry ID
  - `matter_id`: Associated matter ID
  - `matter_path`: Full hierarchical path (e.g., "Client > Matter")
  - `description`: Entry description
  - `start_time`: ISO format datetime
  - `end_time`: ISO format datetime
  - `duration_seconds`: Duration in seconds
  - `invoiced`: Boolean flag
  - `amount_eur`: Calculated amount based on rate
  - `rate_source`: Source of rate (user_matter, matter, upper_matter, user)
  - `owner_id`: User ID (admin/export_all_users only)

**Export Flow:**
1. User selects matters via checkboxes
2. Configure export options (invoiced filter, all users)
3. Click "Preview" to see entries or "Export timesheet" to save
4. File saved as `timesheet_YYYYMMDD_HHMMSS.json`
5. Optional dialog to mark exported entries as invoiced

### 1.2 Key Design Patterns

- **No FilePicker**: Uses text field for export path (avoids Flet client compatibility issues)
- **Persistent Settings**: Export directory saved in `page.data` for session persistence
- **Dual Output**: Preview shows entries; Export writes to file
- **Invoicing Integration**: Optional post-export invoicing flag update

---

## 2. CSV Export Design and Structure

### 2.1 Proposed CSV Format

```csv
id,matter_id,matter_path,description,start_time,end_time,duration_seconds,duration_hhmm,invoiced,amount_eur,rate_source,owner_id
1234,567,"Client A > Project X","Legal consultation",2024-03-15T14:30:00,2024-03-15T16:45:00,8100,2:15,false,450.00,matter,101
```

### 2.2 Column Specifications

| Column | Type | Format | Description |
|--------|------|--------|-------------|
| `id` | Integer | Raw | Time entry database ID |
| `matter_id` | Integer | Raw | Matter database ID |
| `matter_path` | String | CSV-escaped | Full hierarchical path (quotes if contains comma) |
| `description` | String | CSV-escaped | Entry description |
| `start_time` | DateTime | ISO 8601 | Start timestamp |
| `end_time` | DateTime | ISO 8601 | End timestamp |
| `duration_seconds` | Integer | Raw | Duration in seconds |
| `duration_hhmm` | String | H:MM or HH:MM | Human-readable duration (new column) |
| `invoiced` | Boolean | true/false | Invoicing status |
| `amount_eur` | Decimal | 2 decimal places | Calculated amount in EUR |
| `rate_source` | String | Raw | Rate source identifier |
| `owner_id` | Integer | Raw | User ID (admin/export_all_users only) |

### 2.3 CSV Format Considerations

**Encoding:** UTF-8 with BOM (recommended for Excel compatibility)
**Line Endings:** CRLF (Windows-standard, Excel-friendly)
**Delimiter:** Comma (`,`)
**Quote Character:** Double quote (`"`)
**Escape Method:** Double-quote escaping per RFC 4180

### 2.4 Enhanced Columns for Spreadsheet Usability

Add two new computed columns to improve spreadsheet usability:

1. **`duration_hhmm`**: Human-readable duration (e.g., "2:15" or "12:30")
   - Computed from `duration_seconds` using existing [`format_elapsed_hm()`](main.py:62) function
   
2. **`date`**: Extracted date portion from start_time
   - Format: YYYY-MM-DD
   - Enables easy date-based filtering in spreadsheets

### 2.5 Data Transformation Requirements

| Source Field | CSV Column | Transformation |
|--------------|------------|----------------|
| `id` | `id` | None |
| `matter_id` | `matter_id` | None |
| `matter_path` | `matter_path` | CSV escaping |
| `description` | `description` | CSV escaping |
| `start_time` | `start_time` | Keep ISO format |
| `end_time` | `end_time` | Keep ISO format |
| `duration_seconds` | `duration_seconds` | None |
| `duration_seconds` | `duration_hhmm` | Convert via `format_elapsed_hm()` |
| `invoiced` | `invoiced` | Boolean to string (true/false) |
| `amount_eur` | `amount_eur` | Format to 2 decimal places |
| `rate_source` | `rate_source` | None |
| `owner_id` | `owner_id` | None (conditional inclusion) |

---

## 3. UI Integration Approach

### 3.1 Flet-Based Desktop Considerations

**Constraints:**
- FilePicker control causes "Unknown control" errors on some Flet clients
- Solution: Use text field for export path (already implemented for JSON)
- CSV format should be consistent with JSON export UX

### 3.2 Proposed UI Changes

#### Option A: Separate Export Button (Recommended)

Add a new button alongside existing export controls:

```
[Preview] [Export timesheet (JSON)] [Export timesheet (CSV)]
```

**Advantages:**
- Clear separation of formats
- Minimal UI changes
- Users can choose format explicitly
- Consistent with "Quick Win" approach

#### Option B: Format Dropdown

Add format selector to export controls:

```
Format: [JSON ▼]  [Preview] [Export timesheet]
```

**Advantages:**
- More compact UI
- Clearer relationship between formats
- Easier to maintain single export logic

### 3.3 Recommended Implementation (Option A)

**Location:** [`_build_timesheet_tab()`](main.py:3436) in main.py

**UI Layout Update:**
```python
# After existing export buttons (line ~3890-3892)
ft.Row(
    [
        ft.ElevatedButton("Preview", icon=ft.Icons.LIST, on_click=_do_preview),
        ft.ElevatedButton("Export timesheet (JSON)", icon=ft.Icons.UPLOAD, on_click=_do_export_json),
        ft.ElevatedButton("Export timesheet (CSV)", icon=ft.Icons.TABLE_CHART, on_click=_do_export_csv),
    ],
    spacing=12,
)
```

**Rationale:**
- Explicit format naming reduces user confusion
- Mirror existing JSON button placement for consistency
- Minimal code duplication through shared logic

### 3.4 Export Dialog Integration

The existing "mark as invoiced" dialog should apply to CSV exports as well:

```python
# After successful CSV export, show same confirmation dialog
if _write_and_confirm_csv_export(out_path, payload, entry_ids):
    # Same invoicing dialog logic as JSON export
```

---

## 4. Technical Implementation Details

### 4.1 File Structure

```
sentinel_solo/
├── main.py                          # UI layer - add CSV export handler
├── database_manager.py              # Data layer - no changes needed
├── utils.py                         # Add CSV formatting helper
└── exports/                         # Default export directory (existing)
    └── timesheet_YYYYMMDD_HHMMSS.csv
```

### 4.2 Code Organization

#### A. Add CSV Helper Function to [`utils.py`](utils.py:1-653)

```python
import csv
from io import StringIO
from datetime import datetime

def format_time_hm(seconds: float) -> str:
    """Format seconds as H:MM or HH:MM (no seconds)."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}:{m:02d}"

def format_amount_eur(amount: float) -> str:
    """Format amount as string with 2 decimal places."""
    return f"{amount:.2f}"

def entries_to_csv(entries: list[dict]) -> str:
    """Convert time entry dicts to CSV string with UTF-8 BOM."""
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    
    # Write header
    writer.writerow([
        'id', 'matter_id', 'matter_path', 'description',
        'start_time', 'end_time', 'duration_seconds', 'duration_hhmm',
        'invoiced', 'amount_eur', 'rate_source', 'owner_id'
    ])
    
    # Write data rows
    for entry in entries:
        duration_hm = format_time_hm(entry['duration_seconds'])
        invoiced_str = 'true' if entry['invoiced'] else 'false'
        amount_str = format_amount_eur(entry['amount_eur'])
        
        writer.writerow([
            entry['id'],
            entry['matter_id'],
            entry['matter_path'],
            entry['description'],
            entry['start_time'],
            entry['end_time'],
            entry['duration_seconds'],
            duration_hm,
            invoiced_str,
            amount_str,
            entry['rate_source'],
            entry.get('owner_id', '')
        ])
    
    # Add UTF-8 BOM and return
    return '\ufeff' + output.getvalue()
```

#### B. Modify [`main.py`](main.py:3436) - Timesheet Tab

**Changes Required:**

1. **Add CSV export handler function** (after `_write_and_confirm_export` at line ~3727):
   ```python
   def _write_and_confirm_csv_export(out_path: Path, payload: dict, entry_ids: list) -> bool:
       """Write payload to CSV and show mark-as-invoiced dialog."""
       from utils import entries_to_csv
       
       try:
           csv_content = entries_to_csv(payload['entries'])
           out_path.write_text(csv_content, encoding='utf-8-sig')
       except OSError as err:
           page.snack_bar = ft.SnackBar(content=ft.Text(f"Could not save file: {err}"))
           page.snack_bar.open = True
           page.update()
           return False
       
       _show_mark_invoiced_dialog(out_path, entry_ids)
       return True
   ```

2. **Add CSV export function** (after `_do_export` at line ~3750):
   ```python
   def _do_export_csv(_):
       """Export selected time entries as CSV."""
       export_all_users = (
           export_all_users_ref.current.value if export_all_users_ref.current else False
       )
       if not export_all_users and not timesheet_selected_ids:
           page.snack_bar = ft.SnackBar(content=ft.Text("Select at least one matter"))
           page.snack_bar.open = True
           page.update()
           return
       
       only_not_invoiced = (
           only_not_invoiced_ref.current.value if only_not_invoiced_ref.current else True
       )
       entries = self.db.get_time_entries_for_export(
           timesheet_selected_ids,
           only_not_invoiced=only_not_invoiced,
           export_all_users=export_all_users,
       )
       
       if not entries:
           page.snack_bar = ft.SnackBar(
               content=ft.Text(
                   "No time entries to export."
                   if export_all_users
                   else "No matching time entries for the selected matters."
               )
           )
           page.snack_bar.open = True
           page.update()
           return
       
       export_time = datetime.now().isoformat()
       payload = {
           "exported_at": export_time,
           "only_not_invoiced": only_not_invoiced,
           "entries": entries,
       }
       entry_ids = [e["id"] for e in entries]
       timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
       default_name = f"timesheet_{timestamp}.csv"
       
       dir_str = (export_dir_ref.current.value or "").strip() if export_dir_ref.current else ""
       export_dir = Path(dir_str).expanduser() if dir_str else _default_export_dir()
       
       try:
           export_dir.mkdir(parents=True, exist_ok=True)
       except OSError as err:
           page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid save folder: {err}"))
           page.snack_bar.open = True
           page.update()
           return
       
       out_path = export_dir / default_name
       if _write_and_confirm_csv_export(out_path, payload, entry_ids):
           if page.data is None:
               page.data = {}
           page.data["timesheet_export_dir"] = str(export_dir)
       page.update()
   ```

3. **Update button layout** (around line 3890-3892):
   - Add "Export timesheet (CSV)" button
   - Consider renaming existing "Export timesheet" to "Export timesheet (JSON)" for clarity

### 4.3 Shared Logic Optimization

To minimize code duplication, consider extracting common export logic:

```python
def _prepare_export_data(matter_ids: set[int], only_not_invoiced: bool, export_all_users: bool) -> tuple[list[dict], list[int]]:
    """Common preparation logic for JSON and CSV exports."""
    entries = self.db.get_time_entries_for_export(
        matter_ids,
        only_not_invoiced=only_not_invoiced,
        export_all_users=export_all_users,
    )
    
    if not entries:
        return [], []
    
    payload = {
        "exported_at": datetime.now().isoformat(),
        "only_not_invoiced": only_not_invoiced,
        "entries": entries,
    }
    entry_ids = [e["id"] for e in entries]
    
    return payload, entry_ids
```

---

## 5. Testing Considerations

### 5.1 Unit Test Requirements

**Test File:** `tests/test_csv_export.py` (new file) or extend existing test file

#### Test Cases:

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_csv_format_header` | Verify CSV header matches specification | Correct column order and names |
| `test_csv_duration_format` | Verify duration conversion (seconds → HH:MM) | "8100" seconds → "2:15" |
| `test_csv_boolean_format` | Verify boolean to string conversion | True → "true", False → "false" |
| `test_csv_amount_format` | Verify amount formatting | 450.0 → "450.00" |
| `test_csv_escape_commas` | Verify CSV escaping for fields with commas | `"Client, A"` properly quoted |
| `test_csv_utf8_bom` | Verify UTF-8 BOM is included | File starts with `\ufeff` |
| `test_csv_empty_description` | Verify empty descriptions handled | Empty field between delimiters |
| `test_csv_owner_id_exclusion` | Verify owner_id not included for non-admin | Empty or omitted column |

### 5.2 Integration Test Requirements

**Test File:** Extend `tests/test_database_manager.py` or create new integration tests

#### Test Cases:

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_csv_export_single_user` | Export time entries for single user | All entries exported correctly |
| `test_csv_export_admin_all_users` | Admin exports all users' entries | Entries from all users included |
| `test_csv_export_selected_matters` | Export only selected matters | Only entries in selected matters |
| `test_csv_export_only_not_invoiced` | Filter to only non-invoiced entries | Invoiced entries excluded |
| `test_csv_export_mark_invoiced` | Export then mark as invoiced | Entries marked after export |

### 5.3 Manual Testing Checklist

- [ ] Export CSV with various matter selections
- [ ] Verify file opens correctly in Excel, LibreOffice Calc, Google Sheets
- [ ] Test with descriptions containing commas and quotes
- [ ] Test with empty descriptions
- [ ] Test admin export of all users' data
- [ ] Verify "mark as invoiced" dialog appears after CSV export
- [ ] Test export to custom directory path
- [ ] Test export when no matters selected (error handling)
- [ ] Test export when no matching entries (error handling)

### 5.4 Cross-Platform Compatibility

**Testing Matrix:**

| Platform | Spreadsheet Application | Notes |
|----------|------------------------|-------|
| Windows | Microsoft Excel | Primary target - UTF-8 BOM ensures proper encoding |
| Windows | LibreOffice Calc | Verify CSV parsing |
| Linux | LibreOffice Calc | Default on most Linux distros |
| macOS | Numbers | Test UTF-8 BOM handling |
| Any | Google Sheets | Import CSV and verify formatting |

---

## 6. Technical Considerations Specific to This Codebase

### 6.1 Flet-Specific Considerations

1. **No FilePicker**: The existing approach using text field for export path should be reused for CSV exports
2. **Icon Selection**: Use `ft.Icons.TABLE_CHART` or `ft.Icons.TABLE_VIEW` for CSV button icon
3. **Dialog Reuse**: The existing `_show_mark_invoiced_dialog()` can be reused without modification

### 6.2 Database Considerations

- **No schema changes required**: CSV export uses existing data from `get_time_entries_for_export()`
- **PostgreSQL RLS**: Admin export logic already handles role-based security
- **SQLite unscoped queries**: Already handled in existing implementation

### 6.3 Performance Considerations

- **Memory**: CSV generation happens in-memory via StringIO; acceptable for typical timesheet sizes (<10,000 entries)
- **File I/O**: Same pattern as JSON export; no performance concerns
- **Large exports**: If needed, could implement streaming CSV writer for very large datasets

### 6.4 Backward Compatibility

- **JSON export unchanged**: Existing functionality remains intact
- **Export directory persistence**: Reuses existing `page.data["timesheet_export_dir"]` storage
- **File naming convention**: Maintains consistent timestamp-based naming pattern

---

## 7. Implementation Steps Summary

### Phase 1: Core Implementation (Quick Win)

1. **Add CSV helper functions to [`utils.py`](utils.py)**
   - `format_time_hm()` - duration formatting
   - `format_amount_eur()` - amount formatting  
   - `entries_to_csv()` - main CSV generation

2. **Modify [`main.py`](main.py) timesheet tab**
   - Add `_write_and_confirm_csv_export()` function
   - Add `_do_export_csv()` handler
   - Update button layout to include CSV export button

3. **Testing**
   - Unit tests for CSV formatting functions
   - Integration tests for export flow
   - Manual testing across platforms

### Phase 2: Optional Enhancements (Future)

- Format dropdown instead of separate buttons
- Custom column selection for CSV export
- Export preview in spreadsheet-like grid view
- Batch export with date range filtering

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| UTF-8 BOM causes issues in some tools | Low | Medium | Document that BOM is for Excel compatibility; can be made optional |
| CSV escaping issues with special characters | Low | Medium | Use Python's csv module (RFC 4180 compliant) |
| Flet icon not available on all platforms | Low | Low | Provide fallback text label |
| Code duplication between JSON/CSV handlers | Medium | Low | Extract shared logic into helper functions |

---

## 9. Success Criteria

- [ ] CSV export button appears in timesheet tab alongside JSON export
- [ ] Exported CSV file opens correctly in Excel and other spreadsheet applications
- [ ] All time entry fields are properly formatted and escaped
- [ ] "Mark as invoiced" dialog appears after CSV export (same as JSON)
- [ ] Admin export of all users' data works for CSV format
- [ ] Unit tests pass for CSV formatting functions
- [ ] No regression in existing JSON export functionality

---

## 10. Appendix: Sample CSV Output

```csv
"id","matter_id","matter_path","description","start_time","end_time","duration_seconds","duration_hhmm","invoiced","amount_eur","rate_source","owner_id"
"1234","567","Acme Corp > Website Redesign","Initial consultation meeting","2024-03-15T14:30:00","2024-03-15T16:45:00","8100","2:15","false","450.00","matter","101"
"1235","567","Acme Corp > Website Redesign","Code review and testing","2024-03-16T09:00:00","2024-03-16T12:30:00","12600","3:30","false","700.00","user_matter","101"
```

---

**Document Version:** 1.0  
**Created:** 2026-03-13  
**Status:** Ready for review and approval
