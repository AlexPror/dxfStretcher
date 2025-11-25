"""
Анализ файлов оснований и извлечение длин дуг для автоматического сопоставления
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import ezdxf


@dataclass
class ArcInfo:
    """Информация о дуге"""
    radius: float
    arc_length: float
    center: Tuple[float, float]
    start_angle: float
    end_angle: float


@dataclass
class BaseInfo:
    """Информация об основании"""
    file_path: Path
    korpus_number: str  # "корп1", "корп2", etc.
    arc1: ArcInfo  # Внешняя дуга (больший радиус)
    arc2: ArcInfo  # Внутренняя дуга (меньший радиус)
    
    @property
    def outer_radius_length(self) -> float:
        """Длина для внешнего радиуса"""
        return self.arc1.arc_length
    
    @property
    def inner_radius_length(self) -> float:
        """Длина для внутреннего радиуса"""
        return self.arc2.arc_length


@dataclass
class RadiusFileInfo:
    """Информация о файле радиуса"""
    file_path: Path
    korpus_number: str
    is_outer: bool  # True = внешний, False = внутренний
    current_length: float
    target_length: float
    base_info: BaseInfo
    current_width: float = 0.0  # Текущая ширина развертки
    
    @property
    def type_name(self) -> str:
        return "Внешний радиус" if self.is_outer else "Внутренний радиус"


@dataclass
class WidthCheckResult:
    """Результат проверки ширины разверток"""
    korpus_number: str
    outer_file: Optional[Path]
    inner_file: Optional[Path]
    outer_width: Optional[float]
    inner_width: Optional[float]
    width_difference: float
    needs_adjustment: bool
    
    @property
    def has_both_files(self) -> bool:
        return self.outer_file is not None and self.inner_file is not None
    
    @property
    def status_message(self) -> str:
        if not self.has_both_files:
            return "❓ Не все файлы найдены"
        if not self.needs_adjustment:
            return f"✅ Ширины одинаковы ({self.outer_width:.3f} мм)"
        return f"⚠️  Разница {abs(self.width_difference):.3f} мм (внешний: {self.outer_width:.3f}, внутренний: {self.inner_width:.3f})"


class BaseAnalyzer:
    """Анализатор файлов оснований"""
    
    def __init__(self):
        self.bases: Dict[str, BaseInfo] = {}  # korpus_number -> BaseInfo
    
    def analyze_folder(self, folder_path: Path) -> Dict[str, BaseInfo]:
        """
        Анализирует папку и находит все файлы оснований.
        
        Returns:
            Dict[korpus_number, BaseInfo]
        """
        self.bases.clear()
        
        # Ищем все файлы оснований
        base_files = list(folder_path.glob("Основание*.dxf")) + list(folder_path.glob("Основание*.DXF"))
        
        if not base_files:
            raise FileNotFoundError(f"Не найдено файлов оснований в папке: {folder_path}")
        
        for base_file in base_files:
            try:
                base_info = self._analyze_base_file(base_file)
                self.bases[base_info.korpus_number] = base_info
            except Exception as e:
                print(f"[!] Ошибка при анализе {base_file.name}: {e}")
                continue
        
        if not self.bases:
            raise RuntimeError("Не удалось проанализировать ни одного файла основания")
        
        return self.bases
    
    def _analyze_base_file(self, file_path: Path) -> BaseInfo:
        """Анализирует один файл основания"""
        # Извлекаем номер корпуса из имени
        korpus_number = self._extract_korpus_number(file_path.name)
        
        # Читаем DXF и находим дуги
        doc = ezdxf.readfile(str(file_path))
        msp = doc.modelspace()
        
        arcs = []
        for entity in msp:
            if entity.dxftype() == "ARC":
                arc_info = self._extract_arc_info(entity)
                if arc_info:
                    arcs.append(arc_info)
        
        if len(arcs) < 2:
            raise ValueError(f"Найдено менее 2 дуг в файле {file_path.name}. Требуется 2 основные дуги.")
        
        # Сортируем дуги по радиусу (большая первая)
        arcs.sort(key=lambda a: a.radius, reverse=True)
        
        # Берём 2 самые большие дуги
        arc1 = arcs[0]  # Внешняя (больший радиус)
        arc2 = arcs[1]  # Внутренняя (меньший радиус)
        
        return BaseInfo(
            file_path=file_path,
            korpus_number=korpus_number,
            arc1=arc1,
            arc2=arc2
        )
    
    def _extract_arc_info(self, entity) -> Optional[ArcInfo]:
        """Извлекает информацию о дуге из DXF entity"""
        try:
            radius = entity.dxf.radius
            center = (entity.dxf.center.x, entity.dxf.center.y)
            start_angle = entity.dxf.start_angle
            end_angle = entity.dxf.end_angle
            
            # Вычисляем длину дуги
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            
            # Корректировка для случая когда end_angle < start_angle
            if end_rad < start_rad:
                end_rad += 2 * math.pi
            
            angle_diff = end_rad - start_rad
            arc_length = radius * angle_diff
            
            return ArcInfo(
                radius=radius,
                arc_length=arc_length,
                center=center,
                start_angle=start_angle,
                end_angle=end_angle
            )
        except Exception:
            return None
    
    def _extract_korpus_number(self, filename: str) -> str:
        """
        Извлекает номер корпуса из имени файла.
        
        Примеры:
        - "Основание Г1.корп1 - 1шт.DXF" -> "корп1"
        - "Основание Г1.корп2 - 1шт.dxf" -> "корп2"
        """
        # Ищем паттерн "корп" + цифра
        match = re.search(r'корп(\d+)', filename, re.IGNORECASE)
        if match:
            return f"корп{match.group(1)}"
        
        # Альтернативный паттерн: просто цифра после "Г"
        match = re.search(r'Г\d*\.?(\d+)', filename, re.IGNORECASE)
        if match:
            return f"корп{match.group(1)}"
        
        raise ValueError(f"Не удалось извлечь номер корпуса из имени: {filename}")
    
    def find_radius_files(self, folder_path: Path) -> List[Path]:
        """Находит все файлы радиусов в папке"""
        radius_files = []
        
        # Ищем внешние и внутренние радиусы
        patterns = ["Внешний радиус*.dxf", "Внутренний радиус*.dxf"]
        
        for pattern in patterns:
            files = list(folder_path.glob(pattern))
            # Исключаем уже обработанные файлы
            files = [f for f in files if not f.stem.endswith("_stretch") and not f.stem.endswith("_shrink")]
            radius_files.extend(files)
        
        return sorted(radius_files, key=lambda x: x.name)
    
    def match_radius_to_base(self, radius_file: Path, current_length: float) -> RadiusFileInfo:
        """
        Сопоставляет файл радиуса с соответствующим основанием.
        
        Args:
            radius_file: Путь к файлу радиуса
            current_length: Текущая длина радиуса (из измерения)
            
        Returns:
            RadiusFileInfo с информацией о целевой длине
        """
        filename = radius_file.name
        
        # Определяем тип радиуса
        is_outer = "Внешний" in filename or "внешний" in filename
        
        # Извлекаем номер корпуса
        korpus_number = self._extract_korpus_number(filename)
        
        # Находим соответствующее основание
        if korpus_number not in self.bases:
            available = ", ".join(self.bases.keys())
            raise KeyError(
                f"Не найдено основание для {korpus_number}. "
                f"Доступные основания: {available}"
            )
        
        base_info = self.bases[korpus_number]
        
        # Определяем целевую длину
        if is_outer:
            target_length = base_info.outer_radius_length
        else:
            target_length = base_info.inner_radius_length
        
        return RadiusFileInfo(
            file_path=radius_file,
            korpus_number=korpus_number,
            is_outer=is_outer,
            current_length=current_length,
            target_length=target_length,
            base_info=base_info
        )
    
    def check_widths(self, folder_path: Path, tolerance: float = 0.1) -> List[WidthCheckResult]:
        """
        Проверяет ширину разверток внутренних и внешних радиусов для каждого корпуса.
        
        Args:
            folder_path: Папка с файлами разверток
            tolerance: Допустимое отклонение ширины в мм (по умолчанию 0.1 мм)
            
        Returns:
            Список результатов проверки для каждого корпуса
        """
        from .dxf_processor import DxfProcessor
        
        results = []
        dxf_proc = DxfProcessor()
        
        # Находим все файлы радиусов
        radius_files = self.find_radius_files(folder_path)
        
        # Группируем по корпусам
        korpus_files: Dict[str, Dict[str, Path]] = {}
        for file_path in radius_files:
            try:
                korpus_num = self._extract_korpus_number(file_path.name)
                is_outer = "Внешний" in file_path.name or "внешний" in file_path.name
                
                if korpus_num not in korpus_files:
                    korpus_files[korpus_num] = {}
                
                korpus_files[korpus_num]["outer" if is_outer else "inner"] = file_path
            except Exception:
                continue
        
        # Проверяем каждый корпус
        for korpus_num in sorted(korpus_files.keys()):
            files = korpus_files[korpus_num]
            outer_file = files.get("outer")
            inner_file = files.get("inner")
            
            outer_width = None
            inner_width = None
            
            try:
                if outer_file:
                    info = dxf_proc.load(str(outer_file))
                    outer_width = info.width_y
                
                if inner_file:
                    info = dxf_proc.load(str(inner_file))
                    inner_width = info.width_y
                
                # Вычисляем разницу
                if outer_width is not None and inner_width is not None:
                    width_diff = outer_width - inner_width
                    needs_adjustment = abs(width_diff) > tolerance
                else:
                    width_diff = 0.0
                    needs_adjustment = False
                
                result = WidthCheckResult(
                    korpus_number=korpus_num,
                    outer_file=outer_file,
                    inner_file=inner_file,
                    outer_width=outer_width,
                    inner_width=inner_width,
                    width_difference=width_diff,
                    needs_adjustment=needs_adjustment
                )
                results.append(result)
                
            except Exception as e:
                print(f"[!] Ошибка при проверке ширины для {korpus_num}: {e}")
                continue
        
        return results
    
    def align_widths(self, folder_path: Path, use_outer_width: bool = True, 
                     anchor: str = "start") -> Dict[str, List[Path]]:
        """
        Выравнивает ширину разверток (ось Y) для всех корпусов.
        
        Args:
            folder_path: Папка с файлами разверток
            use_outer_width: Если True, использует ширину внешнего радиуса как эталон
                           Если False, использует ширину внутреннего радиуса
            anchor: Точка привязки для масштабирования ("start", "center", "end")
            
        Returns:
            Словарь {korpus_number: [список_обработанных_файлов]}
        """
        from .dxf_processor import DxfProcessor
        
        dxf_proc = DxfProcessor()
        results: Dict[str, List[Path]] = {}
        
        # Проверяем ширины
        width_checks = self.check_widths(folder_path, tolerance=0.1)
        
        for check in width_checks:
            if not check.has_both_files or not check.needs_adjustment:
                continue
            
            korpus_files = []
            
            # Определяем эталонную ширину и файл, который нужно обработать
            if use_outer_width:
                target_width = check.outer_width
                file_to_process = check.inner_file
                current_width = check.inner_width
            else:
                target_width = check.inner_width
                file_to_process = check.outer_file
                current_width = check.outer_width
            
            if file_to_process and target_width and current_width:
                try:
                    # Загружаем файл
                    dxf_proc.load(str(file_to_process))
                    
                    # Выполняем растяжение по оси Y
                    output_file = dxf_proc.stretch(
                        target_length=target_width,
                        axis="Y",
                        anchor=anchor
                    )
                    korpus_files.append(output_file)
                    
                except Exception as e:
                    print(f"[!] Ошибка при выравнивании ширины {file_to_process.name}: {e}")
                    continue
            
            if korpus_files:
                results[check.korpus_number] = korpus_files
        
        return results
    
    def get_summary(self) -> str:
        """Возвращает сводку по найденным основаниям"""
        if not self.bases:
            return "Нет проанализированных оснований"
        
        lines = ["НАЙДЕННЫЕ ОСНОВАНИЯ:", "=" * 70]
        
        for korpus_num, base in sorted(self.bases.items()):
            lines.append(f"\n[{korpus_num.upper()}] {base.file_path.name}")
            lines.append(f"  Дуга 1 (внешняя):  R={base.arc1.radius:.3f} мм, Длина={base.arc1.arc_length:.3f} мм")
            lines.append(f"  Дуга 2 (внутренняя): R={base.arc2.radius:.3f} мм, Длина={base.arc2.arc_length:.3f} мм")
            lines.append(f"  Разница длин: {base.arc1.arc_length - base.arc2.arc_length:.3f} мм")
        
        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

