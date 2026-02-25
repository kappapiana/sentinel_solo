"""
Sentinel Solo: Flet UI with Timer and Manage Matters.
Multi-user: login required; each user sees only their matters and time entries.
"""
import asyncio
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

import flet as ft
import bcrypt

from sqlalchemy.exc import IntegrityError

from database_manager import DatabaseManager, db

__version__ = "v0.1.2"

# Storage keys for persisted login (optional restore)
STORAGE_USER_ID = "user_id"
STORAGE_USERNAME = "username"

DATETIME_FMT = "%Y-%m-%d %H:%M"
TIME_FMT = "%H:%M"


# Rate source colors for chargeable amounts: user_matter=teal, matter=green, upper_matter=orange, user=red
def _rate_source_color(source: str) -> str:
    if source == "user_matter":
        return "teal"
    if source == "matter":
        return "green"
    if source == "upper_matter":
        return "orange"
    return "red"  # user


def format_eur(amount: float) -> str:
    """Format amount in EUR for display."""
    return f"€ {amount:.2f}"


def format_elapsed(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_elapsed_hm(seconds: float) -> str:
    """Format seconds as H:MM or HH:MM (no seconds). For Today's activities duration."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}:{m:02d}"


def format_datetime(dt: datetime | None) -> str:
    """Format for display and editing."""
    if dt is None:
        return ""
    return dt.strftime(DATETIME_FMT)


def format_time(dt: datetime | None) -> str:
    """Time-only HH:MM for day-activity rows."""
    if dt is None:
        return ""
    return dt.strftime(TIME_FMT)


def parse_time(s: str) -> time | None:
    """Parse HH:MM or H:MM; return time or None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, TIME_FMT).time()
    except ValueError:
        return None


def parse_datetime(s: str) -> datetime | None:
    """Parse YYYY-MM-DD HH:MM."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, DATETIME_FMT)
    except ValueError:
        return None


def parse_duration_hours(s: str) -> float | None:
    """Parse duration as decimal hours (e.g. 1.5) or H:MM / HH:MM."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        if ":" in s:
            parts = s.split(":")
            h = int(parts[0].strip())
            m = int(parts[1].strip()) if len(parts) > 1 else 0
            return h + m / 60.0
        return float(s)
    except (ValueError, IndexError):
        return None


def _compute_third_time_static(start_s: str, end_s: str, duration_s: str) -> tuple[datetime | None, datetime | None, float | None]:
    """From two of start/end/duration (parsed), return (start, end, duration_seconds). Shared for timer and matters."""
    start = parse_datetime(start_s)
    end = parse_datetime(end_s)
    dur_h = parse_duration_hours(duration_s)
    dur_sec = dur_h * 3600.0 if dur_h is not None else None
    if start is not None and end is not None:
        return (start, end, (end - start).total_seconds())
    if start is not None and dur_sec is not None:
        return (start, start + timedelta(seconds=dur_sec), dur_sec)
    if end is not None and dur_sec is not None:
        return (end - timedelta(seconds=dur_sec), end, dur_sec)
    return (None, None, None)


