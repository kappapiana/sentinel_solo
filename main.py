"""
Sentinel Solo: Flet UI with Timer and Manage Matters.
"""
import asyncio
from collections import defaultdict
from datetime import datetime

import flet as ft

from sqlalchemy.exc import IntegrityError

from database_manager import (
    init_db,
    add_matter,
    start_timer,
    stop_timer,
    get_matters_with_full_paths,
    get_all_matters,
    get_time_by_client_and_matter,
)


def format_elapsed(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_timer_tab(
    page: ft.Page,
    timer_label: ft.Ref[ft.Text],
    matter_dropdown: ft.Ref[ft.Dropdown],
    running_ref: list[bool],
    start_time_ref: list[datetime | None],
) -> ft.Control:
    """Build the Timer tab: dropdown (full path), Start/Stop, live-updating label.
    Only matters under a client are shown (no time on client/root)."""
    options = get_matters_with_full_paths(for_timer=True)
    dropdown = ft.Dropdown(
        ref=matter_dropdown,
        label="Matter",
        width=400,
        options=[ft.DropdownOption(key=str(mid), text=path) for mid, path in options],
        value=str(options[0][0]) if options else None,
        enable_filter=True,
        editable=True,
    )
    label = ft.Text(
        ref=timer_label,
        value="00:00:00",
        size=48,
        weight=ft.FontWeight.W_500,
    )
    start_btn = ft.ElevatedButton("Start", icon=ft.Icons.PLAY_ARROW)
    stop_btn = ft.OutlinedButton("Stop", icon=ft.Icons.STOP)

    async def timer_loop():
        while running_ref[0] and start_time_ref[0]:
            await asyncio.sleep(1)
            if not running_ref[0]:
                break
            elapsed = (datetime.now() - start_time_ref[0]).total_seconds()
            if timer_label.current:
                timer_label.current.value = format_elapsed(elapsed)
                page.update()

    def on_start(_):
        if not matter_dropdown.current or not matter_dropdown.current.value:
            return
        if running_ref[0]:
            return
        matter_id = int(matter_dropdown.current.value)
        try:
            entry = start_timer(matter_id)
        except ValueError as e:
            page.snack_bar = ft.SnackBar(ft.Text(str(e)), open=True)
            page.update()
            return
        start_time_ref[0] = entry.start_time
        running_ref[0] = True
        timer_label.current.value = "00:00:00"
        page.run_task(timer_loop)
        page.update()

    def on_stop(_):
        if not running_ref[0]:
            return
        running_ref[0] = False
        entry = stop_timer()
        if entry and timer_label.current:
            timer_label.current.value = format_elapsed(entry.duration_seconds)
        page.update()

    start_btn.on_click = on_start
    stop_btn.on_click = on_stop

    timer_controls = [
        ft.Text("Timer", size=24, weight=ft.FontWeight.BOLD),
        ft.Container(height=16),
    ]
    if not options:
        timer_controls.append(
            ft.Text("Add at least one matter under a client to log time.", size=14)
        )
        timer_controls.append(ft.Container(height=16))
    timer_controls.extend([
        dropdown,
        ft.Container(height=24),
        label,
        ft.Container(height=24),
        ft.Row([start_btn, stop_btn], spacing=12),
    ])

    return ft.Column(
        timer_controls,
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )


def build_matters_tab(page: ft.Page, list_ref: ft.Ref[ft.Column]) -> ft.Control:
    """Build the Manage Matters tab: add Clients (root) or Matters (under a client/parent)."""
    name_field = ft.Ref[ft.TextField]()
    code_field = ft.Ref[ft.TextField]()
    parent_dropdown = ft.Ref[ft.Dropdown]()
    add_type_ref = ft.Ref[ft.SegmentedButton]()
    parent_section_ref = ft.Ref[ft.Container]()

    def refresh_list():
        matters = get_all_matters()
        path_list = get_matters_with_full_paths()
        path_by_id = {mid: path for mid, path in path_list}
        if list_ref.current:
            list_ref.current.controls = [
                ft.ListTile(
                    title=ft.Text(path_by_id.get(m.id, m.name)),
                    subtitle=ft.Text(m.matter_code),
                )
                for m in matters
            ]
            page.update()

    def on_add(_):
        if not name_field.current or not code_field.current:
            return
        n = name_field.current.value or ""
        c = code_field.current.value or ""
        if not n.strip() or not c.strip():
            page.snack_bar = ft.SnackBar(ft.Text("Name and code are required."), open=True)
            page.update()
            return
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
        try:
            add_matter(name=n.strip(), matter_code=c.strip(), parent_id=pid)
        except IntegrityError:
            page.snack_bar = ft.SnackBar(
                ft.Text("A matter with this code already exists. Use a unique Matter code."),
                open=True,
            )
            page.update()
            return
        name_field.current.value = ""
        code_field.current.value = ""
        if parent_dropdown.current:
            parent_dropdown.current.value = None
        refresh_list()
        # Refresh parent dropdown so the new matter can be selected as parent
        if parent_dropdown.current:
            path_options = get_matters_with_full_paths()
            parent_dropdown.current.options = [
                ft.DropdownOption(key=str(mid), text=path) for mid, path in path_options
            ]
        page.update()

    def on_type_change(e):
        if parent_section_ref.current and add_type_ref.current:
            parent_section_ref.current.visible = (
                add_type_ref.current.selected and add_type_ref.current.selected[0] == "matter"
            )
            page.update()

    path_options = get_matters_with_full_paths()
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
    # Populate list at build time so we never update a control before it's on the page
    matters = get_all_matters()
    path_list = get_matters_with_full_paths()
    path_by_id = {mid: path for mid, path in path_list}
    initial_list_controls = [
        ft.ListTile(
            title=ft.Text(path_by_id.get(m.id, m.name)),
            subtitle=ft.Text(m.matter_code),
        )
        for m in matters
    ]
    list_column = ft.Column(
        ref=list_ref,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        controls=initial_list_controls,
    )

    return ft.Column(
        [
            ft.Text("Manage Matters", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(height=16),
            ft.Text("Add as", size=14),
            ft.Container(height=4),
            add_type_button,
            ft.Container(height=16),
            ft.TextField(ref=name_field, label="Name", width=400),
            ft.TextField(ref=code_field, label="Code", width=400),
            parent_section,
            ft.Container(height=8),
            ft.ElevatedButton("Add", icon=ft.Icons.ADD, on_click=on_add),
            ft.Container(height=24),
            ft.Text("Clients & Matters", size=16, weight=ft.FontWeight.W_500),
            ft.Container(height=8),
            list_column,
        ],
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )


def build_reporting_tab(page: ft.Page) -> ft.Control:
    """Build the Reporting tab: table of Client | Matter | Time spent."""
    rows_data = get_time_by_client_and_matter()
    if not rows_data:
        content = ft.Column(
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
    else:
        # Group by client, compute client totals; emit Total row then detail rows per client
        by_client: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for client_name, matter_path, total_seconds in rows_data:
            by_client[client_name].append((matter_path, total_seconds))
        table_rows = []
        for client_name in sorted(by_client.keys()):
            matter_rows = by_client[client_name]
            client_total_seconds = sum(sec for _, sec in matter_rows)
            table_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(client_name)),
                        ft.DataCell(ft.Text("Total")),
                        ft.DataCell(ft.Text(format_elapsed(client_total_seconds))),
                    ],
                )
            )
            for matter_path, total_seconds in sorted(matter_rows, key=lambda r: r[0]):
                table_rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(client_name)),
                            ft.DataCell(ft.Text(matter_path)),
                            ft.DataCell(ft.Text(format_elapsed(total_seconds))),
                        ],
                    )
                )
        table = ft.DataTable(
            columns=[
                ft.DataColumn(label=ft.Text("Client")),
                ft.DataColumn(label=ft.Text("Matter")),
                ft.DataColumn(label=ft.Text("Time spent")),
            ],
            rows=table_rows,
        )
        content = ft.Column(
            [
                ft.Text("Reporting", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=16),
                ft.Container(
                    content=ft.Column([table], scroll=ft.ScrollMode.AUTO),
                    expand=True,
                ),
            ],
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )
    return content


