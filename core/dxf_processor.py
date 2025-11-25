"""
Работа с DXF: измерение длины и аффинное масштабирование
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

import ezdxf
from ezdxf.math import Matrix44
from ezdxf import bbox


@dataclass
class DxfInfo:
    source_path: Path
    length_x: float
    width_y: float
    entity_count: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float


class DxfProcessor:
    """Измерение и масштабирование DXF"""

    def __init__(self):
        self.last_doc: Optional[ezdxf.EzDxfDocument] = None
        self.last_path: Optional[Path] = None
        self.extents: Optional[bbox.Extents] = None
        self.zone_cache = {}

    # ------------------------------------------------------------------ #
    def load(self, path: str) -> DxfInfo:
        self.last_path = Path(path)
        self.last_doc = ezdxf.readfile(str(self.last_path))
        msp = self.last_doc.modelspace()
        extents = bbox.extents(msp)
        if extents is None:
            raise RuntimeError("Не удалось вычислить габарит DXF.")

        self.extents = extents
        self.zone_cache.clear()

        length_x = extents.size.x
        width_y = extents.size.y
        min_x = extents.extmin.x
        max_x = extents.extmax.x
        min_y = extents.extmin.y
        max_y = extents.extmax.y

        entity_count = len(msp)
        return DxfInfo(self.last_path, length_x, width_y, entity_count, min_x, max_x, min_y, max_y)

    # ------------------------------------------------------------------ #
    def stretch(self, target_length: float, axis: str = "X", anchor: str = "start",
                save_path: Optional[str] = None) -> Path:
        """
        Растягивает геометрию вдоль заданной оси.

        axis: 'X' или 'Y'
        anchor: 'start' (минимум), 'center', 'end' (максимум)
        """
        if not self.last_doc or not self.extents:
            raise RuntimeError("DXF не загружен. Вызовите load().")

        axis = axis.upper()
        if axis not in ("X", "Y"):
            raise ValueError("axis должен быть X или Y")

        size = self.extents.size.x if axis == "X" else self.extents.size.y
        if size == 0:
            raise ValueError("Текущая длина равна 0, растяжение невозможно.")

        if size == target_length:
            return self.last_path

        zones = self._get_zones(axis)
        mapping = self._build_mapping(zones, axis, target_length)
        self._apply_mapping(mapping, axis)
        self._apply_anchor_shift(mapping, axis, anchor)

        output_path = Path(save_path) if save_path else self.last_path.with_name(
            f"{self.last_path.stem}_stretch.dxf"
        )
        self.last_doc.saveas(output_path)
        return output_path
    
    def stretch_both_axes(self, target_length_x: float, target_width_y: float,
                          anchor_x: str = "start", anchor_y: str = "start",
                          save_path: Optional[str] = None) -> Path:
        """
        Растягивает геометрию одновременно по обеим осям (X и Y).
        
        Args:
            target_length_x: Целевая длина по оси X
            target_width_y: Целевая ширина по оси Y
            anchor_x: Точка привязки для оси X ('start', 'center', 'end')
            anchor_y: Точка привязки для оси Y ('start', 'center', 'end')
            save_path: Путь для сохранения (опционально)
            
        Returns:
            Путь к сохранённому файлу
        """
        if not self.last_doc or not self.extents:
            raise RuntimeError("DXF не загружен. Вызовите load().")
        
        current_length_x = self.extents.size.x
        current_width_y = self.extents.size.y
        
        needs_x_stretch = abs(current_length_x - target_length_x) > 1e-6
        needs_y_stretch = abs(current_width_y - target_width_y) > 1e-6
        
        # Если ничего не нужно растягивать
        if not needs_x_stretch and not needs_y_stretch:
            return self.last_path
        
        # Обрабатываем ось X
        if needs_x_stretch:
            zones_x = self._get_zones("X")
            mapping_x = self._build_mapping(zones_x, "X", target_length_x)
            self._apply_mapping(mapping_x, "X")
            self._apply_anchor_shift(mapping_x, "X", anchor_x)
            # Обновляем extents после изменения
            msp = self.last_doc.modelspace()
            self.extents = bbox.extents(msp)
        
        # Обрабатываем ось Y
        if needs_y_stretch:
            zones_y = self._get_zones("Y")
            mapping_y = self._build_mapping(zones_y, "Y", target_width_y)
            self._apply_mapping(mapping_y, "Y")
            self._apply_anchor_shift(mapping_y, "Y", anchor_y)
        
        # Сохраняем результат
        output_path = Path(save_path) if save_path else self.last_path.with_name(
            f"{self.last_path.stem}_stretch.dxf"
        )
        self.last_doc.saveas(output_path)
        return output_path

    # ------------------------------------------------------------------ #
    @dataclass
    class Zone:
        start_old: float
        end_old: float
        zone_type: str  # 'stretch' or 'fixed'

        @property
        def length(self) -> float:
            return max(0.0, self.end_old - self.start_old)

    @dataclass
    class MappingSegment(Zone):
        start_new: float = 0.0
        end_new: float = 0.0

        @property
        def length_new(self) -> float:
            return max(0.0, self.end_new - self.start_new)

    def _get_axis_bounds(self, axis: str) -> (float, float):
        if axis == "X":
            return self.extents.extmin.x, self.extents.extmax.x
        return self.extents.extmin.y, self.extents.extmax.y

    def _is_fixed_entity(self, entity) -> bool:
        dxftype = entity.dxftype()
        if dxftype in {"CIRCLE", "ARC", "ELLIPSE", "SPLINE"}:
            return True
        if dxftype in {"LWPOLYLINE", "POLYLINE"}:
            try:
                if any(abs(vertex.dxf.bulge) > 1e-6 for vertex in entity.vertices()):
                    return True
            except AttributeError:
                pass
        return False

    def _entity_interval(self, entity, axis: str) -> Optional[tuple]:
        try:
            ext = bbox.extents([entity])
        except Exception:
            return None
        if not ext:
            return None
        start = ext.extmin.x if axis == "X" else ext.extmin.y
        end = ext.extmax.x if axis == "X" else ext.extmax.y
        return start, end

    def _get_zones(self, axis: str) -> List["DxfProcessor.Zone"]:
        cached = self.zone_cache.get(axis)
        if cached:
            return cached

        axis_min, axis_max = self._get_axis_bounds(axis)
        if axis_max < axis_min:
            axis_max = axis_min

        intervals = []
        for entity in self.last_doc.modelspace():
            if not self._is_fixed_entity(entity):
                continue
            interval = self._entity_interval(entity, axis)
            if interval:
                start = max(axis_min, interval[0])
                end = min(axis_max, interval[1])
                if end > start:
                    intervals.append((start, end))

        intervals.sort(key=lambda x: x[0])
        merged = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)

        zones: List[DxfProcessor.Zone] = []
        cursor = axis_min
        for start, end in merged:
            if start > cursor:
                zones.append(DxfProcessor.Zone(cursor, start, "stretch"))
            zones.append(DxfProcessor.Zone(start, end, "fixed"))
            cursor = max(cursor, end)
        if cursor < axis_max:
            zones.append(DxfProcessor.Zone(cursor, axis_max, "stretch"))

        if not zones:
            zones.append(DxfProcessor.Zone(axis_min, axis_max, "stretch"))

        self.zone_cache[axis] = zones
        return zones

    def _build_mapping(self, zones: List["DxfProcessor.Zone"], axis: str, target_length: float) \
            -> List["DxfProcessor.MappingSegment"]:
        axis_min, axis_max = self._get_axis_bounds(axis)
        current_length = axis_max - axis_min
        delta = target_length - current_length

        stretch_total = sum(zone.length for zone in zones if zone.zone_type == "stretch")
        if abs(delta) > 1e-9 and stretch_total <= 0:
            raise RuntimeError("Нет участков для растяжения. Измените модель или уменьшите требуемую длину.")

        mapping: List[DxfProcessor.MappingSegment] = []

        current_old = axis_min
        current_new = axis_min

        for zone in zones:
            zone_length = zone.length
            if zone.zone_type == "stretch" and stretch_total > 0:
                extra = delta * (zone_length / stretch_total)
                new_length = zone_length + extra
            else:
                new_length = zone_length

            mapping.append(
                DxfProcessor.MappingSegment(
                    start_old=zone.start_old,
                    end_old=zone.end_old,
                    zone_type=zone.zone_type,
                    start_new=current_new,
                    end_new=current_new + new_length
                )
            )
            current_old = zone.end_old
            current_new += new_length

        return mapping

    def _map_value(self, value: float, mapping: List["DxfProcessor.MappingSegment"]) -> float:
        eps = 1e-9
        for segment in mapping:
            if value < segment.start_old - eps:
                continue
            if value <= segment.end_old + eps:
                old_len = segment.length
                if old_len < eps:
                    offset = segment.start_new - segment.start_old
                    return value + offset
                ratio = (value - segment.start_old) / old_len
                return segment.start_new + ratio * segment.length_new

        offset = mapping[-1].end_new - mapping[-1].end_old
        return value + offset

    def _apply_mapping(self, mapping: List["DxfProcessor.MappingSegment"], axis: str):
        msp = self.last_doc.modelspace()
        for entity in msp:
            dxftype = entity.dxftype()
            try:
                if dxftype == "LINE":
                    self._map_line(entity, mapping, axis)
                elif dxftype in {"LWPOLYLINE", "POLYLINE"}:
                    self._map_polyline(entity, mapping, axis)
                elif dxftype == "SPLINE":
                    self._map_spline(entity, mapping, axis)
                elif dxftype in {"CIRCLE", "ARC"}:
                    self._map_circle_arc(entity, mapping, axis)
                elif dxftype == "POINT":
                    self._map_point(entity, mapping, axis)
                else:
                    self._map_generic(entity, mapping, axis)
            except Exception:
                continue

    def _map_line(self, entity, mapping, axis: str):
        start = entity.dxf.start
        end = entity.dxf.end
        if axis == "X":
            new_start = (self._map_value(start.x, mapping), start.y, start.z)
            new_end = (self._map_value(end.x, mapping), end.y, end.z)
        else:
            new_start = (start.x, self._map_value(start.y, mapping), start.z)
            new_end = (end.x, self._map_value(end.y, mapping), end.z)
        entity.dxf.start = new_start
        entity.dxf.end = new_end

    def _map_polyline(self, entity, mapping, axis: str):
        for vertex in entity.vertices():
            if axis == "X":
                vertex.dxf.x = self._map_value(vertex.dxf.x, mapping)
            else:
                vertex.dxf.y = self._map_value(vertex.dxf.y, mapping)

    def _map_spline(self, entity, mapping, axis: str):
        if hasattr(entity, "control_points"):
            new_ctrl = []
            for point in entity.control_points:
                x, y, z = point
                if axis == "X":
                    new_ctrl.append((self._map_value(x, mapping), y, z))
                else:
                    new_ctrl.append((x, self._map_value(y, mapping), z))
            entity.control_points = new_ctrl

        if hasattr(entity, "fit_points") and entity.fit_points:
            new_fit = []
            for point in entity.fit_points:
                x, y, z = point
                if axis == "X":
                    new_fit.append((self._map_value(x, mapping), y, z))
                else:
                    new_fit.append((x, self._map_value(y, mapping), z))
            entity.fit_points = new_fit

        if hasattr(entity, "knot_values") and entity.knot_values:
            # координаты узлов не зависят от положения, поэтому не изменяем
            pass

    def _map_circle_arc(self, entity, mapping, axis: str):
        center = entity.dxf.center
        if axis == "X":
            new_center = (self._map_value(center.x, mapping), center.y, center.z)
        else:
            new_center = (center.x, self._map_value(center.y, mapping), center.z)
        entity.dxf.center = new_center

    def _map_point(self, entity, mapping, axis: str):
        location = entity.dxf.location
        if axis == "X":
            entity.dxf.location = (self._map_value(location.x, mapping), location.y, location.z)
        else:
            entity.dxf.location = (location.x, self._map_value(location.y, mapping), location.z)

    def _map_generic(self, entity, mapping, axis: str):
        # Для остальных типов пытаемся применить матрицу преобразования
        axis_index = 0 if axis == "X" else 1
        offset = mapping[0].start_new - mapping[0].start_old
        if axis_index == 0:
            transform = Matrix44.translate(offset, 0, 0)
        else:
            transform = Matrix44.translate(0, offset, 0)
        try:
            entity.transform(transform)
        except Exception:
            pass

    def _apply_anchor_shift(self, mapping, axis: str, anchor: str):
        axis_min, axis_max = self._get_axis_bounds(axis)
        if anchor == "center":
            anchor_value = (axis_min + axis_max) / 2
        elif anchor in {"end", "top", "right"}:
            anchor_value = axis_max
        else:
            anchor_value = axis_min

        new_anchor = self._map_value(anchor_value, mapping)
        shift = anchor_value - new_anchor
        if abs(shift) < 1e-6:
            return

        if axis == "X":
            transform = Matrix44.translate(shift, 0, 0)
        else:
            transform = Matrix44.translate(0, shift, 0)

        for entity in self.last_doc.modelspace():
            try:
                entity.transform(transform)
            except Exception:
                continue