class SentinelApp:
    """Flet UI: holds page, db, refs, and state; tab builders are methods."""

    def __init__(self, page: ft.Page, db_instance: DatabaseManager) -> None:
        self.page = page
        self.db = db_instance
        self.timer_label_ref: ft.Ref[ft.Text] = ft.Ref()
        self.matter_dropdown_ref: ft.Ref[ft.Column] = ft.Ref()
        self.running_ref: list[bool] = [False]
        self.start_time_ref: list[datetime | None] = [None]
        self.matters_list_ref: ft.Ref[ft.Column] = ft.Ref()
        self.body_ref: ft.Ref[ft.Container] = ft.Ref()
        self.expanded_clients: set[str] = set()

    def setup(
        self,
        *,
        logout_callback: Callable[[], None] | None = None,
        current_username: str = "",
        current_user_is_admin: bool = False,
    ) -> None:
        page = self.page
        page.theme_mode = ft.ThemeMode.DARK
        page.title = f"Sentinel Solo {__version__} - {current_username}"
        page.padding = 24

        timer_tab = self._build_timer_tab()

        def refresh_timer_dropdown():
            refresh = (page.data or {}).get("refresh_timer_matters")
            if refresh:
                refresh()
            refresh_activities = (page.data or {}).get("refresh_timer_activities")
            if refresh_activities:
                refresh_activities()

        matters_tab = self._build_matters_tab(refresh_timer_dropdown)

        def on_toggle_client(client_name: str):
            self.expanded_clients.symmetric_difference_update([client_name])
            reporting_container.content = self._build_reporting_tab(on_toggle_client)
            page.update()

        if page.data is None:
            page.data = {}
        page.data["reporting_sort"] = page.data.get("reporting_sort") or "most_uninvoiced"

        def refresh_reporting():
            reporting_container.content = self._build_reporting_tab(on_toggle_client)
            page.update()

        page.data["refresh_reporting"] = refresh_reporting

        reporting_tab = self._build_reporting_tab(on_toggle_client)
        timesheet_tab = self._build_timesheet_tab()
        users_container = (
            ft.Container(content=self._build_users_tab(), expand=True)
            if current_user_is_admin
            else None
        )
        timer_container = ft.Container(content=timer_tab, expand=True)
        matters_container = ft.Container(content=matters_tab, expand=True)
        reporting_container = ft.Container(content=reporting_tab, expand=True)
        timesheet_container = ft.Container(content=timesheet_tab, expand=True)

        def show_timer(_):
            self.body_ref.current.content = timer_container
            refresh = (page.data or {}).get("refresh_timer_matters")
            if refresh:
                refresh()
            refresh_activities = (page.data or {}).get("refresh_timer_activities")
            if refresh_activities:
                refresh_activities()
            page.update()

        def show_matters(_):
            self.body_ref.current.content = matters_container
            page.update()

        def show_reporting(_):
            reporting_container.content = self._build_reporting_tab(on_toggle_client)
            self.body_ref.current.content = reporting_container
            page.update()

        def show_timesheet(_):
            self.body_ref.current.content = timesheet_container
            refresh = (page.data or {}).get("refresh_timesheet_matters")
            if refresh:
                refresh()
            page.update()

        def show_users(_):
            if users_container is not None:
                self.body_ref.current.content = users_container
                page.update()

        def on_rail_change(e):
            idx = e.control.selected_index
            if idx == 0:
                show_timer(e)
            elif idx == 1:
                show_matters(e)
            elif idx == 2:
                show_reporting(e)
            elif idx == 3:
                show_timesheet(e)
            elif current_user_is_admin and idx == 4:
                show_users(e)

        destinations = [
            ft.NavigationRailDestination(
                icon=ft.Icons.TIMER,
                selected_icon=ft.Icons.TIMER,
                label="Timer",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.FOLDER_OPEN,
                selected_icon=ft.Icons.FOLDER_OPEN,
                label="Manage Matters",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.ASSESSMENT,
                selected_icon=ft.Icons.ASSESSMENT,
                label="Reporting",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.UPLOAD,
                selected_icon=ft.Icons.UPLOAD,
                label="Timesheet",
            ),
        ]
        if current_user_is_admin:
            destinations.append(
                ft.NavigationRailDestination(
                    icon=ft.Icons.PEOPLE,
                    selected_icon=ft.Icons.PEOPLE,
                    label="Users",
                ),
            )
        if logout_callback:
            destinations.append(
                ft.NavigationRailDestination(
                    icon=ft.Icons.LOGOUT,
                    selected_icon=ft.Icons.LOGOUT,
                    label="Log out",
                ),
            )
        if page.data is None:
            page.data = {}
        page.data["logout_callback"] = logout_callback
        rail = ft.NavigationRail(
            selected_index=0,
            extended=True,
            min_extended_width=180,
            label_type=ft.NavigationRailLabelType.ALL,
            destinations=destinations,
            on_change=on_rail_change,
        )

        async def _do_logout(_):
            await page.shared_preferences.set(STORAGE_USER_ID, "")
            await page.shared_preferences.set(STORAGE_USERNAME, "")
            if logout_callback:
                logout_callback()

        def _on_rail_change_with_logout(e):
            if logout_callback and e.control.selected_index == len(destinations) - 1:
                e.control.selected_index = 0
                page.update()
                page.run_task(_do_logout, e)
                return
            on_rail_change(e)

        rail.on_change = _on_rail_change_with_logout

        body = ft.Container(ref=self.body_ref, content=timer_container, expand=True)

        top_bar = ft.Row(
            [
                ft.Text(
                    f"Logged in as {current_username}",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            alignment=ft.MainAxisAlignment.END,
            tight=True,
        )

        page.add(
            ft.Column(
                [
                    top_bar,
                    ft.Row(
                        [
                            rail,
                            ft.VerticalDivider(width=1),
                            body,
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
            )
        )

    def _build_timer_tab(self) -> ft.Control:
        """Build the Timer tab: searchable folded matter list, task description, Start/Stop, live-updating label."""
        page = self.page
        timer_label = self.timer_label_ref
        matter_dropdown = self.matter_dropdown_ref
        running_ref = self.running_ref
        start_time_ref = self.start_time_ref
        timer_label = self.timer_label_ref

        def _on_continue_task(entry_id: int):
            """Create a new running entry with same matter/description (Continue task) and start timer UI."""
            try:
                new_entry = self.db.continue_time_entry(entry_id)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                page.update()
                return
            refresh = (page.data or {}).get("refresh_timer_activities")
            if callable(refresh):
                refresh()
            start_time_ref[0] = new_entry.start_time
            running_ref[0] = True
            # Force timer mode so Start/Stop and timer box are visible when continuing.
            set_mode = (page.data or {}).get("_timer_set_mode_callback")
            if callable(set_mode):
                set_mode(False)
            if timer_label.current:
                timer_label.current.value = "00:00:00"
            start_time_section_ref = (page.data or {}).get("_timer_start_time_section_ref")
            start_time_field_ref = (page.data or {}).get("_timer_start_time_field_ref")
            desc_ref = (page.data or {}).get("_timer_description_ref")
            if start_time_section_ref and start_time_section_ref.current:
                start_time_section_ref.current.visible = True
            if start_time_field_ref and start_time_field_ref.current:
                start_time_field_ref.current.value = format_datetime(start_time_ref[0])
            if desc_ref and desc_ref.current:
                desc_ref.current.value = (new_entry.description or "").strip()
            page.run_task(timer_loop)
            page.snack_bar = ft.SnackBar(ft.Text("Continued task; timer running."), open=True)
            page.update()

        # Selectable matters only (non-roots); used for selection and search
        options = self.db.get_matters_with_full_paths(for_timer=True)
        timer_matter_selected: list = [options[0][0], options[0][1]] if options else [None, None]
        # All matters (including roots) so every client appears as a section header even with 0 matters
        options_all = self.db.get_matters_with_full_paths(for_timer=False)

        def _options_by_client_timer(opts: list[tuple[int, str]]) -> dict:
            """Group by client (first path segment). Only non-root matters go into lists."""
            by_client = defaultdict(list)
            for mid, path in opts:
                client = path.split(" > ")[0] if " > " in path else path
                by_client[client].append((mid, path))
            for client in by_client:
                by_client[client].sort(key=lambda x: x[1])
            return by_client

        def _by_client_include_all_clients() -> dict:
            """Like _options_by_client_timer but includes every client (root) as a key so clients with 0 matters appear."""
            by_client = _options_by_client_timer(options)
            for mid, path in options_all:
                if " > " not in path:
                    by_client.setdefault(path, [])
            return by_client

        _by_client_initial = _by_client_include_all_clients()
        timer_matter_expanded: set = set(_by_client_initial.keys())
        timer_matter_search_ref = ft.Ref[ft.TextField]()
        timer_matter_list_ref = matter_dropdown
        timer_matter_selection_ref = ft.Ref[ft.Text]()

        def _build_timer_matter_list(query: str):
            q = (query or "").strip().lower()
            if q:
                flat = [(mid, path) for mid, path in options if path and q in path.lower()][:50]
                return [
                    ft.ListTile(
                        title=ft.Text(path, size=14),
                        dense=True,
                        content_padding=2,
                        on_click=lambda e, mid=mid, path=path: _on_timer_matter_select(mid, path),
                    )
                    for mid, path in flat
                ]
            by_client = _by_client_include_all_clients()
            controls = []
            for client_name in sorted(by_client.keys()):
                items = by_client[client_name]
                is_exp = client_name in timer_matter_expanded
                controls.append(
                    ft.ListTile(
                        title=ft.Text(client_name, weight=ft.FontWeight.W_500, size=14),
                        subtitle=ft.Text(f"{len(items)} matter(s)", size=12),
                        trailing=ft.Icon(ft.Icons.EXPAND_LESS if is_exp else ft.Icons.EXPAND_MORE, size=20),
                        dense=True,
                        content_padding=2,
                        on_click=lambda e, c=client_name: _on_timer_matter_toggle(c),
                    ),
                )
                controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.ListTile(
                                    title=ft.Text(path, size=14),
                                    dense=True,
                                    content_padding=2,
                                    on_click=lambda e, mid=mid, path=path: _on_timer_matter_select(mid, path),
                                )
                                for mid, path in items
                            ],
                            spacing=0,
                        ),
                        visible=is_exp,
                        padding=ft.Padding.only(left=16, top=0, right=0, bottom=0),
                    ),
                )
            return controls

        def _on_timer_matter_toggle(client_name: str):
            timer_matter_expanded.symmetric_difference_update([client_name])
            if timer_matter_list_ref.current:
                timer_matter_list_ref.current.controls = _build_timer_matter_list(
                    timer_matter_search_ref.current.value if timer_matter_search_ref.current else ""
                )
                page.update()

        def _on_timer_matter_select(mid: int, path: str):
            timer_matter_selected[0], timer_matter_selected[1] = mid, path
            if timer_matter_selection_ref.current:
                timer_matter_selection_ref.current.value = f"Selected: {path}"
            page.update()

        def on_timer_matter_search(e):
            if timer_matter_list_ref.current and timer_matter_search_ref.current:
                timer_matter_list_ref.current.controls = _build_timer_matter_list(e.control.value or "")
                page.update()

        def refresh_timer_matter_list():
            nonlocal options, options_all
            options = self.db.get_matters_with_full_paths(for_timer=True)
            options_all = self.db.get_matters_with_full_paths(for_timer=False)
            # Keep all clients expanded so all matters from all clients are visible
            by_client = _by_client_include_all_clients()
            timer_matter_expanded.clear()
            timer_matter_expanded.update(by_client.keys())
            if options and timer_matter_selected[0] not in [mid for mid, _ in options]:
                timer_matter_selected[0], timer_matter_selected[1] = options[0][0], options[0][1]
                if timer_matter_selection_ref.current:
                    timer_matter_selection_ref.current.value = f"Selected: {options[0][1]}"
            if timer_matter_list_ref.current:
                q = timer_matter_search_ref.current.value if timer_matter_search_ref.current else ""
                timer_matter_list_ref.current.controls = _build_timer_matter_list(q)
            page.update()

        if page.data is None:
            page.data = {}
        page.data["refresh_timer_matters"] = refresh_timer_matter_list

        today = date.today()
        activities_list_ref = ft.Ref[ft.Column]()

        def _build_activities_rows() -> list[ft.Control]:
            entries = self.db.get_time_entries_for_day(today)
            path_options = self.db.get_matters_with_full_paths(for_timer=True)
            path_by_id = {mid: path for mid, path in path_options}

            def _refresh_activities():
                if activities_list_ref.current:
                    activities_list_ref.current.controls = _build_activities_rows()
                    page.update()

            rows: list[ft.Control] = []
            for entry in entries:
                entry_id = entry.id
                matter_options = [ft.DropdownOption(key=str(mid), text=path) for mid, path in path_options]
                start_val = format_time(entry.start_time)
                end_val = format_time(entry.end_time) if entry.end_time is not None else "—"
                dur_sec = entry.duration_seconds or 0.0
                if entry.end_time is None and entry.start_time:
                    dur_sec = max(0, (datetime.now() - entry.start_time).total_seconds())
                duration_val = format_elapsed_hm(dur_sec)
                desc_val = (entry.description or "").strip()

                matter_dd = ft.Dropdown(
                    value=str(entry.matter_id),
                    options=matter_options,
                    width=320,
                    on_select=lambda e, eid=entry_id: _on_activity_matter_change(eid, e.control.value),
                )
                desc_tf = ft.TextField(
                    value=desc_val,
                    width=200,
                    hint_text="Task description",
                    on_blur=lambda e, eid=entry_id: _on_activity_description_blur(eid, e.control.value),
                )
                start_tf = ft.TextField(value=start_val, width=90, on_blur=lambda e, eid=entry_id: _on_activity_start_blur(eid, e.control.value))
                end_tf = ft.TextField(value=end_val, width=90, on_blur=lambda e, eid=entry_id: _on_activity_end_blur(eid, e.control.value))
                duration_tf = ft.TextField(value=duration_val, width=100, on_blur=lambda e, eid=entry_id: _on_activity_duration_blur(eid, e.control.value))
                rate, rate_source = self.db.get_resolved_hourly_rate(entry.matter_id, entry.owner_id)
                amount_eur = self.db.amount_eur_from_seconds(dur_sec, rate)
                amount_color = _rate_source_color(rate_source)
                amount_text = ft.Text(format_eur(amount_eur), size=12, color=amount_color, width=90)

                def _on_activity_matter_change(eid: int, val: str | None):
                    if val is None:
                        return
                    try:
                        mid = int(val)
                        self.db.update_time_entry(eid, matter_id=mid)
                        page.snack_bar = ft.SnackBar(ft.Text("Matter updated."), open=True)
                    except ValueError as err:
                        page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    _refresh_activities()
                    page.update()

                def _on_activity_start_blur(eid: int, s: str):
                    entry = next((x for x in self.db.get_time_entries_for_day(today) if x.id == eid), None)
                    if not entry:
                        return
                    t = parse_time(s or "")
                    if t is None:
                        return
                    day = entry.start_time.date()
                    new_start = datetime.combine(day, t)
                    dur = entry.duration_seconds or 0.0
                    new_end = new_start + timedelta(seconds=dur)
                    if dur <= 0:
                        try:
                            self.db.delete_time_entry(eid)
                            page.snack_bar = ft.SnackBar(ft.Text("Entry removed (zero duration)."), open=True)
                        except ValueError as err:
                            page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    else:
                        try:
                            self.db.update_time_entry(eid, start_time=new_start, end_time=new_end, duration_seconds=dur)
                            page.snack_bar = ft.SnackBar(ft.Text("Start updated."), open=True)
                        except ValueError as err:
                            page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    _refresh_activities()
                    page.update()

                def _on_activity_end_blur(eid: int, s: str):
                    entry = next((x for x in self.db.get_time_entries_for_day(today) if x.id == eid), None)
                    if not entry:
                        return
                    if (s or "").strip() in ("", "—", "Running"):
                        return
                    t = parse_time(s)
                    if t is None:
                        return
                    day = entry.start_time.date()
                    new_end = datetime.combine(day, t)
                    new_dur = (new_end - entry.start_time).total_seconds()
                    if new_dur < 0:
                        page.snack_bar = ft.SnackBar(ft.Text("End must be after start."), open=True)
                        page.update()
                        return
                    if new_dur <= 0:
                        try:
                            self.db.delete_time_entry(eid)
                            page.snack_bar = ft.SnackBar(ft.Text("Entry removed (zero duration)."), open=True)
                        except ValueError as err:
                            page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    else:
                        try:
                            self.db.update_time_entry(eid, start_time=entry.start_time, end_time=new_end)
                            page.snack_bar = ft.SnackBar(ft.Text("End updated."), open=True)
                        except ValueError as err:
                            page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    _refresh_activities()
                    page.update()

                def _on_activity_duration_blur(eid: int, s: str):
                    entry = next((x for x in self.db.get_time_entries_for_day(today) if x.id == eid), None)
                    if not entry:
                        return
                    hours = parse_duration_hours(s or "")
                    if hours is None:
                        return
                    if hours < 0:
                        return
                    new_dur = hours * 3600.0
                    if new_dur <= 0:
                        try:
                            self.db.delete_time_entry(eid)
                            page.snack_bar = ft.SnackBar(ft.Text("Entry removed (zero duration)."), open=True)
                        except ValueError as err:
                            page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    else:
                        new_end = entry.start_time + timedelta(seconds=new_dur)
                        try:
                            self.db.update_time_entry(eid, start_time=entry.start_time, duration_seconds=new_dur)
                            page.snack_bar = ft.SnackBar(ft.Text("Duration updated."), open=True)
                        except ValueError as err:
                            page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    _refresh_activities()
                    page.update()

                def _on_activity_description_blur(eid: int, s: str):
                    val = (s or "").strip()
                    try:
                        self.db.update_time_entry(eid, description=val if val else None)
                        page.snack_bar = ft.SnackBar(ft.Text("Description updated."), open=True)
                    except ValueError as err:
                        page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    _refresh_activities()
                    page.update()

                continue_btn = ft.OutlinedButton(
                    content=ft.Text("Continue", size=9, no_wrap=True),
                    width=90,
                    on_click=lambda e, eid=entry_id: _on_continue_task(eid),
                )
                rows.append(
                    ft.Row(
                        [matter_dd, desc_tf, start_tf, end_tf, duration_tf, amount_text, continue_btn],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.START,
                    )
                )

            if not rows:
                return [ft.Text("No activities recorded today. Start the timer or add a manual entry below.", size=14)]
            header = ft.Row(
                [
                    ft.Text("Matter", size=12, weight=ft.FontWeight.W_500, width=320),
                    ft.Text("Description", size=12, weight=ft.FontWeight.W_500, width=200),
                    ft.Text("Start", size=12, weight=ft.FontWeight.W_500, width=90),
                    ft.Text("End", size=12, weight=ft.FontWeight.W_500, width=90),
                    ft.Text("Duration", size=12, weight=ft.FontWeight.W_500, width=100),
                    ft.Text("Amount (€)", size=12, weight=ft.FontWeight.W_500, width=90),
                    ft.Container(width=90),
                ],
                spacing=12,
            )
            return [header] + rows

        def refresh_activities():
            if activities_list_ref.current:
                activities_list_ref.current.controls = _build_activities_rows()
                page.update()

        page.data["refresh_timer_activities"] = refresh_activities

        entries_today = self.db.get_time_entries_for_day(today)
        initial_activities_controls: list[ft.Control] = (
            _build_activities_rows() if entries_today else [ft.Text("No activities recorded today. Start the timer or add a manual entry below.", size=14)]
        )
        activities_list_column = ft.Column(
            ref=activities_list_ref,
            controls=initial_activities_controls,
            scroll=ft.ScrollMode.AUTO,
        )
        activities_list_container = ft.Container(
            content=activities_list_column,
            height=240,
        )

        activities_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Today's activities", size=18, weight=ft.FontWeight.W_500),
                    ft.Container(height=6),
                    activities_list_container,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.only(bottom=8),
        )

        description_ref = ft.Ref[ft.TextField]()
        manual_desc_ref = ft.Ref[ft.TextField]()
        manual_start_ref = ft.Ref[ft.TextField]()
        manual_end_ref = ft.Ref[ft.TextField]()
        manual_duration_ref = ft.Ref[ft.TextField]()
        manual_derived_ref = ft.Ref[ft.Text]()
        timer_section_ref = ft.Ref[ft.Container]()
        manual_section_ref = ft.Ref[ft.Container]()
        start_time_field_ref = ft.Ref[ft.TextField]()
        start_time_section_ref = ft.Ref[ft.Container]()
        if page.data is None:
            page.data = {}
        page.data["_timer_start_time_section_ref"] = start_time_section_ref
        page.data["_timer_start_time_field_ref"] = start_time_field_ref
        page.data["_timer_description_ref"] = description_ref
        label = ft.Text(
            ref=timer_label,
            value="00:00:00",
            size=48,
            weight=ft.FontWeight.W_500,
        )
        start_btn = ft.ElevatedButton("Start", icon=ft.Icons.PLAY_ARROW)
        stop_btn = ft.OutlinedButton("Stop", icon=ft.Icons.STOP)
        manual_mode: list[bool] = [False]
        manual_btn_ref = ft.Ref[ft.ElevatedButton]()

        async def timer_loop():
            while running_ref[0] and start_time_ref[0]:
                await asyncio.sleep(1)
                if not running_ref[0]:
                    break
                elapsed = (datetime.now() - start_time_ref[0]).total_seconds()
                if timer_label.current:
                    timer_label.current.value = format_elapsed(elapsed)
                    page.update()

        def _get_selected_matter_id() -> int | None:
            """Return selected matter id from the matter list (same for timer and manual)."""
            return timer_matter_selected[0]

        def on_start(_):
            matter_id = _get_selected_matter_id()
            if matter_id is None:
                page.snack_bar = ft.SnackBar(ft.Text("Select a matter from the list."), open=True)
                page.update()
                return
            if running_ref[0]:
                return
            description = (description_ref.current.value or "").strip() if description_ref.current else ""
            try:
                entry = self.db.start_timer(matter_id, description=description or None)
            except ValueError as e:
                page.snack_bar = ft.SnackBar(ft.Text(str(e)), open=True)
                page.update()
                return
            start_time_ref[0] = entry.start_time
            running_ref[0] = True
            timer_label.current.value = "00:00:00"
            if start_time_section_ref.current:
                start_time_section_ref.current.visible = True
            if start_time_field_ref.current:
                start_time_field_ref.current.value = format_datetime(start_time_ref[0])
            page.run_task(timer_loop)
            page.update()

        def on_apply_start_time(_):
            if not running_ref[0] or not start_time_field_ref.current:
                return
            s = (start_time_field_ref.current.value or "").strip()
            new_start = parse_datetime(s)
            if new_start is None:
                page.snack_bar = ft.SnackBar(ft.Text("Use format YYYY-MM-DD HH:MM (e.g. 2025-02-20 09:30)"), open=True)
                page.update()
                return
            entry = self.db.update_running_entry_start_time(new_start)
            if entry is None:
                page.snack_bar = ft.SnackBar(ft.Text("No running timer to update."), open=True)
                page.update()
                return
            start_time_ref[0] = new_start
            if timer_label.current:
                timer_label.current.value = format_elapsed((datetime.now() - new_start).total_seconds())
            page.snack_bar = ft.SnackBar(ft.Text("Start time updated."), open=True)
            page.update()

        def on_description_blur(_):
            """When description field loses focus and timer is running, save to the time entry."""
            if running_ref[0] and description_ref.current:
                desc = (description_ref.current.value or "").strip()
                self.db.update_running_entry_description(desc)

        def on_stop(_):
            if not running_ref[0]:
                return
            # Save current description to the running entry before stopping
            if description_ref.current:
                desc = (description_ref.current.value or "").strip()
                self.db.update_running_entry_description(desc)
            running_ref[0] = False
            if start_time_section_ref.current:
                start_time_section_ref.current.visible = False
            entry = self.db.stop_timer()
            if entry and timer_label.current:
                timer_label.current.value = format_elapsed(entry.duration_seconds)
            refresh = page.data.get("refresh_timer_activities")
            if callable(refresh):
                refresh()
            page.update()

        def _update_manual_derived(_=None):
            """When two of Start/End/Duration are filled, compute and show the third."""
            if not manual_derived_ref.current:
                return
            start_s = manual_start_ref.current.value if manual_start_ref.current else ""
            end_s = manual_end_ref.current.value if manual_end_ref.current else ""
            dur_s = manual_duration_ref.current.value if manual_duration_ref.current else ""
            start_t, end_t, dur = _compute_third_time_static(start_s, end_s, dur_s)
            if start_t is None or end_t is None or dur is None:
                manual_derived_ref.current.value = "Fill exactly two of Start, End, Duration; the third will be shown here."
            else:
                manual_derived_ref.current.value = f"Derived: Start {format_datetime(start_t)}, End {format_datetime(end_t)}, Duration {format_elapsed(dur)}"
            page.update()

        def on_manual_add(_):
            matter_id = _get_selected_matter_id()
            if matter_id is None:
                page.snack_bar = ft.SnackBar(ft.Text("Select a matter from the list."), open=True)
                page.update()
                return
            desc = (manual_desc_ref.current.value or "").strip() if manual_desc_ref.current else ""
            start_s = manual_start_ref.current.value if manual_start_ref.current else ""
            end_s = manual_end_ref.current.value if manual_end_ref.current else ""
            dur_s = manual_duration_ref.current.value if manual_duration_ref.current else ""
            start_t, end_t, dur = _compute_third_time_static(start_s, end_s, dur_s)
            if start_t is None or end_t is None or dur is None:
                page.snack_bar = ft.SnackBar(ft.Text("Fill exactly two of Start, End, Duration."), open=True)
                page.update()
                return
            try:
                self.db.add_manual_time_entry(matter_id, desc, start_time=start_t, end_time=end_t, duration_seconds=dur)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                page.update()
                return
            if manual_desc_ref.current:
                manual_desc_ref.current.value = ""
            if manual_start_ref.current:
                manual_start_ref.current.value = ""
            if manual_end_ref.current:
                manual_end_ref.current.value = ""
            if manual_duration_ref.current:
                manual_duration_ref.current.value = ""
            _update_manual_derived()
            refresh = page.data.get("refresh_timer_activities")
            if callable(refresh):
                refresh()
            page.snack_bar = ft.SnackBar(ft.Text("Manual entry added to selected matter."), open=True)
            page.update()

        start_btn.on_click = on_start
        stop_btn.on_click = on_stop

        def _set_mode(manual: bool):
            manual_mode[0] = manual
            if timer_section_ref.current:
                timer_section_ref.current.visible = not manual
            if manual_section_ref.current:
                manual_section_ref.current.visible = manual
            if manual_btn_ref.current:
                manual_btn_ref.current.icon = (
                    ft.Icons.CHECK if manual_mode[0] else ft.Icons.EDIT_NOTE
                )
                # Use a neutral gray background when selected; avoid enum values
                manual_btn_ref.current.style = (
                    ft.ButtonStyle(
                        bgcolor={ft.ControlState.DEFAULT: "#444444"}
                    )
                    if manual_mode[0]
                    else None
                )
            page.update()

        # Expose mode setter so other callbacks (e.g. Continue task) can force timer mode.
        (page.data or {})["_timer_set_mode_callback"] = _set_mode

        def _on_manual_toggle(_):
            _set_mode(not manual_mode[0])

        timer_matter_list_initial = _build_timer_matter_list("")
        matter_block = ft.Container(
            content=ft.Column(
                [
                    ft.TextField(
                        ref=timer_matter_search_ref,
                        label="Search matters by name or path",
                        width=400,
                        on_change=on_timer_matter_search,
                    ),
                    ft.Container(height=4),
                    ft.Container(
                        content=ft.Column(ref=timer_matter_list_ref, controls=timer_matter_list_initial, scroll=ft.ScrollMode.AUTO),
                        height=160,
                        border=ft.border.all(1, ft.Colors.OUTLINE),
                        border_radius=4,
                    ),
                    ft.Container(height=4),
                    ft.Text(
                        ref=timer_matter_selection_ref,
                        size=12,
                        value=f"Selected: {timer_matter_selected[1]}" if timer_matter_selected[1] else "Select a matter below.",
                    ),
                    ft.Text("All time (timer and manual) is logged to the matter selected above.", size=12),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=4,
            padding=6,
        )

        start_time_row = ft.Container(
            ref=start_time_section_ref,
            content=ft.Row(
                [
                    ft.TextField(
                        ref=start_time_field_ref,
                        label="Started at (YYYY-MM-DD HH:MM)",
                        width=280,
                    ),
                    ft.ElevatedButton("Change start time", icon=ft.Icons.SCHEDULE, on_click=on_apply_start_time),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            visible=False,
        )

        timer_section = ft.Container(
            ref=timer_section_ref,
            content=ft.Column(
                [
                    ft.TextField(
                        ref=description_ref,
                        label="Task description (optional)",
                        width=400,
                        on_blur=on_description_blur,
                    ),
                    ft.Container(height=24),
                    label,
                    ft.Container(height=12),
                    start_time_row,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=True,
        )

        manual_section = ft.Container(
            ref=manual_section_ref,
            content=ft.Column(
                [
                    ft.Text("Fill exactly two of Start, End, Duration; the third is derived below.", size=12),
                    ft.Container(height=8),
                    ft.TextField(ref=manual_desc_ref, label="Description (optional)", width=400),
                    ft.TextField(ref=manual_start_ref, label="Start (YYYY-MM-DD HH:MM)", width=400, on_change=_update_manual_derived),
                    ft.TextField(ref=manual_end_ref, label="End (YYYY-MM-DD HH:MM)", width=400, on_change=_update_manual_derived),
                    ft.TextField(ref=manual_duration_ref, label="Duration (hours, e.g. 1.5 or 1:30)", width=400, on_change=_update_manual_derived),
                    ft.Text(ref=manual_derived_ref, size=12, value="Fill exactly two of Start, End, Duration; the third will be shown here."),
                    ft.Container(height=8),
                    ft.ElevatedButton("Add manual entry", icon=ft.Icons.ADD, on_click=on_manual_add),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=False,
        )

        manual_btn = ft.ElevatedButton(
            "Manual entry",
            icon=ft.Icons.EDIT_NOTE,
            ref=manual_btn_ref,
            on_click=_on_manual_toggle,
        )

        timer_controls = [
            ft.Text("Timer", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(height=8),
            activities_section,
        ]
        if not options:
            timer_controls.append(
                ft.Text("Add at least one matter under a client to log time.", size=14)
            )
            timer_controls.append(ft.Container(height=8))
        timer_controls.extend([
            matter_block,
            ft.Container(height=8),
            ft.Row(
                [start_btn, stop_btn, manual_btn],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Container(height=8),
            timer_section,
            manual_section,
        ])

        # Ensure initial mode is timer (manual off).
        _set_mode(False)

        return ft.Column(
            timer_controls,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_matters_tab(
        self,
        on_matters_changed: Callable[[], None] | None = None,
    ) -> ft.Control:
        """Build the Manage Matters tab: add Clients (root) or Matters (under a client/parent)."""
        page = self.page
        list_ref = self.matters_list_ref
        name_field = ft.Ref[ft.TextField]()
        add_rate_field = ft.Ref[ft.TextField]()
        parent_dropdown = ft.Ref[ft.Dropdown]()
        add_type_ref = ft.Ref[ft.SegmentedButton]()
        parent_section_ref = ft.Ref[ft.Container]()
        search_results_ref = ft.Ref[ft.Column]()
    
        move_source: list = [None, None]
        merge_source: list = [None, None]
        move_options_data: list = []  # list of (id_or_None, path) set when dialog opens
        merge_options_data: list = []
        move_selected_ref: list = [None]  # (id_or_None, path)
        merge_selected_ref: list = [None]  # (id, path)
        move_search_ref = ft.Ref[ft.TextField]()
        merge_search_ref = ft.Ref[ft.TextField]()
        move_list_ref = ft.Ref[ft.Column]()
        merge_list_ref = ft.Ref[ft.Column]()
        move_selection_text_ref = ft.Ref[ft.Text]()
        merge_selection_text_ref = ft.Ref[ft.Text]()
        move_expanded: set = set()
        merge_expanded: set = set()
        move_dialog_ref = ft.Ref[ft.AlertDialog]()
        merge_dialog_ref = ft.Ref[ft.AlertDialog]()
        share_matter_id_holder: list = [None]
        share_path_holder: list = [None]
        share_list_ref = ft.Ref[ft.Column]()
        share_add_dropdown_ref = ft.Ref[ft.Dropdown]()
        share_dialog_ref = ft.Ref[ft.AlertDialog]()
        conflict_dialog_ref = ft.Ref[ft.AlertDialog]()
        conflict_data_holder: list = [None]
    
        time_entries_matter_id: list = [None]
        time_entries_path: list = [None]
        time_entries_list_ref = ft.Ref[ft.Column]()
        time_entries_dialog_ref = ft.Ref[ft.AlertDialog]()
        edit_entry_id_ref: list = [None]
        edit_desc_ref = ft.Ref[ft.TextField]()
        edit_start_ref = ft.Ref[ft.TextField]()
        edit_end_ref = ft.Ref[ft.TextField]()
        edit_duration_ref = ft.Ref[ft.TextField]()
        edit_entry_dialog_ref = ft.Ref[ft.AlertDialog]()
        add_desc_ref = ft.Ref[ft.TextField]()
        add_start_ref = ft.Ref[ft.TextField]()
        add_end_ref = ft.Ref[ft.TextField]()
        add_duration_ref = ft.Ref[ft.TextField]()
        add_entry_dialog_ref = ft.Ref[ft.AlertDialog]()
    
        expanded_clients_matters: set[str] = set()
    
        def _by_client():
            matters = self.db.get_all_matters()
            path_list = self.db.get_matters_with_full_paths()
            path_by_id = {mid: path for mid, path in path_list}
            cur = self.db.current_user_id
            by_client: dict[str, list[tuple[int, str, str, bool]]] = defaultdict(list)
            for m in matters:
                path = path_by_id.get(m.id, m.name)
                client = path.split(" > ")[0] if " > " in path else path
                is_owner = cur is not None and m.owner_id == cur
                by_client[client].append((m.id, path, m.matter_code, is_owner))
            for client in by_client:
                by_client[client].sort(key=lambda x: x[1])
            return by_client
    
        def _build_list_controls(by_client: dict):
            controls = []
            for client_name in sorted(by_client.keys()):
                items = by_client[client_name]
                is_expanded = client_name in expanded_clients_matters
                controls.append(
                    ft.ListTile(
                        title=ft.Text(client_name, weight=ft.FontWeight.W_500),
                        subtitle=ft.Text(f"{len(items)} matter(s)"),
                        trailing=ft.Icon(
                            ft.Icons.EXPAND_LESS if is_expanded else ft.Icons.EXPAND_MORE,
                        ),
                        on_click=lambda e, c=client_name: _on_toggle_client(c),
                    ),
                )
                menu_items_builder = []
                for mid, path, code, is_owner in items:
                    display_path = path if is_owner else f"{path} (shared)"
                    items_list = [
                        ft.PopupMenuItem(
                            content="Edit rate…",
                            on_click=lambda e, m=mid, p=path: open_edit_matter_dialog(m, p),
                        ),
                        ft.PopupMenuItem(
                            content="Move…",
                            on_click=lambda e, m=mid, p=path: open_move_dialog(m, p),
                        ),
                        ft.PopupMenuItem(
                            content="Merge…",
                            on_click=lambda e, m=mid, p=path: open_merge_dialog(m, p),
                        ),
                        ft.PopupMenuItem(
                            content="Time entries",
                            on_click=lambda e, m=mid, p=path: open_time_entries_dialog(m, p),
                        ),
                    ]
                    if is_owner:
                        items_list.insert(
                            0,
                            ft.PopupMenuItem(
                                content="Share…",
                                on_click=lambda e, m=mid, p=path: open_share_dialog(m, p),
                            ),
                        )
                    menu_items_builder.append(
                        ft.ListTile(
                            title=ft.Text(display_path, size=14),
                            subtitle=ft.Text(code, size=12),
                            trailing=ft.PopupMenuButton(
                                icon=ft.Icons.MORE_VERT,
                                items=items_list,
                            ),
                        )
                    )
                controls.append(
                    ft.Container(
                        content=ft.Column(menu_items_builder),
                        visible=is_expanded,
                        padding=ft.Padding.only(left=24),
                    ),
                )
            return controls
    
        def _on_toggle_client(client_name: str):
            expanded_clients_matters.symmetric_difference_update([client_name])
            refresh_list()
    
        def _options_by_client(options: list, include_root: bool) -> dict:
            """Group (id, path) options by client (first path segment). Root option in key '— Root (new client) —'."""
            by_client = defaultdict(list)
            if include_root and options and options[0][0] is None:
                by_client["— Root (new client) —"].append(options[0])
                options = options[1:]
            for pid, ptext in options:
                client = ptext.split(" > ")[0] if " > " in ptext else ptext
                by_client[client].append((pid, ptext))
            for client in by_client:
                by_client[client].sort(key=lambda x: x[1])
            return by_client
    
        def _build_move_list_controls(query: str):
            by_client = _options_by_client(move_options_data, include_root=True)
            q = (query or "").strip().lower()
            if q:
                flat = [(pid, ptext) for pid, ptext in move_options_data if ptext and q in ptext.lower()][:15]
                return [
                    ft.ListTile(
                        title=ft.Text(ptext, size=14),
                        data=(pid, ptext),
                        selected=move_selected_ref[0] == (pid, ptext),
                        on_click=lambda e, pid=pid, ptext=ptext: _on_move_select(pid, ptext),
                    )
                    for pid, ptext in flat
                ]
            controls = []
            for client_name in sorted(by_client.keys()):
                items = by_client[client_name]
                is_exp = client_name in move_expanded
                # Root matter (client) in this group: path with no " > " is the client itself
                client_as_target = next((x for x in items if " > " not in x[1]), None)
                def _on_move_header_click(e, c=client_name, root_item=client_as_target):
                    _on_toggle_move_expanded(c)
                    if root_item is not None:
                        _on_move_select(root_item[0], root_item[1])
                controls.append(
                    ft.ListTile(
                        title=ft.Text(client_name, weight=ft.FontWeight.W_500, size=14),
                        subtitle=ft.Text(f"{len(items)} matter(s)", size=12),
                        trailing=ft.Icon(ft.Icons.EXPAND_LESS if is_exp else ft.Icons.EXPAND_MORE, size=20),
                        on_click=_on_move_header_click,
                    ),
                )
                controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.ListTile(
                                    title=ft.Text(ptext, size=14),
                                    data=(pid, ptext),
                                    selected=move_selected_ref[0] == (pid, ptext),
                                    on_click=lambda e, pid=pid, ptext=ptext: _on_move_select(pid, ptext),
                                )
                                for pid, ptext in items
                            ],
                        ),
                        visible=is_exp,
                        padding=ft.Padding.only(left=20),
                    ),
                )
            return controls
    
        def _on_toggle_move_expanded(client_name: str):
            move_expanded.symmetric_difference_update([client_name])
            if move_list_ref.current:
                move_list_ref.current.controls = _build_move_list_controls(move_search_ref.current.value if move_search_ref.current else "")
                page.update()
    
        def _on_move_select(pid, ptext):
            move_selected_ref[0] = (pid, ptext)
            if move_selection_text_ref.current:
                move_selection_text_ref.current.value = f"Selected: {ptext}"
            if move_list_ref.current:
                move_list_ref.current.controls = _build_move_list_controls(move_search_ref.current.value if move_search_ref.current else "")
                page.update()
    
        def _build_merge_list_controls(query: str):
            by_client = _options_by_client(merge_options_data, include_root=False)
            q = (query or "").strip().lower()
            if q:
                flat = [(pid, ptext) for pid, ptext in merge_options_data if ptext and q in ptext.lower()][:15]
                return [
                    ft.ListTile(
                        title=ft.Text(ptext, size=14),
                        data=(pid, ptext),
                        selected=merge_selected_ref[0] == (pid, ptext),
                        on_click=lambda e, pid=pid, ptext=ptext: _on_merge_select(pid, ptext),
                    )
                    for pid, ptext in flat
                ]
            controls = []
            for client_name in sorted(by_client.keys()):
                items = by_client[client_name]
                is_exp = client_name in merge_expanded
                controls.append(
                    ft.ListTile(
                        title=ft.Text(client_name, weight=ft.FontWeight.W_500, size=14),
                        subtitle=ft.Text(f"{len(items)} matter(s)", size=12),
                        trailing=ft.Icon(ft.Icons.EXPAND_LESS if is_exp else ft.Icons.EXPAND_MORE, size=20),
                        on_click=lambda e, c=client_name: _on_toggle_merge_expanded(c),
                    ),
                )
                controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.ListTile(
                                    title=ft.Text(ptext, size=14),
                                    data=(pid, ptext),
                                    selected=merge_selected_ref[0] == (pid, ptext),
                                    on_click=lambda e, pid=pid, ptext=ptext: _on_merge_select(pid, ptext),
                                )
                                for pid, ptext in items
                            ],
                        ),
                        visible=is_exp,
                        padding=ft.Padding.only(left=20),
                    ),
                )
            return controls
    
        def _on_toggle_merge_expanded(client_name: str):
            merge_expanded.symmetric_difference_update([client_name])
            if merge_list_ref.current:
                merge_list_ref.current.controls = _build_merge_list_controls(merge_search_ref.current.value if merge_search_ref.current else "")
                page.update()
    
        def _on_merge_select(pid, ptext):
            merge_selected_ref[0] = (pid, ptext)
            if merge_selection_text_ref.current:
                merge_selection_text_ref.current.value = f"Selected: {ptext}"
            if merge_list_ref.current:
                merge_list_ref.current.controls = _build_merge_list_controls(merge_search_ref.current.value if merge_search_ref.current else "")
                page.update()
    
        def on_move_search(e):
            if move_list_ref.current and move_search_ref.current:
                move_list_ref.current.controls = _build_move_list_controls(e.control.value or "")
                page.update()
    
        def on_merge_search(e):
            if merge_list_ref.current and merge_search_ref.current:
                merge_list_ref.current.controls = _build_merge_list_controls(e.control.value or "")
                page.update()
    
        def open_move_dialog(mid: int, path: str):
            move_source[0], move_source[1] = mid, path
            move_options_data[:] = self.db.get_matters_with_full_paths_excluding(mid, include_root_option=True)
            first = (move_options_data[0][0], move_options_data[0][1]) if move_options_data else (None, "")
            move_selected_ref[0] = first
            move_expanded.clear()
            if move_dialog_ref.current:
                move_dialog_ref.current.title = ft.Text(f"Move '{path}' to")
                move_dialog_ref.current.open = True
            if move_search_ref.current:
                move_search_ref.current.value = ""
            if move_selection_text_ref.current:
                move_selection_text_ref.current.value = f"Selected: {first[1]}"
            if move_list_ref.current:
                move_list_ref.current.controls = _build_move_list_controls("")
            page.update()
    
        def on_move_confirm(_):
            sel = move_selected_ref[0]
            if sel is None or move_source[0] is None:
                return
            new_parent_id = sel[0]
            try:
                self.db.move_matter(move_source[0], new_parent_id)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                page.update()
                return
            if move_dialog_ref.current:
                move_dialog_ref.current.open = False
            refresh_list()
            refresh_parent_dropdown()
            if on_matters_changed:
                on_matters_changed()
            page.snack_bar = ft.SnackBar(ft.Text("Matter moved."), open=True)
            page.update()
    
        def on_move_cancel(_):
            if move_dialog_ref.current:
                move_dialog_ref.current.open = False
            page.update()
    
        def open_merge_dialog(mid: int, path: str):
            merge_source[0], merge_source[1] = mid, path
            merge_options_data[:] = self.db.get_matters_with_full_paths_excluding(mid, include_root_option=False)
            first = (merge_options_data[0][0], merge_options_data[0][1]) if merge_options_data else (None, "")
            merge_selected_ref[0] = first
            merge_expanded.clear()
            if merge_dialog_ref.current:
                merge_dialog_ref.current.title = ft.Text(f"Merge '{path}' into")
                merge_dialog_ref.current.open = True
            if merge_search_ref.current:
                merge_search_ref.current.value = ""
            if merge_selection_text_ref.current:
                merge_selection_text_ref.current.value = f"Selected: {first[1]}"
            if merge_list_ref.current:
                merge_list_ref.current.controls = _build_merge_list_controls("")
            page.update()
    
        def on_merge_confirm(_):
            sel = merge_selected_ref[0]
            if sel is None or merge_source[0] is None:
                return
            target_id = sel[0]
            try:
                self.db.merge_matter_into(merge_source[0], target_id)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                page.update()
                return
            if merge_dialog_ref.current:
                merge_dialog_ref.current.open = False
            refresh_list()
            refresh_parent_dropdown()
            if on_matters_changed:
                on_matters_changed()
            page.snack_bar = ft.SnackBar(ft.Text("Matters merged."), open=True)
            page.update()
    
        def on_merge_cancel(_):
            if merge_dialog_ref.current:
                merge_dialog_ref.current.open = False
            page.update()
    
        def _build_share_list_controls():
            mid = share_matter_id_holder[0]
            if mid is None:
                return []
            try:
                users = self.db.list_matter_shares(mid)
            except ValueError:
                return []
            return [
                ft.ListTile(
                    title=ft.Text(u.username, size=14),
                    trailing=ft.IconButton(
                        icon=ft.Icons.PERSON_REMOVE,
                        on_click=lambda e, uid=u.id: on_share_remove(uid),
                    ),
                )
                for u in users
            ]
    
        def refresh_share_list():
            if share_list_ref.current:
                share_list_ref.current.controls = _build_share_list_controls()
            page.update()
    
        def open_share_dialog(mid: int, path: str):
            share_matter_id_holder[0] = mid
            share_path_holder[0] = path
            if share_dialog_ref.current:
                share_dialog_ref.current.title = ft.Text(f"Share: {path}")
                share_dialog_ref.current.open = True
            refresh_share_list()
            if share_add_dropdown_ref.current:
                opts = self.db.list_users_for_share()
                share_add_dropdown_ref.current.options = [
                    ft.DropdownOption(key=str(uid), text=uname) for uid, uname in opts
                ]
                share_add_dropdown_ref.current.value = None
            page.update()
    
        def on_share_add(_):
            mid = share_matter_id_holder[0]
            path = share_path_holder[0]
            if mid is None or not share_add_dropdown_ref.current or not share_add_dropdown_ref.current.value:
                return
            try:
                user_id = int(share_add_dropdown_ref.current.value)
            except (TypeError, ValueError):
                return
            conflict = self.db.find_owned_matter_with_same_path(user_id, path)
            if conflict is not None:
                other_mid, _ = conflict
                user = self.db.get_user(user_id)
                username = user.username if user else str(user_id)
                conflict_data_holder[0] = (mid, user_id, other_mid, path, username)
                if conflict_dialog_ref.current:
                    conflict_dialog_ref.current.title = ft.Text(
                        f"User {username} has a matter with the same name. Merge their matter into this one?"
                    )
                    conflict_dialog_ref.current.open = True
                page.update()
                return
            try:
                self.db.add_matter_share(mid, user_id)
                refresh_share_list()
                share_add_dropdown_ref.current.value = None
                page.snack_bar = ft.SnackBar(ft.Text("Matter shared."), open=True)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
            page.update()
    
        def on_share_remove(user_id: int):
            mid = share_matter_id_holder[0]
            if mid is None:
                return
            try:
                self.db.remove_matter_share(mid, user_id)
                refresh_share_list()
                page.snack_bar = ft.SnackBar(ft.Text("Share removed."), open=True)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
            page.update()
    
        def on_conflict_merge(_):
            data = conflict_data_holder[0]
            if conflict_dialog_ref.current:
                conflict_dialog_ref.current.open = False
            if data is None:
                page.update()
                return
            mid, user_id, other_mid, path, username = data
            conflict_data_holder[0] = None
            try:
                self.db.merge_other_user_matter_into_mine(other_mid, mid)
                self.db.add_matter_share(mid, user_id)
                refresh_share_list()
                refresh_list()
                if on_matters_changed:
                    on_matters_changed()
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Merged {username}'s matter into this one and shared."),
                    open=True,
                )
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
            page.update()
    
        def on_conflict_skip(_):
            if conflict_dialog_ref.current:
                conflict_dialog_ref.current.open = False
            conflict_data_holder[0] = None
            page.snack_bar = ft.SnackBar(
                ft.Text("Ask the other user to rename their matter, then try sharing again."),
                open=True,
            )
            page.update()
    
        def on_share_close(_):
            if share_dialog_ref.current:
                share_dialog_ref.current.open = False
            page.update()
    
        def _build_time_entries_list_controls():
            mid = time_entries_matter_id[0]
            if mid is None:
                return []
            entries = self.db.get_time_entries_by_matter(mid)
            controls = []
            for entry in entries:
                desc = (entry.description or "")[:40] + ("…" if (entry.description or "") and len(entry.description or "") > 40 else "")
                end_str = format_datetime(entry.end_time) if entry.end_time else "Running"
                dur_sec = entry.duration_seconds or 0.0
                dur_str = format_elapsed(dur_sec) if dur_sec else ("—" if entry.end_time else "—")
                rate, rate_source = self.db.get_resolved_hourly_rate(entry.matter_id, entry.owner_id)
                amount_eur = self.db.amount_eur_from_seconds(dur_sec, rate)
                amount_color = _rate_source_color(rate_source)
                def _on_continue_from_dialog(ent):
                    try:
                        self.db.continue_time_entry(ent.id)
                        refresh_time_entries_list()
                        page.snack_bar = ft.SnackBar(ft.Text("Continued task; new entry is running. Switch to Timer to see it."), open=True)
                    except ValueError as err:
                        page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                    page.update()

                controls.append(
                    ft.ListTile(
                        title=ft.Text(desc or "(no description)", size=14),
                        subtitle=ft.Row(
                            [
                                ft.Text(f"{format_datetime(entry.start_time)} → {end_str}  ·  {dur_str}", size=12),
                                ft.Text("  ", size=12),
                                ft.Text(format_eur(amount_eur), size=12, color=amount_color),
                            ],
                            wrap=True,
                        ),
                        trailing=ft.Row(
                            [
                                ft.OutlinedButton(
                                    content=ft.Text("Continue", size=9, no_wrap=True),
                                    on_click=lambda e, ent=entry: _on_continue_from_dialog(ent),
                                ),
                                ft.IconButton(icon=ft.Icons.EDIT, on_click=lambda e, ent=entry: open_edit_entry_dialog(ent)),
                            ],
                            spacing=4,
                        ),
                    ),
                )
            return controls
    
        def refresh_time_entries_list():
            if time_entries_list_ref.current:
                time_entries_list_ref.current.controls = _build_time_entries_list_controls()
                page.update()
    
        def open_time_entries_dialog(mid: int, path: str):
            time_entries_matter_id[0] = mid
            time_entries_path[0] = path
            if time_entries_dialog_ref.current:
                time_entries_dialog_ref.current.title = ft.Text(f"Time entries: {path}")
                time_entries_dialog_ref.current.open = True
            if time_entries_list_ref.current:
                time_entries_list_ref.current.controls = _build_time_entries_list_controls()
            page.update()
    
        def on_time_entries_add(_):
            open_add_entry_dialog()
    
        def open_edit_entry_dialog(entry):
            edit_entry_id_ref[0] = entry.id
            if edit_desc_ref.current:
                edit_desc_ref.current.value = entry.description or ""
            if edit_start_ref.current:
                edit_start_ref.current.value = format_datetime(entry.start_time)
            if edit_end_ref.current:
                edit_end_ref.current.value = format_datetime(entry.end_time) if entry.end_time else ""
            if edit_duration_ref.current:
                edit_duration_ref.current.value = str(round((entry.duration_seconds or 0) / 3600, 2)) if entry.duration_seconds else ""
            if edit_entry_dialog_ref.current:
                edit_entry_dialog_ref.current.open = True
            page.update()
    
        def on_edit_entry_save(_):
            eid = edit_entry_id_ref[0]
            if eid is None:
                return
            desc = edit_desc_ref.current.value if edit_desc_ref.current else ""
            start_s = edit_start_ref.current.value if edit_start_ref.current else ""
            end_s = edit_end_ref.current.value if edit_end_ref.current else ""
            dur_s = edit_duration_ref.current.value if edit_duration_ref.current else ""
            start_t, end_t, dur = _compute_third_time_static(start_s, end_s, dur_s)
            if start_t is None or end_t is None or dur is None:
                page.snack_bar = ft.SnackBar(ft.Text("Fill exactly two of Start, End, Duration."), open=True)
                page.update()
                return
            try:
                self.db.update_time_entry(eid, description=desc.strip(), start_time=start_t, end_time=end_t, duration_seconds=dur)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                page.update()
                return
            if edit_entry_dialog_ref.current:
                edit_entry_dialog_ref.current.open = False
            refresh_time_entries_list()
            page.snack_bar = ft.SnackBar(ft.Text("Entry updated."), open=True)
            page.update()
    
        def on_edit_entry_cancel(_):
            if edit_entry_dialog_ref.current:
                edit_entry_dialog_ref.current.open = False
            page.update()
    
        def open_add_entry_dialog():
            if add_desc_ref.current:
                add_desc_ref.current.value = ""
            if add_start_ref.current:
                add_start_ref.current.value = ""
            if add_end_ref.current:
                add_end_ref.current.value = ""
            if add_duration_ref.current:
                add_duration_ref.current.value = ""
            if add_entry_dialog_ref.current:
                add_entry_dialog_ref.current.open = True
            page.update()
    
        def on_add_entry_save(_):
            mid = time_entries_matter_id[0]
            if mid is None:
                return
            desc = (add_desc_ref.current.value or "").strip() if add_desc_ref.current else ""
            start_s = add_start_ref.current.value if add_start_ref.current else ""
            end_s = add_end_ref.current.value if add_end_ref.current else ""
            dur_s = add_duration_ref.current.value if add_duration_ref.current else ""
            start_t, end_t, dur = _compute_third_time_static(start_s, end_s, dur_s)
            if start_t is None or end_t is None or dur is None:
                page.snack_bar = ft.SnackBar(ft.Text("Fill exactly two of Start, End, Duration."), open=True)
                page.update()
                return
            try:
                self.db.add_manual_time_entry(mid, desc, start_time=start_t, end_time=end_t, duration_seconds=dur)
            except ValueError as err:
                page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
                page.update()
                return
            if add_entry_dialog_ref.current:
                add_entry_dialog_ref.current.open = False
            refresh_time_entries_list()
            page.snack_bar = ft.SnackBar(ft.Text("Entry added."), open=True)
            page.update()
    
        def on_add_entry_cancel(_):
            if add_entry_dialog_ref.current:
                add_entry_dialog_ref.current.open = False
            page.update()
    
        def on_time_entries_close(_):
            if time_entries_dialog_ref.current:
                time_entries_dialog_ref.current.open = False
            page.update()
    
        edit_matter_id_holder: list = []
        edit_matter_rate_ref = ft.Ref[ft.TextField]()
        edit_matter_my_rate_ref = ft.Ref[ft.TextField]()
        edit_matter_my_rate_container_ref = ft.Ref[ft.Container]()
        edit_matter_dialog_ref = ft.Ref[ft.AlertDialog]()
    
        def open_edit_matter_dialog(mid: int, path: str):
            matters = self.db.get_all_matters()
            matter = next((m for m in matters if m.id == mid), None)
            if not matter:
                return
            edit_matter_id_holder.clear()
            edit_matter_id_holder.append(mid)
            cur = self.db.current_user_id
            is_owner = cur is not None and matter.owner_id == cur
            if edit_matter_rate_ref.current:
                is_root = matter.parent_id is None
                edit_matter_rate_ref.current.label = "Client hourly rate (€)" if is_root else "Matter hourly rate (€)"
                edit_matter_rate_ref.current.visible = is_owner
                rate_val = getattr(matter, "hourly_rate_euro", None)
                edit_matter_rate_ref.current.value = str(rate_val) if rate_val is not None else ""
                edit_matter_rate_ref.current.error_text = None
            if edit_matter_my_rate_container_ref.current:
                edit_matter_my_rate_container_ref.current.visible = not is_owner
            if edit_matter_my_rate_ref.current and not is_owner:
                try:
                    users_rates = self.db.get_matter_access_users_with_rates(mid)
                    my_rate = next((r for uid, _, r in users_rates if uid == cur), None)
                    edit_matter_my_rate_ref.current.value = str(my_rate) if my_rate is not None else ""
                    edit_matter_my_rate_ref.current.error_text = None
                except ValueError:
                    edit_matter_my_rate_ref.current.value = ""
            if edit_matter_dialog_ref.current:
                edit_matter_dialog_ref.current.title = ft.Text(f"Edit: {path}")
                edit_matter_dialog_ref.current.open = True
            page.update()
    
        def on_edit_matter_save(_):
            if not edit_matter_id_holder or not edit_matter_rate_ref.current:
                return
            mid = edit_matter_id_holder[0]
            cur = self.db.current_user_id
            matters = self.db.get_all_matters()
            matter = next((m for m in matters if m.id == mid), None)
            is_owner = matter is not None and cur is not None and matter.owner_id == cur
            if is_owner:
                rate_str = (edit_matter_rate_ref.current.value or "").strip()
                rate_val = None
                if rate_str:
                    try:
                        rate_val = float(rate_str)
                        if rate_val < 0:
                            edit_matter_rate_ref.current.error_text = "Rate must be ≥ 0."
                            page.update()
                            return
                    except ValueError:
                        edit_matter_rate_ref.current.error_text = "Enter a number or leave empty to clear."
                        page.update()
                        return
                try:
                    self.db.update_matter(mid, hourly_rate_euro=rate_val)
                    if edit_matter_dialog_ref.current:
                        edit_matter_dialog_ref.current.open = False
                    refresh_list()
                    if on_matters_changed:
                        on_matters_changed()
                    page.snack_bar = ft.SnackBar(ft.Text("Hourly rate updated."), open=True)
                except ValueError as err:
                    edit_matter_rate_ref.current.error_text = str(err)
            else:
                my_rate_str = (edit_matter_my_rate_ref.current.value or "").strip() if edit_matter_my_rate_ref.current else ""
                my_rate_val = None
                if my_rate_str:
                    try:
                        my_rate_val = float(my_rate_str)
                        if my_rate_val < 0:
                            edit_matter_my_rate_ref.current.error_text = "Rate must be ≥ 0."
                            page.update()
                            return
                    except ValueError:
                        edit_matter_my_rate_ref.current.error_text = "Enter a number or leave empty to clear."
                        page.update()
                        return
                try:
                    self.db.set_user_matter_rate(cur, mid, my_rate_val)
                    if edit_matter_dialog_ref.current:
                        edit_matter_dialog_ref.current.open = False
                    refresh_list()
                    page.snack_bar = ft.SnackBar(ft.Text("Your rate for this matter updated."), open=True)
                except ValueError as err:
                    if edit_matter_my_rate_ref.current:
                        edit_matter_my_rate_ref.current.error_text = str(err)
            page.update()
    
        def on_edit_matter_cancel(_):
            if edit_matter_dialog_ref.current:
                edit_matter_dialog_ref.current.open = False
            page.update()
    
        edit_matter_dialog = ft.AlertDialog(
            ref=edit_matter_dialog_ref,
            title=ft.Text("Edit matter"),
            content=ft.Column(
                [
                    ft.TextField(ref=edit_matter_rate_ref, label="Hourly rate (€)", width=300, hint_text="Leave empty to clear"),
                    ft.Container(
                        ref=edit_matter_my_rate_container_ref,
                        content=ft.TextField(ref=edit_matter_my_rate_ref, label="My rate for this matter (€)", width=300, hint_text="Override your rate for this matter; leave empty to use matter or default"),
                        visible=False,
                    ),
                    ft.Row(
                        [
                            ft.ElevatedButton("Save", on_click=on_edit_matter_save),
                            ft.OutlinedButton("Cancel", on_click=on_edit_matter_cancel),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
    
        def refresh_list():
            by_client = _by_client()
            if list_ref.current:
                list_ref.current.controls = _build_list_controls(by_client)
                page.update()
    
        def on_add(_):
            if not name_field.current:
                return
            n = (name_field.current.value or "").strip()
            if not n:
                page.snack_bar = ft.SnackBar(ft.Text("Name is required."), open=True)
                page.update()
                return
            c = self.db.suggest_unique_code(n)
            is_client = True
            if add_type_ref.current and add_type_ref.current.selected:
                is_client = add_type_ref.current.selected[0] == "client"
            pid = None
            if not is_client:
                if not parent_dropdown.current or not parent_dropdown.current.value:
                    page.snack_bar = ft.SnackBar(
                        ft.Text("Select a parent client or matter when adding a matter."),
                        open=True,
                    )
                    page.update()
                    return
                try:
                    pid = int(parent_dropdown.current.value)
                except (TypeError, ValueError):
                    page.snack_bar = ft.SnackBar(ft.Text("Invalid parent selection."), open=True)
                    page.update()
                    return
            rate_val = None
            if add_rate_field.current and (add_rate_field.current.value or "").strip():
                try:
                    rate_val = float((add_rate_field.current.value or "").strip())
                    if rate_val < 0:
                        page.snack_bar = ft.SnackBar(ft.Text("Hourly rate must be ≥ 0."), open=True)
                        page.update()
                        return
                except ValueError:
                    page.snack_bar = ft.SnackBar(ft.Text("Hourly rate must be a number or empty."), open=True)
                    page.update()
                    return
            try:
                self.db.add_matter(name=n, matter_code=c, parent_id=pid, hourly_rate_euro=rate_val)
            except IntegrityError:
                page.snack_bar = ft.SnackBar(
                    ft.Text("A matter with this name already exists or could not generate a unique code."),
                    open=True,
                )
                page.update()
                return
            name_field.current.value = ""
            if parent_dropdown.current:
                parent_dropdown.current.value = None
            if add_rate_field.current:
                add_rate_field.current.value = ""
            refresh_list()
            refresh_parent_dropdown()
            if on_matters_changed:
                on_matters_changed()
            page.update()
    
        def refresh_parent_dropdown():
            """Reload parent dropdown options from DB so new clients/matters appear immediately."""
            if parent_dropdown.current:
                path_options = self.db.get_matters_with_full_paths()
                parent_dropdown.current.options = [
                    ft.DropdownOption(key=str(mid), text=path) for mid, path in path_options
                ]

        def on_type_change(e):
            if parent_section_ref.current and add_type_ref.current:
                is_matter = add_type_ref.current.selected and add_type_ref.current.selected[0] == "matter"
                parent_section_ref.current.visible = is_matter
                if is_matter:
                    refresh_parent_dropdown()
                if add_rate_field.current:
                    add_rate_field.current.label = "Matter hourly rate (€)" if is_matter else "Client hourly rate (€)"
                page.update()
    
        def on_search(e):
            if not search_results_ref.current:
                return
            by_client = _by_client()
            all_entries = [
                (c, path, code)
                for c, items in by_client.items()
                for (_, path, code, _) in items
            ]
            all_entries.extend((c, c, "") for c in by_client.keys())  # clients as entries too
            q = (e.control.value or "").strip().lower()
            if not q:
                search_results_ref.current.controls = []
                search_results_ref.current.visible = False
            else:
                matching = [x for x in all_entries if q in x[0].lower() or q in x[1].lower()][:6]
                search_results_ref.current.controls = [
                    ft.ListTile(
                        title=ft.Text(path or client, size=14),
                        subtitle=ft.Text(f"{client}" + (f" · {code}" if code else ""), size=12),
                    )
                    for client, path, code in matching
                ]
                search_results_ref.current.visible = bool(matching)
            page.update()

        path_options = self.db.get_matters_with_full_paths()
        parent_dropdown_control = ft.Dropdown(
            ref=parent_dropdown,
            label="Parent client or matter",
            width=400,
            options=[ft.DropdownOption(key=str(mid), text=path) for mid, path in path_options],
            value=None,
        )
        parent_section = ft.Container(
            ref=parent_section_ref,
            content=parent_dropdown_control,
            visible=False,
        )
        add_type_button = ft.SegmentedButton(
            ref=add_type_ref,
            segments=[
                ft.Segment(value="client", label=ft.Text("Client")),
                ft.Segment(value="matter", label=ft.Text("Matter")),
            ],
            selected=["client"],
            on_change=on_type_change,
        )
    
        search_field = ft.TextField(
            label="Search clients and matters",
            width=400,
            on_change=on_search,
        )
        search_results_column = ft.Column(
            ref=search_results_ref,
            visible=False,
            scroll=ft.ScrollMode.AUTO,
        )
    
        by_client_initial = _by_client()
        list_column = ft.Column(
            ref=list_ref,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=_build_list_controls(by_client_initial),
        )
    
        move_dialog = ft.AlertDialog(
            ref=move_dialog_ref,
            title=ft.Text("Move matter to"),
            content=ft.Column(
                [
                    ft.TextField(
                        ref=move_search_ref,
                        label="Search by name or path",
                        width=400,
                        on_change=on_move_search,
                    ),
                    ft.Container(
                        content=ft.Column(ref=move_list_ref, scroll=ft.ScrollMode.AUTO),
                        height=220,
                        border=ft.border.all(1, ft.Colors.OUTLINE),
                        border_radius=4,
                    ),
                    ft.Text(ref=move_selection_text_ref, size=12, value="Selected: —"),
                    ft.Row(
                        [
                            ft.ElevatedButton("Move", on_click=on_move_confirm),
                            ft.OutlinedButton("Cancel", on_click=on_move_cancel),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        merge_dialog = ft.AlertDialog(
            ref=merge_dialog_ref,
            title=ft.Text("Merge matter into"),
            content=ft.Column(
                [
                    ft.TextField(
                        ref=merge_search_ref,
                        label="Search by name or path",
                        width=400,
                        on_change=on_merge_search,
                    ),
                    ft.Container(
                        content=ft.Column(ref=merge_list_ref, scroll=ft.ScrollMode.AUTO),
                        height=220,
                        border=ft.border.all(1, ft.Colors.OUTLINE),
                        border_radius=4,
                    ),
                    ft.Text(ref=merge_selection_text_ref, size=12, value="Selected: —"),
                    ft.Text("All time and sub-matters will be moved.", size=12),
                    ft.Row(
                        [
                            ft.ElevatedButton("Merge", on_click=on_merge_confirm),
                            ft.OutlinedButton("Cancel", on_click=on_merge_cancel),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        share_dialog = ft.AlertDialog(
            ref=share_dialog_ref,
            title=ft.Text("Share matter"),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column(ref=share_list_ref, scroll=ft.ScrollMode.AUTO),
                        height=180,
                        border=ft.border.all(1, ft.Colors.OUTLINE),
                        border_radius=4,
                    ),
                    ft.Row(
                        [
                            ft.Dropdown(
                                ref=share_add_dropdown_ref,
                                label="Add user",
                                width=220,
                                options=[],
                            ),
                            ft.ElevatedButton("Add", on_click=on_share_add),
                        ],
                        spacing=12,
                    ),
                    ft.Row([ft.OutlinedButton("Close", on_click=on_share_close)], spacing=12),
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        conflict_dialog = ft.AlertDialog(
            ref=conflict_dialog_ref,
            title=ft.Text("Same-name matter"),
            content=ft.Column(
                [
                    ft.Text("Merge their matter into this one, or ask them to rename and try again.", size=12),
                    ft.Row(
                        [
                            ft.ElevatedButton("Merge into this one", on_click=on_conflict_merge),
                            ft.OutlinedButton("I'll ask them to rename", on_click=on_conflict_skip),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
        time_entries_dialog = ft.AlertDialog(
            ref=time_entries_dialog_ref,
            title=ft.Text("Time entries"),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column(ref=time_entries_list_ref, scroll=ft.ScrollMode.AUTO),
                        height=280,
                        border=ft.border.all(1, ft.Colors.OUTLINE),
                        border_radius=4,
                    ),
                    ft.Row(
                        [
                            ft.ElevatedButton("Add entry", icon=ft.Icons.ADD, on_click=on_time_entries_add),
                            ft.OutlinedButton("Close", on_click=on_time_entries_close),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        edit_entry_dialog = ft.AlertDialog(
            ref=edit_entry_dialog_ref,
            title=ft.Text("Edit time entry"),
            content=ft.Column(
                [
                    ft.TextField(ref=edit_desc_ref, label="Description", width=400),
                    ft.TextField(ref=edit_start_ref, label="Start (YYYY-MM-DD HH:MM)", width=400),
                    ft.TextField(ref=edit_end_ref, label="End (YYYY-MM-DD HH:MM)", width=400),
                    ft.TextField(ref=edit_duration_ref, label="Duration (hours, e.g. 1.5 or 1:30)", width=400),
                    ft.Text("Fill exactly two of Start, End, Duration; the third is computed.", size=12),
                    ft.Row(
                        [
                            ft.ElevatedButton("Save", on_click=on_edit_entry_save),
                            ft.OutlinedButton("Cancel", on_click=on_edit_entry_cancel),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
        add_entry_dialog = ft.AlertDialog(
            ref=add_entry_dialog_ref,
            title=ft.Text("Add time entry"),
            content=ft.Column(
                [
                    ft.TextField(ref=add_desc_ref, label="Description", width=400),
                    ft.TextField(ref=add_start_ref, label="Start (YYYY-MM-DD HH:MM)", width=400),
                    ft.TextField(ref=add_end_ref, label="End (YYYY-MM-DD HH:MM)", width=400),
                    ft.TextField(ref=add_duration_ref, label="Duration (hours, e.g. 1.5 or 1:30)", width=400),
                    ft.Text("Fill exactly two of Start, End, Duration; the third is computed.", size=12),
                    ft.Row(
                        [
                            ft.ElevatedButton("Add", on_click=on_add_entry_save),
                            ft.OutlinedButton("Cancel", on_click=on_add_entry_cancel),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
        page.overlay.append(move_dialog)
        page.overlay.append(merge_dialog)
        page.overlay.append(share_dialog)
        page.overlay.append(conflict_dialog)
        page.overlay.append(edit_matter_dialog)
        page.overlay.append(time_entries_dialog)
        page.overlay.append(edit_entry_dialog)
        page.overlay.append(add_entry_dialog)
    
        return ft.Column(
            [
                ft.Text("Manage Matters", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=16),
                ft.Text("Add as", size=14),
                ft.Container(height=4),
                add_type_button,
                ft.Container(height=16),
                parent_section,
                ft.TextField(ref=name_field, label="Name", width=400),
                ft.TextField(
                    ref=add_rate_field,
                    label="Client hourly rate (€)",
                    width=400,
                    hint_text="Optional; leave empty to use user default or set later",
                ),
                ft.Container(height=8),
                ft.ElevatedButton("Add", icon=ft.Icons.ADD, on_click=on_add),
                ft.Container(height=24),
                ft.Text("Clients & Matters", size=16, weight=ft.FontWeight.W_500),
                ft.Container(height=8),
                search_field,
                ft.Container(height=8),
                search_results_column,
                ft.Container(height=8),
                list_column,
            ],
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )
    
    
    def _build_reporting_tab(
        self,
        on_toggle_client: Callable[[str], None],
        rows_data: list[tuple[str, str, float, float, float, float, str]] | None = None,
    ) -> ft.Control:
        """Build the Reporting tab: clients (collapsed by default), expand to show matters; total vs not invoiced; chargeable € with color."""
        page = self.page
        expanded_clients = self.expanded_clients
        if rows_data is None:
            rows_data = self.db.get_time_by_client_and_matter_detailed()
        search_results_ref = ft.Ref[ft.Column]()
        sort_value = (page.data or {}).get("reporting_sort") or "most_uninvoiced"

        if not rows_data:
            return ft.Column(
                [
                    ft.Text("Reporting", size=24, weight=ft.FontWeight.BOLD),
                    ft.Container(height=16),
                    ft.Text(
                        "No completed time entries yet. Use the Timer to log time, then return here.",
                        size=14,
                    ),
                ],
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            )

        by_client: dict[str, list[tuple[str, float, float, float, float, str]]] = defaultdict(list)
        for row in rows_data:
            client_name, matter_path, total_seconds, not_invoiced_seconds, total_amount_eur, not_inv_amount_eur, rate_source = row
            by_client[client_name].append((matter_path, total_seconds, not_invoiced_seconds, total_amount_eur, not_inv_amount_eur, rate_source))

        def on_sort_change(e):
            val = getattr(e.control, "value", None) or getattr(e, "data", None)
            if page.data is not None and val:
                page.data["reporting_sort"] = val
                refresh = (page.data or {}).get("refresh_reporting")
                if refresh:
                    refresh()

        sort_dropdown = ft.Dropdown(
            label="Sort clients by",
            width=280,
            value=sort_value,
            options=[
                ft.DropdownOption(key="most_uninvoiced", text="Most not invoiced time"),
                ft.DropdownOption(key="most_accrued", text="Most accrued (total) time"),
            ],
            on_select=on_sort_change,
        )

        client_order = sorted(
            by_client.keys(),
            key=lambda c: (
                sum(r[2] for r in by_client[c]) if sort_value == "most_uninvoiced"  # not_invoiced_seconds
                else sum(r[1] for r in by_client[c])  # total_seconds
            ),
            reverse=True,
        )

        def on_search(e):
            if not search_results_ref.current:
                return
            q = (e.control.value or "").strip().lower()
            if not q:
                search_results_ref.current.controls = []
                search_results_ref.current.visible = False
            else:
                _match_list = [r for r in rows_data if q in r[0].lower() or q in r[1].lower()][:6]
                search_results_ref.current.controls = [
                    ft.ListTile(
                        title=ft.Text(matter_path, size=14),
                        subtitle=ft.Text(
                            f"{client_name} · Total {format_elapsed(sec)} · Not inv. {format_elapsed(ni)} · {format_eur(ta)} (not inv. {format_eur(na)})",
                            size=12,
                        ),
                    )
                    for (client_name, matter_path, sec, ni, ta, na, _) in _match_list
                ]
                search_results_ref.current.visible = bool(_match_list)
            page.update()

        search_field = ft.TextField(
            label="Search clients and matters",
            width=400,
            on_change=on_search,
        )

        search_results_column = ft.Column(
            ref=search_results_ref,
            visible=False,
            scroll=ft.ScrollMode.AUTO,
        )

        client_blocks = []
        for client_name in client_order:
            matter_rows = by_client[client_name]
            client_total = sum(r[1] for r in matter_rows)
            client_not_invoiced = sum(r[2] for r in matter_rows)
            client_total_eur = sum(r[3] for r in matter_rows)
            client_not_inv_eur = sum(r[4] for r in matter_rows)
            is_expanded = client_name in expanded_clients
            client_blocks.append(
                ft.Column(
                    [
                        ft.ListTile(
                            title=ft.Text(client_name, weight=ft.FontWeight.W_500),
                            subtitle=ft.Text(
                                f"Total {format_elapsed(client_total)} · Not inv. {format_elapsed(client_not_invoiced)} · Chargeable {format_eur(client_total_eur)} (not inv. {format_eur(client_not_inv_eur)})",
                                size=12,
                            ),
                            trailing=ft.Icon(
                                ft.Icons.EXPAND_LESS if is_expanded else ft.Icons.EXPAND_MORE,
                            ),
                            on_click=lambda e, c=client_name: on_toggle_client(c),
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.ListTile(
                                        title=ft.Text(matter_path, size=14),
                                        subtitle=ft.Row(
                                            [
                                                ft.Text(
                                                    f"Total {format_elapsed(total_seconds)} · Not inv. {format_elapsed(not_invoiced_seconds)} · ",
                                                    size=12,
                                                ),
                                                ft.Text("Chargeable ", size=12),
                                                ft.Text(format_eur(total_amount_eur), size=12, color=_rate_source_color(rate_source)),
                                                ft.Text(f" (not inv. ", size=12),
                                                ft.Text(format_eur(not_inv_amount_eur), size=12, color=_rate_source_color(rate_source)),
                                                ft.Text(")", size=12),
                                            ],
                                            wrap=True,
                                        ),
                                    )
                                    for (matter_path, total_seconds, not_invoiced_seconds, total_amount_eur, not_inv_amount_eur, rate_source) in sorted(
                                        matter_rows, key=lambda r: r[0]
                                    )
                                ],
                            ),
                            visible=is_expanded,
                            padding=ft.Padding.only(left=24),
                        ),
                    ],
                )
            )

        return ft.Column(
            [
                ft.Text("Reporting", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=16),
                sort_dropdown,
                ft.Container(height=8),
                search_field,
                ft.Container(height=8),
                search_results_column,
                ft.Container(height=16),
                ft.Text("By client", size=16, weight=ft.FontWeight.W_500),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Column(client_blocks, scroll=ft.ScrollMode.AUTO),
                    expand=True,
                ),
            ],
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_timesheet_tab(self) -> ft.Control:
        """Timesheet tab: matter selection (checkboxes, parent selects descendants), export to JSON, optional mark as invoiced."""
        page = self.page
        timesheet_selected_ids: set[int] = set()
        timesheet_expanded: set[str] = set()
        timesheet_search_ref = ft.Ref[ft.TextField]()
        timesheet_list_ref = ft.Ref[ft.Column]()
        timesheet_preview_ref = ft.Ref[ft.Column]()
        only_not_invoiced_ref = ft.Ref[ft.Checkbox]()
        export_all_users_ref = ft.Ref[ft.Checkbox]()
        current_user_is_admin = self.db.current_user_is_admin()

        def _do_preview(_):
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
                preview_controls = [ft.Text("No entries to show.", size=14)]
            else:
                # Group by logical activity (same matter, description, activity_group_id) and aggregate duration and amount
                groups: dict[tuple[str, str, int | None], list[dict]] = {}
                for e in entries:
                    key = (
                        e.get("matter_path") or "",
                        e.get("description") or "",
                        e.get("activity_group_id") if e.get("activity_group_id") is not None else e.get("id"),
                    )
                    groups.setdefault(key, []).append(e)
                preview_controls = [
                    ft.Row(
                        [
                            ft.Text("Matter", size=12, weight=ft.FontWeight.W_500, width=280),
                            ft.Text("Description", size=12, weight=ft.FontWeight.W_500, width=180),
                            ft.Text("Duration", size=12, weight=ft.FontWeight.W_500, width=80),
                            ft.Text("Amount (€)", size=12, weight=ft.FontWeight.W_500, width=90),
                        ],
                        spacing=8,
                    ),
                ]
                for (matter_path, description, _), group_entries in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
                    total_dur = sum(ent.get("duration_seconds", 0) or 0 for ent in group_entries)
                    total_amount = sum(ent.get("amount_eur", 0.0) or 0 for ent in group_entries)
                    rate_source = group_entries[0].get("rate_source", "user")
                    color = _rate_source_color(rate_source)
                    preview_controls.append(
                        ft.Row(
                            [
                                ft.Text((matter_path or "")[:40], size=12, width=280, overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text((description or "")[:30], size=12, width=180, overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(format_elapsed_hm(total_dur), size=12, width=80),
                                ft.Text(format_eur(total_amount), size=12, color=color, width=90),
                            ],
                            spacing=8,
                        )
                    )
            if timesheet_preview_ref.current:
                timesheet_preview_ref.current.controls = preview_controls
            page.update()

        def _options_by_client_timesheet(opts: list[tuple[int, str]]) -> dict:
            by_client = defaultdict(list)
            for mid, path in opts:
                client = path.split(" > ")[0] if " > " in path else path
                by_client[client].append((mid, path))
            for client in by_client:
                by_client[client].sort(key=lambda x: x[1])
            return by_client

        def _build_timesheet_list_controls(query: str):
            path_list = self.db.get_matters_with_full_paths(
                include_all_users=current_user_is_admin
            )
            q = (query or "").strip().lower()
            if q:
                flat = [(mid, path) for mid, path in path_list if path and q in path.lower()][:30]
                return [
                    ft.ListTile(
                        title=ft.Text(path, size=14),
                        leading=ft.Checkbox(
                            value=mid in timesheet_selected_ids,
                            on_change=lambda e, mid=mid: _on_timesheet_check(mid, e.control.value),
                        ),
                    )
                    for mid, path in flat
                ]
            controls = []
            by_client = _options_by_client_timesheet(path_list)
            # Reuse reporting sort preference: most not-invoiced or most accrued (total) time
            sort_value = (page.data or {}).get("reporting_sort") or "most_uninvoiced"
            rows_data = self.db.get_time_by_client_and_matter_detailed()
            client_sort_key: dict[str, float] = defaultdict(float)
            for row in rows_data:
                client_name, _, total_sec, not_inv_sec, *_ = row
                if sort_value == "most_uninvoiced":
                    client_sort_key[client_name] += not_inv_sec
                else:
                    client_sort_key[client_name] += total_sec
            client_order = sorted(
                by_client.keys(),
                key=lambda c: client_sort_key.get(c, 0.0),
                reverse=True,
            )
            for client_name in client_order:
                items = by_client[client_name]
                mids = [mid for mid, _ in items]
                is_exp = client_name in timesheet_expanded
                client_all_checked = all(mid in timesheet_selected_ids for mid in mids)
                controls.append(
                    ft.ListTile(
                        leading=ft.Checkbox(
                            value=client_all_checked,
                            on_change=lambda e, m=mids: _on_timesheet_client_check(m, e.control.value),
                        ),
                        title=ft.Text(client_name, weight=ft.FontWeight.W_500, size=14),
                        subtitle=ft.Text(f"{len(items)} matter(s)", size=12),
                        trailing=ft.Icon(ft.Icons.EXPAND_LESS if is_exp else ft.Icons.EXPAND_MORE, size=20),
                        on_click=lambda e, c=client_name: _on_toggle_timesheet_expanded(c),
                    ),
                )
                controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.ListTile(
                                    title=ft.Text(path, size=14),
                                    leading=ft.Checkbox(
                                        value=mid in timesheet_selected_ids,
                                        on_change=lambda e, mid=mid: _on_timesheet_check(mid, e.control.value),
                                    ),
                                )
                                for mid, path in items
                            ],
                        ),
                        visible=is_exp,
                        padding=ft.Padding.only(left=20),
                    ),
                )
            return controls

        def refresh_timesheet_list():
            if timesheet_list_ref.current:
                search_val = timesheet_search_ref.current.value if timesheet_search_ref.current else ""
                timesheet_list_ref.current.controls = _build_timesheet_list_controls(search_val)
                page.update()

        if page.data is None:
            page.data = {}
        page.data["refresh_timesheet_matters"] = refresh_timesheet_list

        def _on_toggle_timesheet_expanded(client_name: str):
            timesheet_expanded.symmetric_difference_update([client_name])
            if timesheet_list_ref.current:
                timesheet_list_ref.current.controls = _build_timesheet_list_controls(
                    timesheet_search_ref.current.value if timesheet_search_ref.current else ""
                )
                page.update()

        def _on_timesheet_check(matter_id: int, checked: bool):
            nonlocal timesheet_selected_ids
            if checked:
                timesheet_selected_ids.add(matter_id)
                timesheet_selected_ids |= self.db.get_descendant_matter_ids(
                    matter_id, include_all_users=current_user_is_admin
                )
            else:
                timesheet_selected_ids.discard(matter_id)
            if timesheet_list_ref.current:
                timesheet_list_ref.current.controls = _build_timesheet_list_controls(
                    timesheet_search_ref.current.value if timesheet_search_ref.current else ""
                )
                page.update()

        def _on_timesheet_client_check(matter_ids: list[int], checked: bool):
            """Check/uncheck client checkbox: select or clear all matters for that client."""
            nonlocal timesheet_selected_ids
            if checked:
                timesheet_selected_ids |= set(matter_ids)
            else:
                timesheet_selected_ids -= set(matter_ids)
            if timesheet_list_ref.current:
                timesheet_list_ref.current.controls = _build_timesheet_list_controls(
                    timesheet_search_ref.current.value if timesheet_search_ref.current else ""
                )
                page.update()

        def _on_search_change(_):
            if timesheet_list_ref.current and timesheet_search_ref.current:
                timesheet_list_ref.current.controls = _build_timesheet_list_controls(
                    timesheet_search_ref.current.value
                )
                page.update()

        def _on_timesheet_sort_change(e):
            val = getattr(e.control, "value", None) or getattr(e, "data", None)
            if page.data is not None and val:
                page.data["reporting_sort"] = val
                refresh_timesheet_list()

        def _show_mark_invoiced_dialog(out_path: Path, entry_ids: list):
            def _on_mark_yes(_):
                self.db.mark_entries_invoiced(entry_ids)
                dialog.open = False
                page.snack_bar = ft.SnackBar(content=ft.Text("Entries marked as invoiced."))
                page.snack_bar.open = True
                page.update()

            def _on_mark_no(_):
                dialog.open = False
                page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("Mark as invoiced?"),
                content=ft.Text(
                    f"Timesheet saved to {out_path}. Do you want to mark the exported entries as invoiced?"
                ),
                actions=[
                    ft.TextButton("No", on_click=_on_mark_no),
                    ft.ElevatedButton("Yes", on_click=_on_mark_yes),
                ],
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        def _write_and_confirm_export(out_path: Path, payload: dict, entry_ids: list) -> bool:
            """Write payload to out_path and show mark-as-invoiced dialog. Returns True if written."""
            try:
                out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except OSError as err:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Could not save file: {err}"))
                page.snack_bar.open = True
                page.update()
                return False
            _show_mark_invoiced_dialog(out_path, entry_ids)
            return True

        def _default_export_dir() -> Path:
            downloads = Path.home() / "Downloads"
            if downloads.is_dir():
                return downloads
            exports_dir = Path(__file__).resolve().parent / "exports"
            exports_dir.mkdir(exist_ok=True)
            return exports_dir

        # No FilePicker (causes "Unknown control" on some Flet clients). Use a folder path field instead.
        export_dir_ref = ft.Ref[ft.TextField]()

        def _do_export(_):
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
            default_name = f"timesheet_{timestamp}.json"
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
            _write_and_confirm_export(out_path, payload, entry_ids)
            page.update()

        default_dir_str = str(_default_export_dir())
        search_field = ft.TextField(
            label="Search matters by name or path",
            width=400,
            ref=timesheet_search_ref,
            on_change=_on_search_change,
        )
        export_dir_field = ft.TextField(
            label="Save to folder",
            value=default_dir_str,
            width=500,
            ref=export_dir_ref,
            hint_text="e.g. /home/you/Downloads or leave default",
        )
        only_not_invoiced_cb = ft.Checkbox(
            label="Only include entries not yet marked as invoiced",
            value=True,
            ref=only_not_invoiced_ref,
        )
        export_all_users_cb = ft.Checkbox(
            label="Export all users' time (admin only)",
            value=False,
            ref=export_all_users_ref,
            visible=current_user_is_admin,
        )
        list_column = ft.Column(
            ref=timesheet_list_ref,
            controls=_build_timesheet_list_controls(""),
            scroll=ft.ScrollMode.AUTO,
        )
        return ft.Column(
            [
                ft.Text("Timesheet", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=16),
                search_field,
                ft.Container(height=8),
                export_dir_field,
                ft.Container(height=8),
                only_not_invoiced_cb,
                ft.Container(height=8),
                export_all_users_cb,
                ft.Container(height=8),
                ft.Row(
                    [
                        ft.ElevatedButton("Preview", icon=ft.Icons.LIST, on_click=_do_preview),
                        ft.ElevatedButton("Export timesheet", icon=ft.Icons.UPLOAD, on_click=_do_export),
                    ],
                    spacing=12,
                ),
                ft.Container(height=16),
                ft.Text("Preview (amounts by rate source: green=matter, orange=upper, red=user)", size=12),
                ft.Container(height=6),
                ft.Container(
                    content=ft.Column(ref=timesheet_preview_ref, scroll=ft.ScrollMode.AUTO),
                    height=180,
                ),
                ft.Container(height=16),
                ft.Row(
                    [
                        ft.Text("Matters", size=16, weight=ft.FontWeight.W_500),
                        ft.Dropdown(
                            label="Sort clients by",
                            width=280,
                            value=(page.data or {}).get("reporting_sort") or "most_uninvoiced",
                            options=[
                                ft.DropdownOption(key="most_uninvoiced", text="Most not invoiced time"),
                                ft.DropdownOption(key="most_accrued", text="Most accrued (total) time"),
                            ],
                            on_select=_on_timesheet_sort_change,
                        ),
                    ],
                    spacing=24,
                    alignment=ft.MainAxisAlignment.START,
                ),
                ft.Container(height=8),
                ft.Container(content=list_column, expand=True),
            ],
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_users_tab(self) -> ft.Control:
        """User administration (admin only): list users, add/edit/delete."""
        page = self.page
        db = self.db
        current_uid = db.current_user_id
        users_list_ref: ft.Ref[ft.Column] = ft.Ref()

        def build_user_rows():
            users = db.list_users()
            rows: list[ft.Control] = []
            for u in users:
                admin_badge = ft.Chip(label="Admin", height=28) if u.is_admin else ft.Container(width=50, height=28)
                is_self = u.id == current_uid
                edit_btn = ft.OutlinedButton(
                    "Edit",
                    on_click=lambda e, uid=u.id: open_edit_dialog(uid),
                )
                if is_self:
                    delete_btn = ft.Text("(you)", size=12)
                else:
                    delete_btn = ft.OutlinedButton(
                        "Delete",
                        on_click=lambda e, uid=u.id: open_delete_dialog(uid),
                    )
                rows.append(
                    ft.Row(
                        [
                            ft.Text(u.username, size=14, width=180),
                            admin_badge,
                            edit_btn,
                            delete_btn,
                        ],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.START,
                    )
                )
            return rows

        def refresh_list():
            if users_list_ref.current:
                users_list_ref.current.controls = build_user_rows()
                page.update()

        add_dialog_ref: list = []  # hold dialog so on_add_confirm can close it

        def on_add_confirm(_):
            if not add_dialog_ref:
                return
            add_dialog = add_dialog_ref[0]
            content = add_dialog.content
            username_tf = content.controls[0]
            password_tf = content.controls[1]
            admin_cb = content.controls[2]
            username = (username_tf.value or "").strip()
            password = (password_tf.value or "").strip()
            if not username or not password:
                return
            if len(password) < 4:
                return
            try:
                pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                db.create_user(username, pw_hash, is_admin=admin_cb.value)
                username_tf.value = ""
                password_tf.value = ""
                admin_cb.value = False
                close_dialog(add_dialog)
                refresh_list()
            except Exception as ex:
                username_tf.error_text = str(ex)
                page.update()

        add_user_btn = ft.ElevatedButton("Add")
        add_cancel_btn = ft.OutlinedButton("Cancel")
        add_dialog = ft.AlertDialog(
            title=ft.Text("Add user"),
            content=ft.Column(
                [
                    ft.TextField(label="Username", width=300),
                    ft.TextField(label="Password", password=True, can_reveal_password=True, width=300),
                    ft.Checkbox(label="Admin", value=False),
                    ft.Row(
                        [add_user_btn, add_cancel_btn],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
        add_user_btn.on_click = on_add_confirm
        add_cancel_btn.on_click = lambda _: close_dialog(add_dialog)
        add_dialog_ref.append(add_dialog)

        edit_dialog_user_id: list[int] = []
        edit_dialog_ref: list = []

        def on_edit_confirm(_):
            if not edit_dialog_ref:
                return
            edit_dialog = edit_dialog_ref[0]
            content = edit_dialog.content
            if not edit_dialog_user_id:
                return
            uid = edit_dialog_user_id[0]
            username_tf = content.controls[0]
            password_tf = content.controls[1]
            admin_cb = content.controls[2]
            rate_tf = content.controls[3]
            username = (username_tf.value or "").strip()
            new_password = (password_tf.value or "").strip()
            rate_str = (rate_tf.value or "").strip()
            default_rate: float | None = None
            if rate_str:
                try:
                    default_rate = float(rate_str)
                    if default_rate < 0:
                        username_tf.error_text = "Default hourly rate must be ≥ 0."
                        page.update()
                        return
                except ValueError:
                    username_tf.error_text = "Default hourly rate must be a number."
                    page.update()
                    return
            cur = db.get_user(current_uid)
            can_set_admin = cur and cur.is_admin and uid != current_uid
            try:
                kwargs: dict = {"username": username}
                if new_password:
                    kwargs["password_hash"] = bcrypt.hashpw(
                        new_password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8")
                if can_set_admin:
                    kwargs["is_admin"] = admin_cb.value
                kwargs["default_hourly_rate_euro"] = default_rate
                db.update_user(uid, **kwargs)
                close_dialog(edit_dialog)
                refresh_list()
            except Exception as ex:
                username_tf.error_text = str(ex)
                page.update()

        edit_save_btn = ft.ElevatedButton("Save")
        edit_cancel_btn = ft.OutlinedButton("Cancel")
        edit_dialog = ft.AlertDialog(
            title=ft.Text("Edit user"),
            content=ft.Column(
                [
                    ft.TextField(label="Username", width=300),
                    ft.TextField(label="New password (leave blank to keep)", password=True, can_reveal_password=True, width=300),
                    ft.Checkbox(label="Admin", value=False),
                    ft.TextField(label="Default hourly rate (€)", width=300, hint_text="Leave empty to clear"),
                    ft.Row(
                        [edit_save_btn, edit_cancel_btn],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
        edit_save_btn.on_click = on_edit_confirm
        edit_cancel_btn.on_click = lambda _: close_dialog(edit_dialog)
        edit_dialog_ref.append(edit_dialog)

        def open_edit_dialog(uid: int):
            user = db.get_user(uid)
            if not user:
                return
            edit_dialog_user_id.clear()
            edit_dialog_user_id.append(uid)
            content = edit_dialog.content
            content.controls[0].value = user.username
            content.controls[1].value = ""
            content.controls[2].value = user.is_admin
            content.controls[2].visible = current_uid != uid and (db.get_user(current_uid) and db.get_user(current_uid).is_admin)
            rate_val = getattr(user, "default_hourly_rate_euro", None)
            content.controls[3].value = str(rate_val) if rate_val is not None else ""
            content.controls[0].error_text = None
            edit_dialog.open = True
            page.update()

        delete_confirm_text_ref: ft.Ref[ft.Text] = ft.Ref()
        delete_user_id_holder: list[int] = []
        delete_confirm_dialog_ref: list = []

        def on_delete_confirm(_):
            if not delete_confirm_dialog_ref or not delete_user_id_holder or not delete_confirm_text_ref.current:
                return
            delete_confirm_dialog = delete_confirm_dialog_ref[0]
            try:
                uid = delete_user_id_holder[0]
                db.delete_user(uid)
                close_dialog(delete_confirm_dialog)
                refresh_list()
            except Exception as ex:
                delete_confirm_text_ref.current.value = str(ex)
                page.update()

        delete_confirm_btn = ft.ElevatedButton("Delete")
        delete_cancel_btn = ft.OutlinedButton("Cancel")
        delete_confirm_dialog = ft.AlertDialog(
            title=ft.Text("Delete user?"),
            content=ft.Column(
                [
                    ft.Text("", ref=delete_confirm_text_ref, width=400),
                    ft.Row(
                        [delete_confirm_btn, delete_cancel_btn],
                        spacing=12,
                    ),
                ],
                tight=True,
            ),
        )
        delete_confirm_btn.on_click = on_delete_confirm
        delete_cancel_btn.on_click = lambda _: close_dialog(delete_confirm_dialog)
        delete_confirm_dialog_ref.append(delete_confirm_dialog)

        def open_delete_dialog(uid: int):
            user = db.get_user(uid)
            if not user:
                return
            delete_user_id_holder.clear()
            delete_user_id_holder.append(uid)
            if delete_confirm_text_ref.current:
                delete_confirm_text_ref.current.value = f'Delete user "{user.username}"? This cannot be undone.'
            delete_confirm_dialog.open = True
            page.update()

        def close_dialog(dlg: ft.AlertDialog):
            dlg.open = False
            page.update()

        def open_add_dialog(_):
            add_dialog.content.controls[0].value = ""
            add_dialog.content.controls[1].value = ""
            add_dialog.content.controls[2].value = False
            add_dialog.content.controls[0].error_text = None
            add_dialog.open = True
            page.update()

        page.overlay.append(add_dialog)
        page.overlay.append(edit_dialog)
        page.overlay.append(delete_confirm_dialog)

        # Database backup (admin only - this is the Users tab)
        def _default_backup_dir() -> Path:
            downloads = Path.home() / "Downloads"
            if downloads.is_dir():
                return downloads
            exports_dir = Path(__file__).resolve().parent / "exports"
            exports_dir.mkdir(exist_ok=True)
            return exports_dir

        backup_export_dir_ref = ft.Ref[ft.TextField]()
        backup_import_path_ref = ft.Ref[ft.TextField]()

        def _do_backup_export(_):
            if not db.current_user_is_admin():
                page.snack_bar = ft.SnackBar(content=ft.Text("Only admin can export the full database."))
                page.snack_bar.open = True
                page.update()
                return
            try:
                data = db.export_full_database()
            except ValueError as e:
                page.snack_bar = ft.SnackBar(content=ft.Text(str(e)))
                page.snack_bar.open = True
                page.update()
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"sentinel_backup_{timestamp}.json"
            dir_str = (backup_export_dir_ref.current.value or "").strip() if backup_export_dir_ref.current else ""
            export_dir = Path(dir_str).expanduser() if dir_str else _default_backup_dir()
            try:
                export_dir.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Cannot create folder: {err}"))
                page.snack_bar.open = True
                page.update()
                return
            out_path = export_dir / default_name
            try:
                out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError as err:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Cannot save file: {err}"))
                page.snack_bar.open = True
                page.update()
                return
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Backup saved to {out_path}"))
            page.snack_bar.open = True
            page.update()

        import_confirm_dialog_ref: list = []

        def _do_import_confirm(_):
            if not import_confirm_dialog_ref:
                return
            path_str = (backup_import_path_ref.current.value or "").strip() if backup_import_path_ref.current else ""
            if not path_str:
                page.snack_bar = ft.SnackBar(content=ft.Text("Enter the path to the backup file."))
                page.snack_bar.open = True
                page.update()
                return
            path = Path(path_str).expanduser()
            if not path.is_file():
                page.snack_bar = ft.SnackBar(content=ft.Text(f"File not found: {path}"))
                page.snack_bar.open = True
                page.update()
                return
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError) as e:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid backup file: {e}"))
                page.snack_bar.open = True
                page.update()
                return
            try:
                db.import_full_database(data)
            except ValueError as e:
                page.snack_bar = ft.SnackBar(content=ft.Text(str(e)))
                page.snack_bar.open = True
                page.update()
                return
            except Exception as e:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Import failed: {e}"))
                page.snack_bar.open = True
                page.update()
                return
            close_dialog(import_confirm_dialog_ref[0])
            page.snack_bar = ft.SnackBar(content=ft.Text("Database restored. Please log in again."))
            page.snack_bar.open = True
            page.update()
            # Clear stored login and show login view
            async def _clear_and_logout():
                await page.shared_preferences.set(STORAGE_USER_ID, "")
                await page.shared_preferences.set(STORAGE_USERNAME, "")
                cb = (page.data or {}).get("logout_callback")
                if cb:
                    cb()

            page.run_task(_clear_and_logout)

        def _open_import_confirm(_):
            path_str = (backup_import_path_ref.current.value or "").strip() if backup_import_path_ref.current else ""
            if not path_str:
                page.snack_bar = ft.SnackBar(content=ft.Text("Enter the path to the backup file."))
                page.snack_bar.open = True
                page.update()
                return
            path = Path(path_str).expanduser()
            if not path.is_file():
                page.snack_bar = ft.SnackBar(content=ft.Text(f"File not found: {path}"))
                page.snack_bar.open = True
                page.update()
                return
            import_confirm_dialog.open = True
            page.update()

        import_confirm_btn = ft.ElevatedButton("Import", on_click=_do_import_confirm)
        import_cancel_btn = ft.TextButton("Cancel", on_click=lambda _: close_dialog(import_confirm_dialog))
        import_confirm_dialog = ft.AlertDialog(
            title=ft.Text("Import full database?"),
            content=ft.Text("This will replace all users, matters, and time entries with the backup. Continue?"),
            actions=[import_cancel_btn, import_confirm_btn],
        )
        import_confirm_dialog_ref.append(import_confirm_dialog)
        page.overlay.append(import_confirm_dialog)

        list_col = ft.Column(ref=users_list_ref, controls=build_user_rows(), scroll=ft.ScrollMode.AUTO)

        backup_export_dir_field = ft.TextField(
            label="Save to folder",
            value=str(_default_backup_dir()),
            width=500,
            ref=backup_export_dir_ref,
            hint_text="Folder for backup file",
        )
        backup_import_path_field = ft.TextField(
            label="Backup file path",
            value="",
            width=500,
            ref=backup_import_path_ref,
            hint_text="Full path to sentinel_backup_YYYYMMDD_HHMMSS.json",
        )

        return ft.Column(
            [
                ft.Text("User administration", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=16),
                ft.ElevatedButton("Add user", icon=ft.Icons.ADD, on_click=open_add_dialog),
                ft.Container(height=16),
                ft.Text("Users", size=16, weight=ft.FontWeight.W_500),
                ft.Container(height=8),
                ft.Container(content=list_col, expand=True),
                ft.Container(height=24),
                ft.Text("Database backup", size=18, weight=ft.FontWeight.W_500),
                ft.Container(height=8),
                backup_export_dir_field,
                ft.Container(height=4),
                ft.ElevatedButton("Export full database", icon=ft.Icons.SAVE, on_click=_do_backup_export),
                ft.Container(height=16),
                backup_import_path_field,
                ft.Container(height=4),
                ft.ElevatedButton("Import full database", icon=ft.Icons.UPLOAD, on_click=_open_import_confirm),
            ],
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            scroll=ft.ScrollMode.AUTO,
        )


def _build_create_first_admin_view(
    page: ft.Page,
    login_db: DatabaseManager,
    on_success: Callable[[int, str], None],
) -> ft.Control:
    """Build 'Create first admin' form when no users exist. On success call on_success(user_id, username)."""
    username_field = ft.TextField(
        label="Username (admin)",
        autofocus=True,
        text_align=ft.TextAlign.LEFT,
        width=300,
    )
    password_field = ft.TextField(
        label="Password",
        password=True,
        can_reveal_password=True,
        text_align=ft.TextAlign.LEFT,
        width=300,
    )
    error_text = ft.Text("", color=ft.Colors.RED, visible=False)
    loading = ft.ProgressRing(visible=False)

    def _do_create(_):
        username = (username_field.value or "").strip()
        password = (password_field.value or "").strip()
        if not username or not password:
            error_text.value = "Enter username and password."
            error_text.visible = True
            loading.visible = False
            page.update()
            return
        if len(password) < 4:
            error_text.value = "Password must be at least 4 characters."
            error_text.visible = True
            loading.visible = False
            page.update()
            return
        error_text.visible = False
        loading.visible = True
        page.update()
        try:
            pw_hash = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            user_id = login_db.create_first_admin(username, pw_hash)
        except Exception as e:
            error_text.value = str(e) or "Failed to create admin."
            error_text.visible = True
            loading.visible = False
            page.update()
            return
        if user_id is None:
            error_text.value = "A user already exists. Use the login form."
            error_text.visible = True
            loading.visible = False
            page.update()
            return
        loading.visible = False
        page.update()
        on_success(user_id, username)

    password_field.on_submit = _do_create
    create_btn = ft.ElevatedButton("Create admin", on_click=_do_create)
    backend_hint = ft.Text(
        f"Backend: {login_db.backend_description()}",
        size=12,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    if login_db.backend_description() == "SQLite (local)":
        backend_hint.tooltip = "If you installed with --postgres, start the app from the launcher (sentinel-solo) so config.env is loaded."
    return ft.Column(
        [
            ft.Text("Sentinel Solo", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=8),
            backend_hint,
            ft.Container(height=4),
            ft.Text("No users yet. Create the first admin account.", size=14),
            ft.Container(height=24),
            username_field,
            ft.Container(height=12),
            password_field,
            ft.Container(height=12),
            error_text,
            ft.Container(height=12),
            ft.Row([loading, create_btn], spacing=12),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        expand=True,
    )


def _build_login_view(
    page: ft.Page,
    login_db: DatabaseManager,
    on_success: Callable[[int, str], None],  # sync; can schedule async work via page.run_task
) -> ft.Control:
    """Build login form: username, password, Log in. On success call on_success(user_id, username)."""
    username_field = ft.TextField(
        label="Username",
        autofocus=True,
        text_align=ft.TextAlign.LEFT,
        width=300,
    )
    password_field = ft.TextField(
        label="Password",
        password=True,
        can_reveal_password=True,
        text_align=ft.TextAlign.LEFT,
        width=300,
    )
    error_text = ft.Text("", color=ft.Colors.RED, visible=False)
    loading = ft.ProgressRing(visible=False)

    def _do_login(_):
        username = (username_field.value or "").strip()
        password = (password_field.value or "").strip()
        if not username or not password:
            error_text.value = "Enter username and password."
            error_text.visible = True
            loading.visible = False
            page.update()
            return
        error_text.visible = False
        loading.visible = True
        page.update()
        try:
            creds = login_db.get_login_credentials(username)
            if creds and bcrypt.checkpw(
                password.encode("utf-8"),
                creds[1].encode("utf-8") if isinstance(creds[1], str) else creds[1],
            ):
                user_id = creds[0]
            else:
                user_id = None
        except Exception:
            user_id = None
        if user_id is None:
            error_text.value = "Invalid username or password."
            error_text.visible = True
            loading.visible = False
            page.update()
            return
        loading.visible = False
        page.update()
        on_success(user_id, username)

    password_field.on_submit = _do_login
    login_btn = ft.ElevatedButton("Log in", on_click=_do_login)
    return ft.Column(
        [
            ft.Text("Sentinel Solo", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=24),
            username_field,
            ft.Container(height=12),
            password_field,
            ft.Container(height=12),
            error_text,
            ft.Container(height=12),
            ft.Row([loading, login_btn], spacing=12),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        expand=True,
    )


async def main(page: ft.Page) -> None:
    login_db = DatabaseManager()
    login_db.init_db()

    async def go_main(user_id: int, username: str) -> None:
        await page.shared_preferences.set(STORAGE_USER_ID, str(user_id))
        await page.shared_preferences.set(STORAGE_USERNAME, username)
        page.controls.clear()
        user_db = DatabaseManager(current_user_id=user_id)
        is_admin = user_db.get_current_user_is_admin()
        app = SentinelApp(page, user_db)
        app.setup(
            logout_callback=show_login,
            current_username=username,
            current_user_is_admin=is_admin,
        )
        page.update()

    async def _go_main_task(uid: int, uname: str) -> None:
        await go_main(uid, uname)

    def on_login_success(uid: int, uname: str) -> None:
        page.run_task(_go_main_task, uid, uname)

    def show_login() -> None:
        page.controls.clear()
        if page.data is not None:
            page.data.pop("app", None)
        # If no users exist, show "Create first admin" instead of login
        if not login_db.has_any_user():
            view = _build_create_first_admin_view(
                page,
                login_db,
                on_success=on_login_success,
            )
        else:
            view = _build_login_view(
                page,
                login_db,
                on_success=on_login_success,
            )
        page.add(ft.SafeArea(ft.Container(view, expand=True)))
        page.update()

    # Always show the login / first-admin screen on app start.
    show_login()


if __name__ == "__main__":
    ft.run(main)
