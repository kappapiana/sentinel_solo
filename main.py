"""
Sentinel Solo: Flet UI with Timer and Manage Matters.
"""
import asyncio
from datetime import datetime

import flet as ft

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

    # When no matters under a client exist, show message instead of dropdown
    timer_controls = [
        ft.Text("Timer", size=24, weight=ft.FontWeight.BOLD),
        ft.Container(height=16),
    ]
    if options:
        timer_controls.extend([dropdown, ft.Container(height=24), label, ft.Container(height=24), ft.Row([start_btn, stop_btn], spacing=12)])
    else:
        timer_controls.append(
            ft.Text("Add at least one matter under a client to log time.", size=14)
        )

    return ft.Column(
        timer_controls,
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )


def build_matters_tab(page: ft.Page, list_ref: ft.Ref[ft.Column]) -> ft.Control:
    """Build the Manage Matters tab: list of matters and add form."""
    name_field = ft.Ref[ft.TextField]()
    code_field = ft.Ref[ft.TextField]()
    parent_dropdown = ft.Ref[ft.Dropdown]()

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
            return
        pid = None
        if parent_dropdown.current and parent_dropdown.current.value:
            pid = int(parent_dropdown.current.value)
        add_matter(name=n.strip(), matter_code=c.strip(), parent_id=pid)
        name_field.current.value = ""
        code_field.current.value = ""
        if parent_dropdown.current:
            parent_dropdown.current.value = None
        refresh_list()
        page.update()

    path_options = get_matters_with_full_paths()
    parent_dropdown_control = ft.Dropdown(
        ref=parent_dropdown,
        label="Parent matter (optional)",
        width=400,
        options=[ft.DropdownOption(key=str(mid), text=path) for mid, path in path_options],
        value=None,
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
            ft.TextField(ref=name_field, label="Name", width=400),
            ft.TextField(ref=code_field, label="Matter code", width=400),
            parent_dropdown_control,
            ft.Container(height=8),
            ft.ElevatedButton("Add matter", icon=ft.Icons.ADD, on_click=on_add),
            ft.Container(height=24),
            ft.Text("Matters", size=16, weight=ft.FontWeight.W_500),
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
        table = ft.DataTable(
            columns=[
                ft.DataColumn(label=ft.Text("Client")),
                ft.DataColumn(label=ft.Text("Matter")),
                ft.DataColumn(label=ft.Text("Time spent")),
            ],
            rows=[
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(client)),
                        ft.DataCell(ft.Text(matter_path)),
                        ft.DataCell(ft.Text(format_elapsed(total_seconds))),
                    ],
                )
                for client, matter_path, total_seconds in rows_data
            ],
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
