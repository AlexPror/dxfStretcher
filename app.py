import logging
import sys
import re
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import json

import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.flat_pattern_service import FlatPatternService, StretchResult
from core.base_analyzer import BaseAnalyzer, BaseInfo, RadiusFileInfo


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


class FlatPatternApp(ctk.CTk):
    """GUI приложения с пакетной обработкой и генерацией отчётов"""

    def __init__(self):
        super().__init__()
        self.title("DXF Stretcher v3.0")
        self.geometry("920x680")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.service = FlatPatternService()
        self.base_analyzer = BaseAnalyzer()
        
        # Переменные для одиночной обработки
        self.file_var = ctk.StringVar()
        self.target_var = ctk.StringVar(value="0")
        self.status_var = ctk.StringVar(value="Выберите файл и нажмите «Измерить».")
        self.axis_var = ctk.StringVar(value="X")
        self.anchor_var = ctk.StringVar(value="start")
        self.info_text: Optional[ctk.CTkLabel] = None
        self.last_result: Optional[StretchResult] = None
        
        # Переменные для пакетной обработки
        self.batch_folder_var = ctk.StringVar()
        self.batch_axis_var = ctk.StringVar(value="X")
        self.batch_anchor_var = ctk.StringVar(value="start")
        self.batch_results: List[StretchResult] = []
        self.batch_log_text = None
        self.batch_bases_analyzed = False

        # Шрифты (ГОСТ, при отсутствии — Arial)
        self.font_family = "GOST type A"
        try:
            self.font_regular = ctk.CTkFont(family=self.font_family, size=13)
        except Exception:
            self.font_family = "Arial"
            self.font_regular = ctk.CTkFont(family=self.font_family, size=13)
        self.font_small = ctk.CTkFont(family=self.font_family, size=11)
        self.font_title = ctk.CTkFont(family=self.font_family, size=16, weight="bold")

        self._build_layout()

    # ------------------------------------------------------------------ #
    def _build_layout(self):
        """Создаёт вкладки для одиночной и пакетной обработки"""
        
        # Табы
        self.tabview = ctk.CTkTabview(self, width=880, height=640)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_single = self.tabview.add("Одиночная обработка")
        self.tab_batch = self.tabview.add("Пакетная обработка")
        
        self._build_single_tab()
        self._build_batch_tab()

    # ------------------------------------------------------------------ #
    # ВКЛАДКА: Одиночная обработка
    # ------------------------------------------------------------------ #
    def _build_single_tab(self):
        padding = {"padx": 20, "pady": 10}

        # Файл
        file_frame = ctk.CTkFrame(self.tab_single)
        file_frame.pack(fill="x", **padding)

        ctk.CTkLabel(file_frame, text="Файл развертки / модели:", font=self.font_regular).pack(anchor="w")
        entry_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        entry_frame.pack(fill="x", pady=(6, 0))

        file_entry = ctk.CTkEntry(entry_frame, textvariable=self.file_var, font=self.font_regular)
        file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(entry_frame, text="Обзор", width=120, command=self._select_file,
                      font=self.font_regular).pack(side="right")

        # Параметры растяжения
        params_frame = ctk.CTkFrame(self.tab_single)
        params_frame.pack(fill="x", **padding)

        # Направление
        axis_label = ctk.CTkLabel(params_frame, text="Направление:", font=self.font_regular)
        axis_label.grid(row=0, column=0, sticky="w", padx=5, pady=(10, 4))
        axis_menu = ctk.CTkOptionMenu(params_frame, values=["X", "Y"], variable=self.axis_var,
                                      font=self.font_regular,
                                      command=lambda _: self._on_axis_change())
        axis_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=(10, 4))

        # Центр масштабирования
        anchor_label = ctk.CTkLabel(params_frame, text="Центр масштабирования:", font=self.font_regular)
        anchor_label.grid(row=1, column=0, sticky="w", padx=5, pady=(0, 4))
        self.anchor_menu = ctk.CTkOptionMenu(params_frame, values=[], font=self.font_regular,
                                             command=lambda _: None)
        self.anchor_menu.grid(row=1, column=1, sticky="ew", padx=5, pady=(0, 4))

        # Целевая длина
        ctk.CTkLabel(params_frame, text="Целевая длина, мм:", font=self.font_regular)\
            .grid(row=2, column=0, sticky="w", padx=5, pady=(10, 4))
        ctk.CTkEntry(params_frame, textvariable=self.target_var, font=self.font_regular)\
            .grid(row=2, column=1, sticky="ew", padx=5, pady=(10, 4))
        params_frame.grid_columnconfigure(1, weight=1)
        self._update_anchor_menu()

        # Кнопки
        buttons_frame = ctk.CTkFrame(self.tab_single)
        buttons_frame.pack(fill="x", **padding)

        ctk.CTkButton(buttons_frame, text="Измерить", command=self._measure,
                      font=self.font_regular).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons_frame, text="Изменить длину", command=self._stretch,
                      font=self.font_regular, fg_color="#2B7A0B").pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons_frame, text="Сохранить DXF", command=self._save,
                      font=self.font_regular).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons_frame, text="Очистить", fg_color="gray30", command=self._clear,
                      font=self.font_regular).pack(side="left", expand=True, padx=5)

        # Информация
        info_frame = ctk.CTkFrame(self.tab_single)
        info_frame.pack(fill="both", expand=True, **padding)

        ctk.CTkLabel(info_frame, text="Сводка:", font=self.font_title).pack(anchor="w")
        self.info_text = ctk.CTkLabel(info_frame, text="–", justify="left", font=self.font_regular)
        self.info_text.pack(fill="both", expand=True, pady=(10, 0))

        ctk.CTkLabel(self.tab_single, textvariable=self.status_var, text_color="#6ddf8c",
                     font=self.font_small).pack(fill="x", padx=20, pady=(0, 20))

    # ------------------------------------------------------------------ #
    # ВКЛАДКА: Пакетная обработка
    # ------------------------------------------------------------------ #
    def _build_batch_tab(self):
        padding = {"padx": 20, "pady": 10}

        # Папка
        folder_frame = ctk.CTkFrame(self.tab_batch)
        folder_frame.pack(fill="x", **padding)

        ctk.CTkLabel(folder_frame, text="Папка с DXF файлами:", font=self.font_regular).pack(anchor="w")
        entry_frame = ctk.CTkFrame(folder_frame, fg_color="transparent")
        entry_frame.pack(fill="x", pady=(6, 0))

        folder_entry = ctk.CTkEntry(entry_frame, textvariable=self.batch_folder_var, font=self.font_regular)
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(entry_frame, text="Обзор", width=120, command=self._select_batch_folder,
                      font=self.font_regular).pack(side="right")

        # Параметры
        params_frame = ctk.CTkFrame(self.tab_batch)
        params_frame.pack(fill="x", **padding)

        # Направление
        ctk.CTkLabel(params_frame, text="Направление растяжения:", font=self.font_regular)\
            .grid(row=0, column=0, sticky="w", padx=5, pady=(10, 4))
        ctk.CTkOptionMenu(params_frame, values=["X", "Y"], variable=self.batch_axis_var,
                         font=self.font_regular).grid(row=0, column=1, sticky="ew", padx=5, pady=(10, 4))

        # Центр масштабирования
        ctk.CTkLabel(params_frame, text="Центр масштабирования:", font=self.font_regular)\
            .grid(row=1, column=0, sticky="w", padx=5, pady=(0, 4))
        ctk.CTkOptionMenu(params_frame, values=["Левый край", "Центр", "Правый край"], 
                         variable=self.batch_anchor_var,
                         font=self.font_regular).grid(row=1, column=1, sticky="ew", padx=5, pady=(0, 4))
        
        params_frame.grid_columnconfigure(1, weight=1)
        
        # Информационный блок
        info_label = ctk.CTkLabel(
            self.tab_batch, 
            text="ℹ️ Целевые длины определяются автоматически из файлов оснований",
            font=self.font_small,
            text_color="#6ddf8c"
        )
        info_label.pack(fill="x", padx=20, pady=(0, 10))

        # Кнопки (первая строка)
        buttons_frame = ctk.CTkFrame(self.tab_batch)
        buttons_frame.pack(fill="x", **padding)

        ctk.CTkButton(buttons_frame, text="1. Анализировать основания", command=self._analyze_bases,
                      font=self.font_regular, fg_color="#1f538d", height=40).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons_frame, text="2. Запустить обработку", command=self._batch_process,
                      font=self.font_regular, fg_color="#2B7A0B", height=40).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons_frame, text="3. Создать отчёт", command=self._generate_report,
                      font=self.font_regular, height=40).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons_frame, text="Очистить", fg_color="gray30", command=self._batch_clear,
                      font=self.font_regular, height=40).pack(side="left", expand=True, padx=5)
        
        # Кнопки (вторая строка - проверка ширины)
        width_buttons_frame = ctk.CTkFrame(self.tab_batch)
        width_buttons_frame.pack(fill="x", **padding)
        
        ctk.CTkButton(width_buttons_frame, text="🔍 Проверить ширину разверток", 
                      command=self._check_widths,
                      font=self.font_regular, fg_color="#8B4513", height=40).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(width_buttons_frame, text="📏 Выровнять ширину", 
                      command=self._align_widths,
                      font=self.font_regular, fg_color="#8B6914", height=40).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(width_buttons_frame, text="🎯 Длина + Ширина (2в1)", 
                      command=self._batch_process_both_axes,
                      font=self.font_regular, fg_color="#9B59B6", height=40).pack(side="left", expand=True, padx=5)

        # Лог обработки
        log_frame = ctk.CTkFrame(self.tab_batch)
        log_frame.pack(fill="both", expand=True, **padding)

        ctk.CTkLabel(log_frame, text="Лог обработки:", font=self.font_title).pack(anchor="w")
        
        self.batch_log_text = ctk.CTkTextbox(log_frame, font=self.font_small, wrap="word")
        self.batch_log_text.pack(fill="both", expand=True, pady=(10, 0))

    # ------------------------------------------------------------------ #
    # Одиночная обработка
    # ------------------------------------------------------------------ #
    def _select_file(self):
        filetypes = [
            ("Kompas files", "*.dxf *.cdw *.m3d"),
            ("DXF files", "*.dxf"),
            ("Kompas drawings", "*.cdw"),
            ("Kompas parts", "*.m3d")
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.file_var.set(path)
            self.status_var.set("Файл выбран, нажмите «Измерить».")

    def _measure(self):
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Файл не выбран", "Сначала выберите файл.")
            return

        try:
            axis = self.axis_var.get()
            result = self.service.measure(path, axis=axis)
            self.last_result = result
            self.target_var.set(f"{result.current_length:.3f}")
            self.anchor_var.set("start")
            self._update_anchor_menu()
            self._show_info(result)
            self.status_var.set("Измерение выполнено. Введите желаемую длину и нажмите «Изменить длину».")
        except Exception as exc:
            logging.exception("Measure error")
            messagebox.showerror("Ошибка измерения", str(exc))
            self.status_var.set("Ошибка. Проверьте файл и повторите.")

    def _stretch(self):
        if not self.last_result:
            messagebox.showwarning("Нет данных", "Сначала выполните измерение.")
            return

        try:
            target = float(self.target_var.get().replace(",", "."))
            if target <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Неверное значение", "Введите положительное число для длины.")
            return

        try:
            axis = self.axis_var.get()
            anchor = self.anchor_var.get()
            result = self.service.stretch(target, axis=axis, anchor=anchor)
            self.last_result = result
            self._show_info(result)
            
            action = "растянута" if result.scale >= 1.0 else "укорочена"
            self.status_var.set(f"Развертка {action}. DXF: {result.stretched_dxf.name}")
        except Exception as exc:
            logging.exception("Stretch error")
            messagebox.showerror("Ошибка изменения длины", str(exc))
            self.status_var.set("Ошибка при изменении длины.")

    def _save(self):
        if not self.service.stretched_path:
            messagebox.showwarning("Нет результата", "Сначала выполните изменение длины.")
            return

        default_name = self.service.stretched_path.name
        path = filedialog.asksaveasfilename(defaultextension=".dxf", initialfile=default_name,
                                            filetypes=[("DXF files", "*.dxf")])
        if not path:
            return

        try:
            saved = self.service.save_stretched(path)
            self.status_var.set(f"DXF сохранён: {saved}")
            messagebox.showinfo("Сохранено", f"Файл сохранён:\n{saved}")
        except Exception as exc:
            logging.exception("Save error")
            messagebox.showerror("Ошибка сохранения", str(exc))

    def _clear(self):
        self.file_var.set("")
        self.target_var.set("0")
        self.axis_var.set("X")
        self.anchor_var.set("start")
        self._update_anchor_menu()
        self.status_var.set("Выберите файл и нажмите «Измерить».")
        self.info_text.configure(text="–")
        self.last_result = None
        self.service.clear()

    def _on_axis_change(self):
        """Изменение направления растяжения"""
        self.anchor_var.set("start")
        self._update_anchor_menu()
        length = self._current_length_for_axis()
        if length:
            self.target_var.set(f"{length:.3f}")

    def _update_anchor_menu(self):
        axis = self.axis_var.get().upper()
        if axis == "Y":
            options = [("Нижний край", "start"), ("Центр", "center"), ("Верхний край", "end")]
        else:
            options = [("Левый край", "start"), ("Центр", "center"), ("Правый край", "end")]

        display_values = [label for label, _ in options]
        internal_values = {label: value for label, value in options}

        self.anchor_menu.configure(values=display_values)
        current_label = display_values[0]
        for label, value in options:
            if value == self.anchor_var.get():
                current_label = label
                break
        self.anchor_menu.set(current_label)

        def on_select(choice: str):
            self.anchor_var.set(internal_values[choice])

        self.anchor_menu.configure(command=on_select)

    def _current_length_for_axis(self) -> Optional[float]:
        axis = self.axis_var.get().upper()
        if self.service.current_info:
            return self.service.current_info.length_x if axis == "X" else self.service.current_info.width_y
        if self.last_result:
            if axis == self.last_result.axis:
                return self.last_result.current_length
            if axis == "Y":
                return self.last_result.width
            return self.last_result.current_length
        return None

    def _show_info(self, result: StretchResult):
        anchor_names = {
            "start": "Край",
            "center": "Центр",
            "end": "Противоположный край"
        }
        anchor_display = anchor_names.get(result.anchor, result.anchor)
        
        action = "Удлинение" if result.scale >= 1.0 else "Укорочение"
        delta = result.target_length - result.current_length
        
        text = (
            f"Источник: {result.source_file.name}\n"
            f"DXF: {result.dxf_file.name}\n"
            f"Текущая длина: {result.current_length:.3f} мм\n"
            f"Ширина: {result.width:.3f} мм\n"
            f"Целевая длина: {result.target_length:.3f} мм\n"
            f"{action}: {delta:+.3f} мм ({(result.scale - 1) * 100:+.2f}%)\n"
            f"Направление: {result.axis}\n"
            f"Центр масштабирования: {anchor_display}\n"
            f"Коэффициент: {result.scale:.6f}\n"
            f"Результат: {result.stretched_dxf.name if result.stretched_dxf else '–'}"
        )
        self.info_text.configure(text=text)

    # ------------------------------------------------------------------ #
    # Пакетная обработка
    # ------------------------------------------------------------------ #
    def _select_batch_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.batch_folder_var.set(folder)
            self._batch_log(f"Выбрана папка: {folder}")

    def _batch_log(self, message: str):
        """Добавляет сообщение в лог"""
        if self.batch_log_text:
            self.batch_log_text.insert("end", f"{message}\n")
            self.batch_log_text.see("end")
            self.update()

    def _batch_clear(self):
        self.batch_folder_var.set("")
        self.batch_results.clear()
        self.batch_bases_analyzed = False
        self.base_analyzer.bases.clear()
        if self.batch_log_text:
            self.batch_log_text.delete("1.0", "end")

    def _analyze_bases(self):
        """Анализирует файлы оснований в выбранной папке"""
        folder = self.batch_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Папка не выбрана", "Сначала выберите папку с файлами.")
            return
        
        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("Ошибка", f"Папка не найдена: {folder}")
            return
        
        self.batch_log_text.delete("1.0", "end")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"АНАЛИЗ ФАЙЛОВ ОСНОВАНИЙ")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"Папка: {folder}")
        self._batch_log("")
        
        try:
            bases = self.base_analyzer.analyze_folder(folder_path)
            
            self._batch_log(f"✅ Найдено оснований: {len(bases)}")
            self._batch_log("")
            
            for korpus_num, base in sorted(bases.items()):
                self._batch_log(f"[{korpus_num.upper()}] {base.file_path.name}")
                self._batch_log(f"  ├─ Дуга 1 (для ВНЕШНЕГО радиуса):")
                self._batch_log(f"  │  Радиус: {base.arc1.radius:.3f} мм")
                self._batch_log(f"  │  Длина:  {base.arc1.arc_length:.3f} мм")
                self._batch_log(f"  │")
                self._batch_log(f"  └─ Дуга 2 (для ВНУТРЕННЕГО радиуса):")
                self._batch_log(f"     Радиус: {base.arc2.radius:.3f} мм")
                self._batch_log(f"     Длина:  {base.arc2.arc_length:.3f} мм")
                self._batch_log(f"     Разница: {base.arc1.arc_length - base.arc2.arc_length:.3f} мм")
                self._batch_log("")
            
            # Ищем файлы радиусов
            radius_files = self.base_analyzer.find_radius_files(folder_path)
            
            self._batch_log(f"📁 Найдено файлов радиусов: {len(radius_files)}")
            for rf in radius_files:
                self._batch_log(f"   - {rf.name}")
            
            self._batch_log("")
            self._batch_log(f"{'='*70}")
            self._batch_log(f"✅ АНАЛИЗ ЗАВЕРШЁН. Можно запускать обработку!")
            self._batch_log(f"{'='*70}")
            
            self.batch_bases_analyzed = True
            messagebox.showinfo(
                "Анализ завершён", 
                f"Найдено оснований: {len(bases)}\n"
                f"Найдено файлов радиусов: {len(radius_files)}\n\n"
                f"Теперь нажмите '2. Запустить обработку'"
            )
            
        except FileNotFoundError as e:
            self._batch_log(f"❌ ОШИБКА: {e}")
            messagebox.showerror("Ошибка", str(e))
        except Exception as exc:
            self._batch_log(f"❌ ОШИБКА: {exc}")
            logging.exception("Analyze bases error")
            messagebox.showerror("Ошибка анализа", str(exc))

    def _batch_process(self):
        """Пакетная обработка с автоматическим определением целевых длин"""
        folder = self.batch_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Папка не выбрана", "Выберите папку с файлами.")
            return
        
        if not self.batch_bases_analyzed or not self.base_analyzer.bases:
            messagebox.showwarning(
                "Основания не проанализированы", 
                "Сначала нажмите '1. Анализировать основания'"
            )
            return

        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("Ошибка", f"Папка не найдена: {folder}")
            return

        # Получаем файлы радиусов
        radius_files = self.base_analyzer.find_radius_files(folder_path)
        
        if not radius_files:
            messagebox.showwarning("Нет файлов", "Не найдено файлов радиусов для обработки.")
            return

        self._batch_log("")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"ПАКЕТНАЯ ОБРАБОТКА С АВТОМАТИЧЕСКИМ СОПОСТАВЛЕНИЕМ")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"Папка: {folder}")
        self._batch_log(f"Найдено файлов радиусов: {len(radius_files)}")
        self._batch_log(f"")

        axis = self.batch_axis_var.get()
        anchor_map = {"Левый край": "start", "Центр": "center", "Правый край": "end"}
        anchor = anchor_map.get(self.batch_anchor_var.get(), "start")

        self.batch_results.clear()
        success_count = 0
        error_count = 0
        skip_count = 0

        for i, file_path in enumerate(radius_files, 1):
            self._batch_log(f"[{i}/{len(radius_files)}] {file_path.name}")
            
            try:
                # Измерение текущей длины
                measure_result = self.service.measure(str(file_path), axis=axis)
                current_length = measure_result.current_length
                
                # Сопоставление с основанием
                try:
                    radius_info = self.base_analyzer.match_radius_to_base(file_path, current_length)
                except KeyError as e:
                    self._batch_log(f"    ⚠️  ПРОПУЩЕН: {e}")
                    skip_count += 1
                    self._batch_log("")
                    continue
                
                target_length = radius_info.target_length
                
                # Информация о сопоставлении
                self._batch_log(f"    Тип: {radius_info.type_name}")
                self._batch_log(f"    Корпус: {radius_info.korpus_number}")
                self._batch_log(f"    Основание: {radius_info.base_info.file_path.name}")
                
                if radius_info.is_outer:
                    self._batch_log(f"    Целевая длина: {target_length:.3f} мм (ДУГА 1 основания)")
                else:
                    self._batch_log(f"    Целевая длина: {target_length:.3f} мм (ДУГА 2 основания)")
                
                # Проверка: нужна ли обработка?
                delta = target_length - current_length
                if abs(delta) < 0.01:
                    self._batch_log(f"    ✓ Длина уже соответствует целевой, обработка не требуется")
                    skip_count += 1
                    self._batch_log("")
                    continue
                
                # Растяжение/сжатие
                result = self.service.stretch(target_length, axis=axis, anchor=anchor)
                self.batch_results.append(result)
                
                action = "УДЛИНЕНИЕ" if result.scale >= 1.0 else "УКОРОЧЕНИЕ"
                percent = (result.scale - 1) * 100
                
                self._batch_log(f"    {action}: {current_length:.3f} -> {target_length:.3f} мм")
                self._batch_log(f"    Delta: {delta:+.3f} мм ({percent:+.2f}%)")
                self._batch_log(f"    Коэффициент: {result.scale:.6f}")
                self._batch_log(f"    ✅ Результат: {result.stretched_dxf.name}")
                success_count += 1
                
            except Exception as exc:
                self._batch_log(f"    ❌ ОШИБКА: {exc}")
                error_count += 1
                logging.exception(f"Error processing {file_path}")
            
            self._batch_log("")

        self._batch_log(f"{'='*70}")
        self._batch_log(f"ОБРАБОТКА ЗАВЕРШЕНА")
        self._batch_log(f"✅ Успешно обработано: {success_count}")
        self._batch_log(f"⚠️  Пропущено: {skip_count}")
        self._batch_log(f"❌ Ошибок: {error_count}")
        self._batch_log(f"{'='*70}")
        
        # Автоматическая проверка ширины после обработки длин
        if success_count > 0:
            self._batch_log("")
            self._batch_log(f"{'='*70}")
            self._batch_log(f"АВТОМАТИЧЕСКАЯ ПРОВЕРКА ШИРИНЫ")
            self._batch_log(f"{'='*70}")
            try:
                width_checks = self.base_analyzer.check_widths(folder_path, tolerance=0.1)
                issues_found = sum(1 for check in width_checks if check.needs_adjustment)
                
                if issues_found > 0:
                    self._batch_log(f"⚠️  ВНИМАНИЕ: Обнаружено {issues_found} корпусов с расхождением ширины!")
                    self._batch_log("")
                    for check in width_checks:
                        if check.needs_adjustment:
                            self._batch_log(f"[{check.korpus_number.upper()}] Разница: {abs(check.width_difference):.3f} мм")
                    self._batch_log("")
                    self._batch_log("💡 Рекомендация: Используйте кнопку '📏 Выровнять ширину'")
                else:
                    self._batch_log(f"✅ Ширины всех разверток в норме!")
            except Exception as e:
                self._batch_log(f"⚠️  Не удалось проверить ширину: {e}")
            self._batch_log(f"{'='*70}")

        messagebox.showinfo(
            "Обработка завершена", 
            f"✅ Успешно: {success_count}\n"
            f"⚠️  Пропущено: {skip_count}\n"
            f"❌ Ошибок: {error_count}"
        )

    def _check_widths(self):
        """Проверяет ширину разверток и выводит отчёт"""
        folder = self.batch_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Папка не выбрана", "Сначала выберите папку с файлами.")
            return
        
        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("Ошибка", f"Папка не найдена: {folder}")
            return
        
        self._batch_log("")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"ПРОВЕРКА ШИРИНЫ РАЗВЕРТОК")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"Папка: {folder}")
        self._batch_log("")
        
        try:
            width_checks = self.base_analyzer.check_widths(folder_path, tolerance=0.1)
            
            if not width_checks:
                self._batch_log("❌ Не найдено файлов для проверки")
                messagebox.showinfo("Проверка ширины", "Не найдено файлов для проверки")
                return
            
            issues_found = sum(1 for check in width_checks if check.needs_adjustment)
            
            self._batch_log(f"Проверено корпусов: {len(width_checks)}")
            self._batch_log(f"Найдено расхождений: {issues_found}")
            self._batch_log("")
            
            for check in width_checks:
                self._batch_log(f"[{check.korpus_number.upper()}] {check.status_message}")
                if check.has_both_files:
                    if check.outer_file:
                        self._batch_log(f"  ├─ Внешний: {check.outer_file.name} ({check.outer_width:.3f} мм)")
                    if check.inner_file:
                        self._batch_log(f"  └─ Внутренний: {check.inner_file.name} ({check.inner_width:.3f} мм)")
                    
                    if check.needs_adjustment:
                        self._batch_log(f"     ⚠️  ТРЕБУЕТСЯ ВЫРАВНИВАНИЕ!")
                else:
                    if check.outer_file:
                        self._batch_log(f"  - Внешний: {check.outer_file.name}")
                    if check.inner_file:
                        self._batch_log(f"  - Внутренний: {check.inner_file.name}")
                self._batch_log("")
            
            self._batch_log(f"{'='*70}")
            if issues_found > 0:
                self._batch_log(f"⚠️  Обнаружено {issues_found} корпусов с расхождением ширины!")
                self._batch_log(f"Нажмите '📏 Выровнять ширину' для исправления")
                messagebox.showwarning(
                    "Проверка ширины завершена",
                    f"⚠️  Обнаружено расхождений: {issues_found}\n\n"
                    f"Проверено корпусов: {len(width_checks)}\n"
                    f"Нажмите '📏 Выровнять ширину' для исправления"
                )
            else:
                self._batch_log(f"✅ Все ширины в норме!")
                messagebox.showinfo(
                    "Проверка ширины завершена",
                    f"✅ Все ширины в норме!\n\n"
                    f"Проверено корпусов: {len(width_checks)}"
                )
            self._batch_log(f"{'='*70}")
            
        except Exception as exc:
            self._batch_log(f"❌ ОШИБКА: {exc}")
            logging.exception("Width check error")
            messagebox.showerror("Ошибка проверки ширины", str(exc))
    
    def _batch_process_both_axes(self):
        """Пакетная обработка с одновременной коррекцией длины И ширины"""
        folder = self.batch_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Папка не выбрана", "Выберите папку с файлами.")
            return
        
        if not self.batch_bases_analyzed or not self.base_analyzer.bases:
            messagebox.showwarning(
                "Основания не проанализированы", 
                "Сначала нажмите '1. Анализировать основания'"
            )
            return

        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("Ошибка", f"Папка не найдена: {folder}")
            return
        
        # Проверяем ширины
        try:
            width_checks = self.base_analyzer.check_widths(folder_path, tolerance=0.1)
            issues_found = sum(1 for check in width_checks if check.needs_adjustment)
            
            if issues_found == 0:
                messagebox.showinfo(
                    "Выравнивание не требуется", 
                    "Ширины уже одинаковы!\nДостаточно обычной обработки длин."
                )
                return
            
            # Диалог выбора эталона ширины
            dialog = ctk.CTkToplevel(self)
            dialog.title("Одновременная коррекция длины + ширины")
            dialog.geometry("550x300")
            dialog.transient(self)
            dialog.grab_set()
            
            selected_option = {"value": None}
            
            ctk.CTkLabel(
                dialog, 
                text="🎯 ОДНОВРЕМЕННАЯ КОРРЕКЦИЯ ДЛИНЫ И ШИРИНЫ",
                font=self.font_title
            ).pack(pady=15)
            
            ctk.CTkLabel(
                dialog,
                text=f"Обнаружено {issues_found} корпусов с расхождением ширины.\n"
                     "Выберите эталонную ширину для выравнивания:",
                font=self.font_regular,
                text_color="#FFA500"
            ).pack(pady=10)
            
            def on_choice(use_outer: bool):
                selected_option["value"] = use_outer
                dialog.destroy()
            
            button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            button_frame.pack(pady=15)
            
            ctk.CTkButton(
                button_frame,
                text="📏 ВНЕШНИЙ радиус (эталон ширины)",
                command=lambda: on_choice(True),
                font=self.font_regular,
                fg_color="#2B7A0B",
                height=50,
                width=450
            ).pack(pady=5)
            
            ctk.CTkButton(
                button_frame,
                text="📏 ВНУТРЕННИЙ радиус (эталон ширины)",
                command=lambda: on_choice(False),
                font=self.font_regular,
                fg_color="#1f538d",
                height=50,
                width=450
            ).pack(pady=5)
            
            ctk.CTkButton(
                button_frame,
                text="Отмена",
                command=dialog.destroy,
                font=self.font_regular,
                fg_color="gray30",
                height=35,
                width=450
            ).pack(pady=5)
            
            self.wait_window(dialog)
            
            if selected_option["value"] is None:
                return
            
            use_outer_width = selected_option["value"]
            
        except Exception as exc:
            logging.exception("Width check error")
            messagebox.showerror("Ошибка проверки ширины", str(exc))
            return
        
        # Получаем файлы радиусов (ИСХОДНЫЕ, без _stretch!)
        radius_files = self.base_analyzer.find_radius_files(folder_path)
        
        if not radius_files:
            messagebox.showwarning("Нет файлов", "Не найдено файлов радиусов для обработки.")
            return

        self._batch_log("")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"ОДНОВРЕМЕННАЯ КОРРЕКЦИЯ ДЛИНЫ + ШИРИНЫ (2в1)")
        self._batch_log(f"{'='*70}")
        self._batch_log(f"Папка: {folder}")
        self._batch_log(f"Эталон ширины: {'ВНЕШНИЙ радиус' if use_outer_width else 'ВНУТРЕННИЙ радиус'}")
        self._batch_log(f"Найдено файлов радиусов: {len(radius_files)}")
        self._batch_log("")

        axis_x = self.batch_axis_var.get()
        anchor_map = {"Левый край": "start", "Центр": "center", "Правый край": "end"}
        anchor = anchor_map.get(self.batch_anchor_var.get(), "start")

        self.batch_results.clear()
        success_count = 0
        error_count = 0
        skip_count = 0

        # Группируем файлы по корпусам для определения эталонной ширины
        korpus_widths = {}
        for check in width_checks:
            if check.has_both_files:
                target_width = check.outer_width if use_outer_width else check.inner_width
                korpus_widths[check.korpus_number] = target_width

        for i, file_path in enumerate(radius_files, 1):
            self._batch_log(f"[{i}/{len(radius_files)}] {file_path.name}")
            
            try:
                # Измерение текущих размеров
                measure_result = self.service.measure(str(file_path), axis=axis_x)
                current_length = measure_result.current_length
                current_width = measure_result.width
                
                # Сопоставление с основанием
                try:
                    radius_info = self.base_analyzer.match_radius_to_base(file_path, current_length)
                except KeyError as e:
                    self._batch_log(f"    ⚠️  ПРОПУЩЕН: {e}")
                    skip_count += 1
                    self._batch_log("")
                    continue
                
                target_length = radius_info.target_length
                target_width = korpus_widths.get(radius_info.korpus_number, current_width)
                
                # Проверка необходимости обработки
                length_delta = target_length - current_length
                width_delta = target_width - current_width
                
                needs_length_adj = abs(length_delta) >= 0.01
                needs_width_adj = abs(width_delta) >= 0.01
                
                if not needs_length_adj and not needs_width_adj:
                    self._batch_log(f"    ✓ Размеры уже соответствуют целевым")
                    skip_count += 1
                    self._batch_log("")
                    continue
                
                # Информация о коррекции
                self._batch_log(f"    Тип: {radius_info.type_name}")
                self._batch_log(f"    Корпус: {radius_info.korpus_number}")
                
                if needs_length_adj:
                    self._batch_log(f"    ДЛИНА (X): {current_length:.3f} → {target_length:.3f} мм (Δ {length_delta:+.3f})")
                else:
                    self._batch_log(f"    ДЛИНА (X): {current_length:.3f} мм ✓")
                
                if needs_width_adj:
                    self._batch_log(f"    ШИРИНА (Y): {current_width:.3f} → {target_width:.3f} мм (Δ {width_delta:+.3f})")
                else:
                    self._batch_log(f"    ШИРИНА (Y): {current_width:.3f} мм ✓")
                
                # Применяем одновременную обработку обеих осей
                from core.dxf_processor import DxfProcessor
                dxf_proc = DxfProcessor()
                dxf_proc.load(str(file_path))
                
                output_file = dxf_proc.stretch_both_axes(
                    target_length_x=target_length,
                    target_width_y=target_width,
                    anchor_x=anchor,
                    anchor_y=anchor
                )
                
                # Создаём результат для отчёта
                scale_x = target_length / current_length if current_length > 0 else 1.0
                scale_y = target_width / current_width if current_width > 0 else 1.0
                
                from core.flat_pattern_service import StretchResult
                result = StretchResult(
                    source_file=file_path,
                    dxf_file=file_path,
                    current_length=current_length,
                    width=current_width,
                    target_length=target_length,
                    scale=scale_x,
                    axis=axis_x,
                    anchor=anchor,
                    stretched_dxf=output_file
                )
                self.batch_results.append(result)
                
                self._batch_log(f"    Коэфф. X: {scale_x:.6f}, Коэфф. Y: {scale_y:.6f}")
                self._batch_log(f"    ✅ Результат: {output_file.name}")
                success_count += 1
                
            except Exception as exc:
                self._batch_log(f"    ❌ ОШИБКА: {exc}")
                error_count += 1
                logging.exception(f"Error processing {file_path}")
            
            self._batch_log("")

        self._batch_log(f"{'='*70}")
        self._batch_log(f"ОБРАБОТКА ЗАВЕРШЕНА")
        self._batch_log(f"✅ Успешно обработано: {success_count}")
        self._batch_log(f"⚠️  Пропущено: {skip_count}")
        self._batch_log(f"❌ Ошибок: {error_count}")
        self._batch_log(f"{'='*70}")

        messagebox.showinfo(
            "Обработка завершена", 
            f"✅ Успешно: {success_count}\n"
            f"⚠️  Пропущено: {skip_count}\n"
            f"❌ Ошибок: {error_count}\n\n"
            f"Одновременно скорректированы длина И ширина!"
        )
    
    def _align_widths(self):
        """Выравнивает ширину разверток с выбором эталона"""
        folder = self.batch_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Папка не выбрана", "Сначала выберите папку с файлами.")
            return
        
        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("Ошибка", f"Папка не найдена: {folder}")
            return
        
        # Сначала проверяем ширины
        try:
            width_checks = self.base_analyzer.check_widths(folder_path, tolerance=0.1)
            issues_found = sum(1 for check in width_checks if check.needs_adjustment)
            
            if issues_found == 0:
                messagebox.showinfo("Выравнивание не требуется", "Все ширины уже одинаковы!")
                return
            
            # Диалог выбора эталона
            dialog = ctk.CTkToplevel(self)
            dialog.title("Выбор эталонной ширины")
            dialog.geometry("500x250")
            dialog.transient(self)
            dialog.grab_set()
            
            selected_option = {"value": None}
            
            ctk.CTkLabel(
                dialog, 
                text="Выберите эталонную ширину для выравнивания:",
                font=self.font_title
            ).pack(pady=20)
            
            ctk.CTkLabel(
                dialog,
                text=f"Обнаружено {issues_found} корпусов с расхождением ширины",
                font=self.font_regular,
                text_color="#FFA500"
            ).pack(pady=10)
            
            def on_choice(use_outer: bool):
                selected_option["value"] = use_outer
                dialog.destroy()
            
            button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            button_frame.pack(pady=20)
            
            ctk.CTkButton(
                button_frame,
                text="📏 Использовать ширину ВНЕШНЕГО радиуса",
                command=lambda: on_choice(True),
                font=self.font_regular,
                fg_color="#2B7A0B",
                height=50,
                width=400
            ).pack(pady=5)
            
            ctk.CTkButton(
                button_frame,
                text="📏 Использовать ширину ВНУТРЕННЕГО радиуса",
                command=lambda: on_choice(False),
                font=self.font_regular,
                fg_color="#1f538d",
                height=50,
                width=400
            ).pack(pady=5)
            
            ctk.CTkButton(
                button_frame,
                text="Отмена",
                command=dialog.destroy,
                font=self.font_regular,
                fg_color="gray30",
                height=35,
                width=400
            ).pack(pady=5)
            
            self.wait_window(dialog)
            
            if selected_option["value"] is None:
                return  # Пользователь отменил
            
            use_outer_width = selected_option["value"]
            
            # Выполняем выравнивание
            self._batch_log("")
            self._batch_log(f"{'='*70}")
            self._batch_log(f"ВЫРАВНИВАНИЕ ШИРИНЫ РАЗВЕРТОК")
            self._batch_log(f"{'='*70}")
            self._batch_log(f"Эталон: {'ВНЕШНИЙ радиус' if use_outer_width else 'ВНУТРЕННИЙ радиус'}")
            self._batch_log("")
            
            anchor_map = {"Левый край": "start", "Центр": "center", "Правый край": "end"}
            anchor = anchor_map.get(self.batch_anchor_var.get(), "start")
            
            results = self.base_analyzer.align_widths(folder_path, use_outer_width, anchor)
            
            total_processed = sum(len(files) for files in results.values())
            
            if total_processed > 0:
                self._batch_log(f"✅ Обработано корпусов: {len(results)}")
                self._batch_log(f"✅ Выровнено файлов: {total_processed}")
                self._batch_log("")
                
                for korpus_num, files in sorted(results.items()):
                    self._batch_log(f"[{korpus_num.upper()}]")
                    for file in files:
                        self._batch_log(f"  ✅ {file.name}")
                    self._batch_log("")
                
                self._batch_log(f"{'='*70}")
                self._batch_log("✅ ВЫРАВНИВАНИЕ ЗАВЕРШЕНО")
                self._batch_log(f"{'='*70}")
                
                messagebox.showinfo(
                    "Выравнивание завершено",
                    f"✅ Успешно выровнено!\n\n"
                    f"Обработано корпусов: {len(results)}\n"
                    f"Выровнено файлов: {total_processed}\n\n"
                    f"Эталон: {'ВНЕШНИЙ радиус' if use_outer_width else 'ВНУТРЕННИЙ радиус'}"
                )
            else:
                self._batch_log("⚠️  Нет файлов для обработки")
                messagebox.showinfo("Выравнивание", "Нет файлов для обработки")
            
        except Exception as exc:
            self._batch_log(f"❌ ОШИБКА: {exc}")
            logging.exception("Width alignment error")
            messagebox.showerror("Ошибка выравнивания ширины", str(exc))
    
    def _generate_report(self):
        """Генерирует детальный текстовый отчёт о пакетной обработке"""
        if not self.batch_results:
            messagebox.showwarning("Нет данных", "Сначала выполните пакетную обработку.")
            return

        folder = self.batch_folder_var.get().strip()
        if not folder:
            folder = str(Path.cwd())

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(folder) / f"ОТЧЁТ_ОБРАБОТКА_{timestamp}.txt"

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("="*80 + "\n")
                f.write("      ОТЧЁТ: АВТОМАТИЧЕСКАЯ ПАКЕТНАЯ ОБРАБОТКА РАЗВЕРТОК\n")
                f.write("="*80 + "\n")
                f.write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
                f.write(f"Папка: {folder}\n")
                f.write(f"Обработано файлов: {len(self.batch_results)}\n")
                f.write("\n")
                
                # Информация об основаниях
                if self.base_analyzer.bases:
                    f.write("="*80 + "\n")
                    f.write("ИСПОЛЬЗОВАННЫЕ ОСНОВАНИЯ\n")
                    f.write("="*80 + "\n")
                    for korpus_num, base in sorted(self.base_analyzer.bases.items()):
                        f.write(f"\n[{korpus_num.upper()}] {base.file_path.name}\n")
                        f.write(f"  Дуга 1 (внешняя):  R={base.arc1.radius:.3f} мм, L={base.arc1.arc_length:.3f} мм\n")
                        f.write(f"  Дуга 2 (внутренняя): R={base.arc2.radius:.3f} мм, L={base.arc2.arc_length:.3f} мм\n")
                        f.write(f"  Разница:          {base.arc1.arc_length - base.arc2.arc_length:.3f} мм\n")
                    f.write("\n")

                # Детали обработки каждого файла
                f.write("="*80 + "\n")
                f.write("РЕЗУЛЬТАТЫ ОБРАБОТКИ\n")
                f.write("="*80 + "\n\n")

                for i, result in enumerate(self.batch_results, 1):
                    action = "УДЛИНЕНИЕ" if result.scale >= 1.0 else "УКОРОЧЕНИЕ"
                    delta = result.target_length - result.current_length
                    percent = (result.scale - 1) * 100
                    
                    f.write("-"*80 + "\n")
                    f.write(f"ФАЙЛ {i}: {result.source_file.name}\n")
                    f.write("-"*80 + "\n")
                    
                    # Определяем тип и корпус из имени файла
                    filename = result.source_file.name
                    try:
                        korpus_match = re.search(r'корп(\d+)', filename, re.IGNORECASE)
                        if korpus_match:
                            korpus_num = f"корп{korpus_match.group(1)}"
                            if korpus_num in self.base_analyzer.bases:
                                base = self.base_analyzer.bases[korpus_num]
                                is_outer = "Внешний" in filename or "внешний" in filename
                                
                                f.write(f"Тип:             {'Внешний радиус' if is_outer else 'Внутренний радиус'}\n")
                                f.write(f"Корпус:          {korpus_num}\n")
                                f.write(f"Основание:       {base.file_path.name}\n")
                                
                                if is_outer:
                                    f.write(f"Эталон:          Дуга 1 (R={base.arc1.radius:.3f} мм)\n")
                                else:
                                    f.write(f"Эталон:          Дуга 2 (R={base.arc2.radius:.3f} мм)\n")
                    except:
                        pass
                    
                    f.write(f"Исходная длина:  {result.current_length:.3f} мм\n")
                    f.write(f"Целевая длина:   {result.target_length:.3f} мм\n")
                    f.write(f"{action}:        {delta:+.3f} мм ({percent:+.2f}%)\n")
                    f.write(f"Направление:     {result.axis}\n")
                    f.write(f"Коэффициент:     {result.scale:.6f}\n")
                    f.write(f"Результат:       {result.stretched_dxf.name if result.stretched_dxf else '–'}\n")
                    f.write("\n")

                # Сводная статистика
                f.write("="*80 + "\n")
                f.write("СВОДНАЯ СТАТИСТИКА\n")
                f.write("="*80 + "\n")
                
                elongated = sum(1 for r in self.batch_results if r.scale >= 1.0)
                shortened = sum(1 for r in self.batch_results if r.scale < 1.0)
                
                f.write(f"Всего обработано:     {len(self.batch_results)}\n")
                f.write(f"  - Удлинено:         {elongated}\n")
                f.write(f"  - Укорочено:        {shortened}\n")
                
                avg_delta = sum(abs(r.target_length - r.current_length) for r in self.batch_results) / len(self.batch_results)
                f.write(f"Средняя коррекция:    {avg_delta:.3f} мм\n")
                
                f.write("\n")
                f.write("="*80 + "\n")
                f.write("                        КОНЕЦ ОТЧЁТА\n")
                f.write("="*80 + "\n")

            self._batch_log(f"✅ Отчёт сохранён: {report_path.name}")
            messagebox.showinfo("Отчёт создан", f"Детальный отчёт сохранён:\n{report_path}")

        except Exception as exc:
            logging.exception("Report generation error")
            messagebox.showerror("Ошибка", f"Не удалось создать отчёт: {exc}")


if __name__ == "__main__":
    app = FlatPatternApp()
    app.mainloop()
