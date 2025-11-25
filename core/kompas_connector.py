"""
Компонент подключения к КОМПАС-3D (облегчённая версия BaseKompasComponent)
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import pythoncom
from win32com.client import Dispatch, DispatchEx


@dataclass
class KompasSettings:
    """Настройки подключения к КОМПАС-3D"""
    visible: bool = bool(int(os.getenv("KOMPAS_VISIBLE", "1")))
    prog_id: str = os.getenv("KOMPAS_PROG_ID", "Kompas.Application.7")


class KompasConnector:
    """
    Упрощённый менеджер подключения к КОМПАС-3D.
    Используется всеми сервисами проекта.
    """

    def __init__(self, settings: Optional[KompasSettings] = None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.settings = settings or KompasSettings()
        self.application = None
        self.connected = False

    # ------------------------------------------------------------------ #
    # Подключение / отключение
    # ------------------------------------------------------------------ #
    def connect(self, force: bool = False) -> bool:
        """Подключение к КОМПАС-3D"""
        if self.connected and not force and self.application:
            return True

        try:
            pythoncom.CoInitialize()
        except pythoncom.com_error:
            # Уже инициализировано в текущем потоке
            pass

        try:
            self.logger.info(f"Подключение к КОМПАС ({self.settings.prog_id})")
            try:
                self.application = Dispatch(self.settings.prog_id)
            except Exception:
                self.application = DispatchEx(self.settings.prog_id)

            self.application.Visible = bool(self.settings.visible)
            self.application.HideMessage = 0
            self.connected = True
            self.logger.info("КОМПАС подключён")
            return True
        except Exception as exc:
            self.logger.error(f"Не удалось подключиться к КОМПАС-3D: {exc}")
            self.connected = False
            return False

    def disconnect(self):
        """Отключение от КОМПАС-3D"""
        if not self.connected:
            return
        self.logger.info("Отключение от КОМПАС-3D")
        self.application = None
        try:
            pythoncom.CoUninitialize()
        except pythoncom.com_error:
            pass
        self.connected = False

    # ------------------------------------------------------------------ #
    # Работа с документами
    # ------------------------------------------------------------------ #
    def open_document(self, file_path: str) -> bool:
        """Открыть документ (деталь, сборку или чертёж)"""
        if not self.connect():
            return False

        path = Path(file_path)
        if not path.exists():
            self.logger.error(f"Файл не найден: {file_path}")
            return False

        try:
            doc = self.application.Documents.Open(str(path), False, False)
            if doc:
                self.application.ActiveDocument = doc
                time.sleep(0.5)
                self.logger.info(f"Открыт документ: {doc.Name}")
                return True
        except Exception as exc:
            self.logger.error(f"Не удалось открыть документ {file_path}: {exc}")

        return False

    def close_active_document(self, save: bool = False) -> bool:
        """Закрыть активный документ"""
        if not self.connected:
            return False

        try:
            active_doc = self.application.ActiveDocument
            if not active_doc:
                return False
            name = active_doc.Name
            active_doc.Close(save)
            self.logger.info(f"Документ закрыт: {name} (save={save})")
            return True
        except Exception as exc:
            self.logger.error(f"Ошибка закрытия документа: {exc}")
            return False

    def export_active_to_dxf(self, output_path: str) -> bool:
        """
        Сохраняет активный 2D-документ в DXF через ksSaveToDXF.
        Предполагается, что активен чертёж/развёртка.
        """
        if not self.connected:
            return False

        try:
            api5 = Dispatch("Kompas.Application.5")
            doc2d = api5.ActiveDocument2D
            if not doc2d:
                self.logger.error("ActiveDocument2D не найден")
                return False

            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.exists():
                out_path.unlink()

            result = doc2d.ksSaveToDXF(str(out_path))
            time.sleep(1)
            if result and out_path.exists():
                self.logger.info(f"DXF сохранён: {out_path}")
                return True

            self.logger.error("ksSaveToDXF вернул False или файл не создан")
            return False
        except Exception as exc:
            self.logger.error(f"Ошибка сохранения DXF: {exc}")
            return False


