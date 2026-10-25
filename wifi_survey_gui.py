import base64
import math
import os
import struct
import subprocess
import sys
import tkinter as tk
import zlib
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PROJECT_DIR = Path(__file__).resolve().parent
FLOORS = [f"P{number}" for number in range(5)]
sys.path.insert(0, str(PROJECT_DIR / "validation"))
from map_measurements import (
    build_router_coverage_models,
    load_access_point_inventory,
    load_map_measurements,
    summarize_router_eduroam_signal,
)


def _format_measurement(value, units):
    if value is None:
        return "—"
    return f"{value:.1f} {units}"


def _coverage_overlay_png(radius_70, radius_40, max_radius, alpha=80):
    size = max(1, math.ceil(max_radius * 2 + 1))
    center = (size - 1) / 2
    rows = []
    for y in range(size):
        row = bytearray((0,))
        dy = y - center
        for x in range(size):
            distance = math.hypot(x - center, dy)
            if distance <= radius_70:
                row.extend((47, 158, 68, alpha))
            elif distance <= radius_40:
                row.extend((255, 212, 59, alpha))
            elif distance <= max_radius:
                row.extend((224, 49, 49, alpha))
            else:
                row.extend((0, 0, 0, 0))
        rows.append(bytes(row))

    def chunk(name, data):
        payload = name + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    png_data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack(">2I5B", size, size, 8, 6, 0, 0, 0),
        )
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png_data)


class SurveyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WiFi Survey - Seleccionar posición")
        self.root.geometry("1050x760")
        self.root.minsize(720, 520)
        self.plan_image = None
        self.image_path = None
        self.image_size = None
        self.selected_position = None
        self.displayed_point_position = None
        self.capture_process = None
        self.capture_position = None
        self.measured_points = {}
        self.access_points = []
        self.coverage_models = []
        self.inventory_error = None
        self.coverage_mode = False
        self.coverage_router_selector = None
        self.coverage_router_selector_checks = {}
        self.coverage_fill_images = []

        self.building_var = tk.StringVar(value="FIC")
        self.floor_var = tk.StringVar(value="P1")
        self.point_var = tk.StringVar(value="P1")
        self.orientation_var = tk.StringVar(value="0-Norte")
        self.interval_var = tk.StringVar(value="3")
        self.samples_var = tk.StringVar(value="10")
        self.procedure_var = tk.StringVar()
        self.all_networks_var = tk.BooleanVar(value=False)
        self.position_text = tk.StringVar(value="Haz clic en el plano para marcar la posición.")
        self.image_text = tk.StringVar(value="No hay ningún plano cargado.")
        self.status_text = tk.StringVar(value="Selecciona la planta y carga su plano.")
        self.coverage_router_vars = {}
        self.coverage_router_menu_text = tk.StringVar(value="Routers visibles")
        self.coverage_text = tk.StringVar(value="")

        self.build_controls()
        self.floor_var.trace_add("write", self.on_floor_change)
        self.root.after(1000, self.check_capture_process)
        self.load_default_plan()

    def build_controls(self):
        controls = ttk.Frame(self.root, padding=10)
        self.controls_frame = controls
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Edificio").grid(row=0, column=0, sticky=tk.W, padx=(0, 4))
        ttk.Entry(controls, textvariable=self.building_var, width=12).grid(
            row=0, column=1, sticky=tk.W, padx=(0, 12)
        )
        ttk.Label(controls, text="Planta").grid(row=0, column=2, sticky=tk.W, padx=(0, 4))
        ttk.Combobox(
            controls,
            textvariable=self.floor_var,
            values=FLOORS,
            state="readonly",
            width=7,
        ).grid(row=0, column=3, sticky=tk.W, padx=(0, 8))
        ttk.Button(controls, text="Cargar plano...", command=self.choose_plan).grid(
            row=0, column=4, sticky=tk.W
        )
        ttk.Label(controls, textvariable=self.image_text).grid(
            row=0, column=5, sticky=tk.W, padx=8
        )

        ttk.Label(controls, text="Punto").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.point_var, width=12).grid(
            row=1, column=1, sticky=tk.W, pady=(8, 0), padx=(0, 12)
        )
        ttk.Label(controls, text="Orientación").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.orientation_var, width=13).grid(
            row=1, column=3, sticky=tk.W, pady=(8, 0), padx=(0, 8)
        )
        ttk.Label(controls, text="Intervalo (s)").grid(row=1, column=4, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.interval_var, width=6).grid(
            row=1, column=5, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(controls, text="Capturas").grid(row=1, column=6, sticky=tk.W, pady=(8, 0), padx=(8, 4))
        ttk.Entry(controls, textvariable=self.samples_var, width=6).grid(
            row=1, column=7, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(controls, text="Procedimiento").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.procedure_var, width=55).grid(
            row=2, column=1, columnspan=4, sticky=tk.EW, pady=(8, 0), padx=(0, 8)
        )
        ttk.Checkbutton(
            controls,
            text="Escanear todas las redes visibles (mínimo 5 s)",
            variable=self.all_networks_var,
            command=self.update_interval_hint,
        ).grid(row=2, column=5, columnspan=3, sticky=tk.W, pady=(8, 0))

        controls.columnconfigure(4, weight=0)
        controls.columnconfigure(5, weight=1)

        map_frame = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        self.map_frame = map_frame
        map_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(map_frame, background="#333333", highlightthickness=0)
        horizontal = ttk.Scrollbar(map_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vertical = ttk.Scrollbar(map_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        horizontal.grid(row=1, column=0, sticky=tk.EW)
        map_frame.rowconfigure(0, weight=1)
        map_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.select_position)

        self.coverage_frame = ttk.LabelFrame(
            self.root,
            text="Mapa de rangos estimados",
            padding=(8, 5),
        )
        coverage_controls = ttk.Frame(self.coverage_frame)
        coverage_controls.pack(fill=tk.X)
        ttk.Label(coverage_controls, text="Mostrar:").pack(side=tk.LEFT)
        self.coverage_router_menu = ttk.Button(
            coverage_controls,
            textvariable=self.coverage_router_menu_text,
            command=self.open_coverage_router_selector,
        )
        self.coverage_router_menu.pack(side=tk.LEFT, padx=(5, 12))
        ttk.Label(coverage_controls, textvariable=self.coverage_text).pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )
        coverage_legend = ttk.Frame(self.coverage_frame)
        coverage_legend.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(coverage_legend, text="■").pack(side=tk.LEFT)
        for label, color in (
            ("Límite observado", "#e03131"),
            ("Radio 40%", "#ffd43b"),
            ("Radio 70%", "#2f9e44"),
        ):
            tk.Label(
                coverage_legend,
                width=2,
                background=color,
                relief=tk.SOLID,
                borderwidth=1,
            ).pack(side=tk.LEFT, padx=(3, 2))
            ttk.Label(coverage_legend, text=label).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(
            coverage_legend,
            text="En vista individual se rellenan las zonas <40%, 40-69% y ≥70%.",
        ).pack(side=tk.LEFT, padx=(4, 0))

        measurements_frame = ttk.LabelFrame(
            self.root,
            text="Mediciones del punto seleccionado",
            padding=(8, 5),
        )
        self.measurements_frame = measurements_frame
        measurements_frame.pack(fill=tk.X, padx=10, pady=(8, 0))
        measurements_header = ttk.Frame(measurements_frame)
        measurements_header.pack(fill=tk.X)
        self.measurements_summary = tk.StringVar(
            value="Haz clic en uno de los marcadores del mapa para consultar sus datos."
        )
        ttk.Label(measurements_header, textvariable=self.measurements_summary).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(
            measurements_header,
            text="Medir de nuevo aquí",
            command=self.start_capture,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(
            measurements_header,
            text="Recargar datos",
            command=self.refresh_measurements,
        ).pack(side=tk.RIGHT)

        self.coverage_summary = tk.StringVar(value="")
        ttk.Label(
            measurements_frame,
            textvariable=self.coverage_summary,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))
        coverage_legend = ttk.Frame(measurements_frame)
        coverage_legend.pack(anchor=tk.W)
        ttk.Label(
            coverage_legend,
            text="◆ Punto medido",
            foreground="#1971c2",
        ).pack(side=tk.LEFT)
        ttk.Label(
            coverage_legend,
            text="● Router",
            foreground="#495057",
        ).pack(side=tk.LEFT, padx=(10, 14))
        ttk.Label(coverage_legend, text="Señal recibida:").pack(side=tk.LEFT)
        for label, color in (
            ("0-24%", "#e03131"),
            ("25-49%", "#fd7e14"),
            ("50-74%", "#ffd43b"),
            ("75-100%", "#2f9e44"),
            ("Sin dato", "#868e96"),
        ):
            tk.Label(
                coverage_legend,
                width=2,
                background=color,
                relief=tk.SOLID,
                borderwidth=1,
            ).pack(side=tk.LEFT, padx=(8, 2))
            ttk.Label(coverage_legend, text=label).pack(side=tk.LEFT)

        router_frame = ttk.Frame(measurements_frame)
        router_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(
            router_frame,
            text="Routers eduroam: señal media del BSSID mejor recibido en este punto",
        ).pack(anchor=tk.W)
        router_columns = ("router", "bssid", "signal", "observations")
        self.router_table = ttk.Treeview(
            router_frame,
            columns=router_columns,
            show="headings",
            height=4,
        )
        for column, title, width in (
            ("router", "Router / ubicación", 245),
            ("bssid", "BSSID eduroam", 165),
            ("signal", "Señal media (%)", 110),
            ("observations", "Muestras", 75),
        ):
            self.router_table.heading(column, text=title)
            self.router_table.column(column, width=width, minwidth=65, stretch=True)
        for tag, color in (
            ("low", "#ffc9c9"),
            ("medium_low", "#ffe8cc"),
            ("medium_high", "#fff3bf"),
            ("high", "#d3f9d8"),
            ("missing", "#e9ecef"),
        ):
            self.router_table.tag_configure(tag, background=color)
        router_scrollbar = ttk.Scrollbar(
            router_frame,
            orient=tk.VERTICAL,
            command=self.router_table.yview,
        )
        self.router_table.configure(yscrollcommand=router_scrollbar.set)
        self.router_table.pack(side=tk.LEFT, fill=tk.X, expand=True)
        router_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        table_frame = ttk.Frame(measurements_frame)
        table_frame.pack(fill=tk.X, pady=(5, 0))
        columns = (
            "bssid", "ssid", "detections", "connected", "signal",
            "rssi", "rx", "tx", "band", "channel",
        )
        self.measurements_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=5,
        )
        headings = {
            "bssid": ("BSSID / MAC", 135),
            "ssid": ("SSID", 145),
            "detections": ("Detecciones", 85),
            "connected": ("Con conexión", 90),
            "signal": ("Señal media (%)", 105),
            "rssi": ("RSSI medio (dBm)", 110),
            "rx": ("Rx medio (Mbps)", 105),
            "tx": ("Tx medio (Mbps)", 105),
            "band": ("Banda", 75),
            "channel": ("Canal", 65),
        }
        for column in columns:
            title, width = headings[column]
            self.measurements_table.heading(column, text=title)
            self.measurements_table.column(column, width=width, minwidth=55, stretch=True)
        table_scrollbar = ttk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=self.measurements_table.yview,
        )
        self.measurements_table.configure(yscrollcommand=table_scrollbar.set)
        self.measurements_table.pack(side=tk.LEFT, fill=tk.X, expand=True)
        table_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        footer = ttk.Frame(self.root, padding=10)
        self.footer_frame = footer
        footer.pack(fill=tk.X)
        self.position_label = ttk.Label(footer, textvariable=self.position_text)
        self.position_label.pack(anchor=tk.W)
        actions = ttk.Frame(footer)
        self.actions_frame = actions
        actions.pack(fill=tk.X, pady=(6, 0))
        self.capture_button = ttk.Button(
            actions,
            text="Iniciar capturas en posición seleccionada",
            command=self.start_capture,
        )
        self.capture_button.pack(side=tk.LEFT)
        self.coverage_button = ttk.Button(
            actions,
            text="Ver rangos de cobertura",
            command=self.toggle_coverage_mode,
        )
        self.coverage_button.pack(side=tk.LEFT, padx=(6, 0))
        self.status_label = ttk.Label(actions, textvariable=self.status_text)
        self.status_label.pack(side=tk.LEFT, padx=12)

    def toggle_coverage_mode(self):
        self.coverage_mode = not self.coverage_mode
        if self.coverage_mode:
            self.coverage_button.configure(text="Volver a las mediciones")
            self.canvas.delete("measurement")
            self.canvas.delete("selection")
            self.canvas.delete("coverage")
            self.controls_frame.pack_forget()
            self.measurements_frame.pack_forget()
            self.position_label.pack_forget()
            self.capture_button.pack_forget()
            self.coverage_frame.pack(
                fill=tk.X,
                padx=10,
                pady=(8, 0),
                before=self.map_frame,
            )
            self.status_text.set(
                "Modo de rangos: selecciona un router en el menú o visualízalos todos."
            )
            self.draw_coverage_map()
            return

        self.coverage_button.configure(text="Ver rangos de cobertura")
        self.close_coverage_router_selector()
        self.coverage_frame.pack_forget()
        self.controls_frame.pack(fill=tk.X, before=self.map_frame)
        self.measurements_frame.pack(
            fill=tk.X,
            padx=10,
            pady=(8, 0),
            before=self.footer_frame,
        )
        self.position_label.pack(anchor=tk.W, before=self.actions_frame)
        self.capture_button.pack(side=tk.LEFT, before=self.coverage_button)
        self.refresh_measurements()

    def default_plan_path(self):
        building = self.building_var.get().strip()
        floor = self.floor_var.get().strip()
        if not building or floor not in FLOORS:
            return None
        candidates = [
            PROJECT_DIR / f"{building} - {floor}.png",
            PROJECT_DIR / f"{building}-{floor}.png",
        ]
        return next((path for path in candidates if path.is_file()), None)

    def on_floor_change(self, *_):
        self.selected_position = None
        self.displayed_point_position = None
        self.position_text.set("Haz clic en el plano para marcar la posición.")
        self.load_default_plan()

    def load_default_plan(self):
        path = self.default_plan_path()
        if path is None:
            self.clear_plan()
            return
        self.load_plan(path)

    def choose_plan(self):
        path = filedialog.askopenfilename(
            title="Selecciona el plano de la planta",
            initialdir=str(self.image_path.parent if self.image_path else PROJECT_DIR),
            filetypes=[("Imágenes PNG", "*.png")],
        )
        if path:
            self.load_plan(Path(path))

    def load_plan(self, path):
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError as error:
            messagebox.showerror("No se pudo cargar el plano", str(error))
            return
        self.plan_image = image
        self.image_path = path.resolve()
        self.image_size = (image.width(), image.height())
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=image, anchor=tk.NW, tags=("plan",))
        self.canvas.configure(scrollregion=(0, 0, *self.image_size))
        self.image_text.set(f"{path.name} ({image.width()} x {image.height()} px)")
        self.selected_position = None
        self.displayed_point_position = None
        self.position_text.set("Haz clic en el plano para marcar la posición.")
        self.status_text.set("Plano cargado; haz clic en tu posición.")
        self.refresh_measurements()

    def clear_plan(self):
        self.canvas.delete("all")
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.plan_image = None
        self.image_path = None
        self.image_size = None
        self.image_text.set("No se encontró el plano; pulsa «Cargar plano...»")
        self.measured_points = {}
        self.access_points = []
        self.coverage_models = []
        self.inventory_error = None
        self.coverage_text.set("Carga un plano para visualizar rangos.")
        self.canvas.delete("coverage")
        self.clear_measurements_table()
        self.clear_router_table()
        self.measurements_summary.set("Carga el plano para consultar sus mediciones.")
        self.coverage_summary.set("")

    def clear_measurements_table(self):
        for item in self.measurements_table.get_children():
            self.measurements_table.delete(item)

    def clear_router_table(self):
        for item in self.router_table.get_children():
            self.router_table.delete(item)

    def refresh_measurements(self):
        if self.plan_image is None:
            return
        plan_id = f"{self.building_var.get().strip()}-{self.floor_var.get().strip()}"
        try:
            self.measured_points = load_map_measurements(
                PROJECT_DIR / "data" / "practica2",
                plan_id,
            )
        except (OSError, ValueError) as error:
            self.status_text.set(f"No se pudieron leer las mediciones: {error}")
            messagebox.showerror("Error al leer las mediciones", str(error))
            return

        self.access_points = []
        self.inventory_error = None
        inventory_files = list(PROJECT_DIR.glob("ap_list_up_*.csv"))
        if not inventory_files:
            self.inventory_error = "No se encontró el inventario ap_list_up_*.csv."
        else:
            try:
                inventory_path = max(
                    inventory_files,
                    key=lambda path: path.stat().st_mtime,
                )
                self.access_points = load_access_point_inventory(
                    inventory_path,
                    plan_id,
                )
            except (OSError, ValueError) as error:
                self.inventory_error = f"No se pudo leer el inventario de AP: {error}"
        self.coverage_models = build_router_coverage_models(
            self.measured_points,
            self.access_points,
        )

        self.canvas.delete("measurement")
        self.canvas.delete("coverage")
        self.clear_router_table()
        self.coverage_summary.set("")
        if not self.coverage_mode:
            self.draw_measurement_markers()
        if self.measured_points:
            self.status_text.set(
                f"{len(self.measured_points)} punto(s) medido(s) en {plan_id}. "
                "Haz clic en un marcador para ver sus redes."
            )
            if (
                not self.coverage_mode
                and self.displayed_point_position in self.measured_points
            ):
                self.show_measurements(
                    self.displayed_point_position,
                    self.measured_points[self.displayed_point_position],
                )
        else:
            self.displayed_point_position = None
            self.measurements_summary.set(
                f"No hay mediciones guardadas para {plan_id}. Las nuevas capturas aparecerán aquí."
            )
            self.status_text.set(
                f"No hay puntos medidos en {plan_id}; selecciona un punto para iniciar una captura."
            )
        if self.coverage_mode:
            self.draw_coverage_map()

    def draw_measurement_markers(self):
        self.canvas.delete("measurement")
        for (x, y), point in self.measured_points.items():
            marker_tag = f"point_{x}_{y}"
            self.canvas.create_polygon(
                x,
                y - 11,
                x + 11,
                y,
                x,
                y + 11,
                x - 11,
                y,
                fill="#1971c2",
                outline="#ffffff",
                width=2,
                tags=("measurement", marker_tag),
            )
            self.canvas.create_text(
                x + 14,
                y - 10,
                text=str(point["capture_count"]),
                fill="#ffffff",
                font=("Segoe UI", 9, "bold"),
                tags=("measurement", marker_tag),
            )

    def draw_coverage_map(self, _event=None):
        self.canvas.delete("coverage")
        self.coverage_fill_images = []
        if not self.coverage_mode or self.plan_image is None:
            return

        supported_models = [
            model for model in self.coverage_models
            if model["supported"]
        ]
        self.update_coverage_router_menu(supported_models)

        if self.inventory_error:
            self.coverage_text.set(self.inventory_error)
            return
        if not supported_models:
            self.coverage_text.set(
                "No hay datos suficientes: se requieren medidas en dos distancias "
                "distintas y una tendencia de señal decreciente."
            )
            return

        models_to_draw = [
            model for model in supported_models
            if self.coverage_router_vars[model["name"]].get()
        ]
        if not models_to_draw:
            self.coverage_text.set(
                "No hay routers seleccionados. Pulsa «Elegir routers» para marcar los que quieras ver."
            )
            return
        single_router_selected = len(models_to_draw) == 1

        for model in models_to_draw:
            x, y = model["x"], model["y"]
            if x is None or y is None:
                continue

            radius_70 = model["radius_70"]
            radius_40 = model["radius_40"]
            max_radius = model["max_radius"]
            if not single_router_selected:
                for radius, color, dash in (
                    (max_radius, "#e03131", (5, 3)),
                    (radius_40, "#d4a000", ()),
                    (radius_70, "#2f9e44", ()),
                ):
                    if radius > 0:
                        self.canvas.create_oval(
                            x - radius,
                            y - radius,
                            x + radius,
                            y + radius,
                            fill="",
                            outline=color,
                            width=2,
                            dash=dash,
                            tags=("coverage",),
                        )
            else:
                if max_radius > 0:
                    overlay = tk.PhotoImage(
                        master=self.canvas,
                        data=_coverage_overlay_png(
                            radius_70,
                            radius_40,
                            max_radius,
                        ),
                    )
                    self.coverage_fill_images.append(overlay)
                    self.canvas.create_image(
                        x - (overlay.width() - 1) / 2,
                        y - (overlay.height() - 1) / 2,
                        image=overlay,
                        anchor=tk.NW,
                        tags=("coverage",),
                    )
                for radius, color in (
                    (max_radius, "#e03131"),
                    (radius_40, "#d4a000"),
                    (radius_70, "#2f9e44"),
                ):
                    if radius > 0:
                        self.canvas.create_oval(
                            x - radius,
                            y - radius,
                            x + radius,
                            y + radius,
                            fill="",
                            outline=color,
                            width=1,
                            tags=("coverage",),
                        )

        selected_names = {model["name"] for model in models_to_draw}
        for model in self.access_points:
            if model["name"] not in selected_names:
                continue
            x, y = model["x"], model["y"]
            if x is None or y is None:
                continue
            self.canvas.create_oval(
                x - 8,
                y - 8,
                x + 8,
                y + 8,
                fill="#ffffff",
                outline="#212529",
                width=2,
                tags=("coverage",),
            )
            self.canvas.create_text(
                x + 12,
                y - 9,
                text=model["name"].rsplit("-", 1)[-1],
                fill="#212529",
                anchor=tk.W,
                font=("Segoe UI", 8, "bold"),
                tags=("coverage",),
            )

        unsupported_count = len(self.coverage_models) - len(supported_models)
        if single_router_selected:
            selected_model = models_to_draw[0]
            radius_70 = selected_model["radius_70"]
            radius_40 = selected_model["radius_40"]
            max_radius = selected_model["max_radius"]
            self.coverage_text.set(
                f"{selected_model['name']}: radio estimado ≥70% "
                f"{radius_70:.0f} px; ≥40% {radius_40:.0f} px; "
                f"máximo muestreado {max_radius:.0f} px (ajuste lineal)."
            )
        else:
            self.coverage_text.set(
                f"Mostrando {len(models_to_draw)} routers seleccionados; "
                f"{unsupported_count} sin tendencia suficiente. Los contornos "
                "marcan los radios de 70%, 40% y la muestra más lejana."
            )

    def update_coverage_router_menu(self, supported_models):
        model_names = [model["name"] for model in supported_models]
        if list(self.coverage_router_vars) == model_names:
            self.update_coverage_router_menu_text()
            return

        previous_names = {
            name for name, variable in self.coverage_router_vars.items()
            if variable.get()
        }
        initial_load = not self.coverage_router_vars
        self.coverage_router_vars = {}
        for name in model_names:
            self.coverage_router_vars[name] = tk.BooleanVar(
                value=initial_load or name in previous_names
            )
        self.update_coverage_router_menu_text()
        if (
            self.coverage_router_selector is not None
            and self.coverage_router_selector.winfo_exists()
        ):
            self.build_coverage_router_selector_contents()

    def update_coverage_router_menu_text(self):
        selected_count = sum(
            variable.get() for variable in self.coverage_router_vars.values()
        )
        total_count = len(self.coverage_router_vars)
        self.coverage_router_menu_text.set(
            f"Elegir routers ({selected_count}/{total_count})"
        )

    def open_coverage_router_selector(self):
        if (
            self.coverage_router_selector is not None
            and self.coverage_router_selector.winfo_exists()
        ):
            self.coverage_router_selector.lift()
            self.coverage_router_selector.focus_set()
            return

        selector = tk.Toplevel(self.root)
        selector.title("Routers visibles")
        selector.transient(self.root)
        selector.resizable(False, False)
        self.coverage_router_selector = selector
        selector.protocol("WM_DELETE_WINDOW", self.close_coverage_router_selector)
        selector.update_idletasks()
        x = self.coverage_router_menu.winfo_rootx()
        y = self.coverage_router_menu.winfo_rooty() + self.coverage_router_menu.winfo_height()
        selector.geometry(f"+{x}+{y}")
        self.build_coverage_router_selector_contents()

    def build_coverage_router_selector_contents(self):
        selector = self.coverage_router_selector
        if selector is None or not selector.winfo_exists():
            return
        for child in selector.winfo_children():
            child.destroy()
        self.coverage_router_selector_checks = {}

        content = ttk.Frame(selector, padding=10)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Marca los routers que quieres mostrar:",
        ).pack(anchor=tk.W, pady=(0, 6))
        actions = ttk.Frame(content)
        actions.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(
            actions,
            text="Seleccionar todos",
            command=lambda: self.set_coverage_router_selection(
                set(self.coverage_router_vars)
            ),
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Quitar selección",
            command=lambda: self.set_coverage_router_selection(set()),
        ).pack(side=tk.LEFT, padx=(6, 0))

        if not self.coverage_router_vars:
            ttk.Label(
                content,
                text="No hay routers con datos suficientes.",
            ).pack(anchor=tk.W, pady=4)
            return

        for name, variable in self.coverage_router_vars.items():
            checkbutton = ttk.Checkbutton(
                content,
                text=name,
                variable=variable,
                command=self.draw_coverage_map,
            )
            checkbutton.pack(anchor=tk.W, pady=2)
            self.coverage_router_selector_checks[name] = checkbutton

        ttk.Button(
            content,
            text="Cerrar",
            command=self.close_coverage_router_selector,
        ).pack(anchor=tk.E, pady=(8, 0))

    def close_coverage_router_selector(self):
        if (
            self.coverage_router_selector is not None
            and self.coverage_router_selector.winfo_exists()
        ):
            self.coverage_router_selector.destroy()
        self.coverage_router_selector = None

    def set_coverage_router_selection(self, names):
        for name, variable in self.coverage_router_vars.items():
            variable.set(name in names)
        self.update_coverage_router_menu_text()
        self.draw_coverage_map()

    def select_measured_point(self, position):
        point = self.measured_points.get(position)
        if point is not None:
            x, y = position
            self.selected_position = position
            self.displayed_point_position = position
            self.draw_selection_marker(position)
            self.show_measurements(position, point)
            return True
        return False

    def show_measurements(self, position, point):
        self.clear_measurements_table()
        x, y = position
        self.selected_position = position
        self.displayed_point_position = position
        if point["point_ids"]:
            self.point_var.set(point["point_ids"][-1])
        self.position_text.set(f"Posición seleccionada: x={x}, y={y} px")
        self.measurements_summary.set(
            f"Punto ({x}, {y}) px · {point['capture_count']} capturas · "
            f"{point['sessions']} sesión(es) · "
            f"{point['scan_errors']} error(es) de escaneo"
        )
        self.show_router_coverage(point)
        self.canvas.tag_raise("measurement")
        self.draw_selection_marker(position)
        for network in point["networks"]:
            values = (
                network["bssid"],
                network["ssid"],
                network["detections"],
                network["connected_captures"],
                _format_measurement(network["mean_signal_percent"], "%"),
                _format_measurement(network["mean_rssi_dbm"], "dBm"),
                _format_measurement(network["mean_rx_rate_mbps"], "Mbps"),
                _format_measurement(network["mean_tx_rate_mbps"], "Mbps"),
                network["bands"],
                network["channels"],
            )
            self.measurements_table.insert("", tk.END, values=values)
        self.status_text.set(
            "Las tasas Rx/Tx solo se muestran para el BSSID conectado; "
            "Windows no proporciona esas tasas para los AP vecinos."
        )

    @staticmethod
    def coverage_color(value):
        if value is None:
            return "#868e96"
        if value < 25:
            return "#e03131"
        if value < 50:
            return "#fd7e14"
        if value < 75:
            return "#ffd43b"
        return "#2f9e44"

    def show_router_coverage(self, point):
        self.canvas.delete("coverage")
        self.clear_router_table()
        if self.inventory_error:
            self.coverage_summary.set(self.inventory_error)
            return
        if not self.access_points:
            self.coverage_summary.set("El inventario no contiene routers para esta planta.")
            return

        summaries = summarize_router_eduroam_signal(point, self.access_points)
        detected_count = 0
        for router in summaries:
            value = router["mean_signal_percent"]
            color = self.coverage_color(value)
            if router["detected"]:
                detected_count += 1
            if value is None:
                signal_text = "Sin medida" if router["detected"] else "No detectado"
                bssid_text = "—"
                tag = "missing"
            else:
                signal_text = f"{value:.1f}%"
                bssid_text = router["bssid"]
                tag = self.coverage_tag(value)
            self.router_table.insert(
                "",
                tk.END,
                values=(
                    router["name"],
                    bssid_text,
                    signal_text,
                    router["signal_observation_count"],
                ),
                tags=(tag,),
            )

            if router["x"] is not None and router["y"] is not None:
                x, y = router["x"], router["y"]
                self.canvas.create_oval(
                    x - 8,
                    y - 8,
                    x + 8,
                    y + 8,
                    fill=color,
                    outline="#202020",
                    width=2,
                    tags=("coverage",),
                )
                short_name = router["name"].rsplit("-", 1)[-1]
                label = "—" if value is None else f"{value:.0f}%"
                self.canvas.create_text(
                    x + 12,
                    y - 10,
                    text=f"{short_name} {label}",
                    fill="#ffffff",
                    font=("Segoe UI", 8, "bold"),
                    tags=("coverage",),
                )

        self.coverage_summary.set(
            f"Señal observada directamente en este punto: {detected_count} de "
            f"{len(summaries)} routers detectados. «No detectado» significa que "
            "no aparece en las capturas; no se sustituye por una estimación. "
            "Se muestra la media del BSSID de eduroam mejor recibido de cada router."
        )

    @staticmethod
    def coverage_tag(value):
        if value is None:
            return "missing"
        if value < 25:
            return "low"
        if value < 50:
            return "medium_low"
        if value < 75:
            return "medium_high"
        return "high"

    def select_position(self, event):
        if self.plan_image is None or self.coverage_mode:
            return
        click_x = round(self.canvas.canvasx(event.x))
        click_y = round(self.canvas.canvasy(event.y))
        width, height = self.image_size
        if not (0 <= click_x < width and 0 <= click_y < height):
            return
        nearest_point = min(
            self.measured_points,
            key=lambda position: math.hypot(position[0] - click_x, position[1] - click_y),
            default=None,
        )
        if (
            nearest_point is not None
            and math.hypot(nearest_point[0] - click_x, nearest_point[1] - click_y) <= 24
        ):
            self.select_measured_point(nearest_point)
            return

        x, y = click_x, click_y
        self.selected_position = (x, y)
        self.displayed_point_position = None
        self.point_var.set(f"{self.floor_var.get()}-{x}-{y}")
        self.draw_selection_marker((x, y))
        self.position_text.set(f"Posición seleccionada: x={x}, y={y} px")
        self.clear_measurements_table()
        self.clear_router_table()
        self.coverage_summary.set("")
        self.canvas.delete("coverage")
        self.measurements_summary.set(
            "Punto sin mediciones. Usa «Iniciar capturas en posición seleccionada» para medir aquí."
        )
        self.status_text.set("Punto nuevo seleccionado; puedes iniciar las capturas.")

    def draw_selection_marker(self, position):
        x, y = position
        self.canvas.delete("selection")
        radius = 8
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            outline="#ff2020",
            width=3,
            tags=("selection",),
        )
        self.canvas.create_line(
            x - radius - 4, y, x + radius + 4, y,
            fill="#ff2020", width=2, tags=("selection",),
        )
        self.canvas.create_line(
            x, y - radius - 4, x, y + radius + 4,
            fill="#ff2020", width=2, tags=("selection",),
        )

    def update_interval_hint(self):
        if self.all_networks_var.get():
            try:
                interval = int(self.interval_var.get())
            except ValueError:
                interval = 0
            if interval < 5:
                self.interval_var.set("5")

    def start_capture(self):
        if self.plan_image is None or self.selected_position is None:
            messagebox.showwarning("Falta seleccionar la posición", "Carga un plano y haz clic en tu posición.")
            return
        if self.capture_process is not None and self.capture_process.poll() is None:
            messagebox.showwarning("Captura en curso", "Ya hay una captura ejecutándose en su ventana de terminal.")
            return

        building = self.building_var.get().strip()
        floor = self.floor_var.get().strip()
        point_id = self.point_var.get().strip()
        if not building or floor not in FLOORS or not point_id:
            messagebox.showerror("Datos incompletos", "Indica el edificio, la planta y el identificador del punto.")
            return
        try:
            interval = int(self.interval_var.get())
            samples = int(self.samples_var.get())
        except ValueError:
            messagebox.showerror("Datos no válidos", "El intervalo y el número de capturas deben ser enteros.")
            return
        if interval < (5 if self.all_networks_var.get() else 1) or samples < 1:
            messagebox.showerror(
                "Datos no válidos",
                "El intervalo debe ser positivo (mínimo 5 s al escanear todas las redes) y las capturas deben ser al menos 1.",
            )
            return

        x, y = self.selected_position
        self.capture_position = self.selected_position
        self.displayed_point_position = self.selected_position
        plan_id = f"{building}-{floor}"
        command = [
            sys.executable,
            str(PROJECT_DIR / "wifi_scanner.py"),
            "--room", point_id,
            "--point-id", point_id,
            "--orientation", self.orientation_var.get().strip() or "sin especificar",
            "--interval", str(interval),
            "--samples", str(samples),
            "--dataset", "practica2",
            "--building", building,
            "--floor", floor,
            "--plan-id", plan_id,
            "--map-file", str(self.image_path),
            "--coordinate-system", "image_pixels_top_left",
            "--units", "px",
            "--origin", "top_left",
            "--x-axis", "right",
            "--y-axis", "down",
            "--x", str(x),
            "--y", str(y),
        ]
        procedure = self.procedure_var.get().strip()
        if procedure:
            command.extend(["--procedure", procedure])
        if self.all_networks_var.get():
            command.append("--all")

        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
        try:
            self.capture_process = subprocess.Popen(
                command,
                cwd=str(PROJECT_DIR),
                creationflags=creationflags,
            )
        except OSError as error:
            self.capture_position = None
            messagebox.showerror("No se pudo iniciar la captura", str(error))
            return
        self.status_text.set(
            f"Captura iniciada para {point_id} en {floor}, coordenadas ({x}, {y}) px."
        )

    def check_capture_process(self):
        if self.capture_process is not None:
            return_code = self.capture_process.poll()
            if return_code is not None:
                self.capture_process = None
                self.refresh_measurements()
                if (
                    self.capture_position is not None
                    and self.capture_position not in self.measured_points
                    and self.selected_position == self.capture_position
                ):
                    self.canvas.delete("selection")
                    self.selected_position = None
                    self.displayed_point_position = None
                    self.position_text.set("No se guardaron capturas en la posición cancelada.")
                    self.measurements_summary.set(
                        "La adquisición terminó sin guardar medidas en este punto."
                    )
                self.capture_position = None
                self.status_text.set(f"Captura finalizada (código {return_code}).")
        self.root.after(1000, self.check_capture_process)

def main():
    root = tk.Tk()
    SurveyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
