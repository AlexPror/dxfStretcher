"""
Высокоуровневая логика удлинения разверток
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .kompas_connector import KompasConnector
from .dxf_processor import DxfProcessor, DxfInfo


@dataclass
class StretchResult:
    source_file: Path
    dxf_file: Path
    current_length: float
    width: float
    target_length: float
    scale: float
    axis: str
    anchor: str
    stretched_dxf: Optional[Path]


class FlatPatternService:
    """Главный сервис: импорт, измерение, растяжение, экспорт"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.kompas = KompasConnector()
        self.dxf = DxfProcessor()
        self.current_info: Optional[DxfInfo] = None
        self.current_dxf: Optional[Path] = None
        self.stretched_path: Optional[Path] = None
        self.current_axis: str = "X"

    # ------------------------------------------------------------------ #
    def _export_via_kompas(self, file_path: Path) -> Path:
        """Экспортирует файл через КОМПАС в DXF (во временную папку)"""
        if not self.kompas.open_document(str(file_path)):
            raise RuntimeError("Не удалось открыть файл в КОМПАС-3D")

        temp_dir = Path(tempfile.gettempdir()) / "flat_pattern_stretch"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_dxf = temp_dir / f"{file_path.stem}_tmp.dxf"

        if not self.kompas.export_active_to_dxf(str(temp_dxf)):
            self.kompas.close_active_document(save=False)
            raise RuntimeError("КОМПАС не смог экспортировать документ в DXF")

        self.kompas.close_active_document(save=False)
        return temp_dxf

    def _prepare_dxf(self, file_path: str) -> Path:
        """Возвращает путь к DXF (исходный или экспортированный через КОМПАС)"""
        path = Path(file_path)
        if path.suffix.lower() == ".dxf":
            return path
        return self._export_via_kompas(path)

    # ------------------------------------------------------------------ #
    def measure(self, file_path: str, axis: str = "X") -> StretchResult:
        """Загружает файл и измеряет текущую длину развертки"""
        dxf_path = self._prepare_dxf(file_path)
        info = self.dxf.load(str(dxf_path))

        self.current_info = info
        self.current_dxf = dxf_path
        self.stretched_path = None
        self.current_axis = axis.upper()
        current_length = info.length_x if self.current_axis == "X" else info.width_y

        return StretchResult(
            source_file=Path(file_path),
            dxf_file=dxf_path,
            current_length=current_length,
            width=info.width_y,
            target_length=current_length,
            scale=1.0,
            axis=self.current_axis,
            anchor="start",
            stretched_dxf=None,
        )

    def stretch(self, target_length: float, axis: str = "X", anchor: str = "start") -> StretchResult:
        """Применяет коэффициент растяжения к текущей развертке"""
        if not self.current_info or not self.current_dxf:
            raise RuntimeError("Сначала необходимо выбрать файл и выполнить измерение.")

        axis = axis.upper()
        axis_length = self.current_info.length_x if axis == "X" else self.current_info.width_y
        stretched = self.dxf.stretch(target_length, axis=axis, anchor=anchor)
        self.stretched_path = stretched

        scale = target_length / axis_length
        return StretchResult(
            source_file=self.current_info.source_path,
            dxf_file=self.current_dxf,
            current_length=axis_length,
            width=self.current_info.width_y,
            target_length=target_length,
            scale=scale,
            axis=axis,
            anchor=anchor,
            stretched_dxf=stretched,
        )

    def save_stretched(self, output_path: str) -> Path:
        """Сохраняет результат в указанное место"""
        if not self.stretched_path or not self.stretched_path.exists():
            raise RuntimeError("Ещё не выполнено растяжение.")

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.stretched_path, destination)
        return destination

    def clear(self):
        self.current_info = None
        self.current_dxf = None
        self.stretched_path = None