def main(page: ft.Page) -> None:
    page.theme_mode = ft.ThemeMode.DARK
    page.title = "Sentinel Solo"
    page.padding = 24

    timer_label_ref: ft.Ref[ft.Text] = ft.Ref()
    matter_dropdown_ref: ft.Ref[ft.Dropdown] = ft.Ref()
    running_ref: list[bool] = [False]
    start_time_ref: list[datetime | None] = [None]
    matters_list_ref: ft.Ref[ft.Column] = ft.Ref()
    body_ref: ft.Ref[ft.Container] = ft.Ref()

    timer_tab = build_timer_tab(
        page, timer_label_ref, matter_dropdown_ref, running_ref, start_time_ref
    )
    matters_tab = build_matters_tab(page, matters_list_ref)
    reporting_tab = build_reporting_tab(page)

    timer_container = ft.Container(content=timer_tab, expand=True)
    matters_container = ft.Container(content=matters_tab, expand=True)
    reporting_container = ft.Container(content=reporting_tab, expand=True)

    def show_timer(_):
        body_ref.current.content = timer_container
        if matter_dropdown_ref.current:
            opts = get_matters_with_full_paths(for_timer=True)
            matter_dropdown_ref.current.options = [
                ft.DropdownOption(key=str(mid), text=path) for mid, path in opts
            ]
            if opts and not matter_dropdown_ref.current.value:
                matter_dropdown_ref.current.value = str(opts[0][0])
        page.update()

    def show_matters(_):
        body_ref.current.content = matters_container
        page.update()

    def show_reporting(_):
        # Rebuild so data is current when opening the tab
        reporting_container.content = build_reporting_tab(page)
        body_ref.current.content = reporting_container
        page.update()

    def on_rail_change(e):
        idx = e.control.selected_index
        if idx == 0:
            show_timer(e)
        elif idx == 1:
            show_matters(e)
        else:
            show_reporting(e)

    rail = ft.NavigationRail(
        selected_index=0,
        extended=True,
        min_extended_width=180,
        label_type=ft.NavigationRailLabelType.ALL,
        destinations=[
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
        ],
        on_change=on_rail_change,
    )

    body = ft.Container(ref=body_ref, content=timer_container, expand=True)

    page.add(
        ft.Row(
            [
                rail,
                ft.VerticalDivider(width=1),
                body,
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    init_db()
    ft.run(main)
