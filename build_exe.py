"""
Скрипт для создания EXE файла DXF Stretcher
"""
import sys
import subprocess
from pathlib import Path
import os

# Настройка кодировки для Windows
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def build_exe():
    """Создаёт EXE файл с помощью PyInstaller"""
    
    print("="*80)
    print("СОЗДАНИЕ EXE ФАЙЛА - DXF Stretcher")
    print("="*80)
    
    # Проверяем, установлен ли PyInstaller
    try:
        import PyInstaller
        print("[OK] PyInstaller установлен")
    except ImportError:
        print("[!] PyInstaller не установлен. Устанавливаю...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller установлен")
    
    # Параметры сборки
    app_name = "DXF_Stretcher"
    main_script = "app.py"
    icon_file = None  # Можно добавить иконку позже
    
    print(f"\n[*] Сборка {app_name}.exe...")
    print(f"    Скрипт: {main_script}")
    
    # Команда PyInstaller
    cmd = [
        "pyinstaller",
        "--name", app_name,
        "--onefile",  # Один EXE файл
        "--windowed",  # Без консоли (GUI приложение)
        "--clean",
        # Добавляем данные
        "--add-data", "core;core",
        # Скрываем импорты
        "--hidden-import", "customtkinter",
        "--hidden-import", "ezdxf",
        "--hidden-import", "PIL._tkinter_finder",
        # Исключаем ненужное для уменьшения размера
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        main_script
    ]
    
    # Если есть иконка
    if icon_file and Path(icon_file).exists():
        cmd.extend(["--icon", icon_file])
    
    print(f"\n[*] Запуск сборки...")
    print(f"    (это может занять 1-2 минуты)")
    
    try:
        subprocess.check_call(cmd)
        
        # Проверяем результат
        exe_file = Path("dist") / f"{app_name}.exe"
        
        if exe_file.exists():
            size_mb = exe_file.stat().st_size / (1024 * 1024)
            print(f"\n{'='*80}")
            print(f"[OK] УСПЕШНО!")
            print(f"{'='*80}")
            print(f"\n[+] EXE файл создан:")
            print(f"    Путь: {exe_file.absolute()}")
            print(f"    Размер: {size_mb:.1f} МБ")
            print(f"\n[!] МОЖНО ОТПРАВЛЯТЬ В ЦЕХ!")
            print(f"\n[i] Инструкция для цеха:")
            print(f"    1. Скопируйте файл {app_name}.exe на компьютер")
            print(f"    2. Запустите двойным кликом")
            print(f"    3. Python НЕ ТРЕБУЕТСЯ!")
            print(f"\n[i] Что включено:")
            print(f"    [+] DXF Stretcher GUI")
            print(f"    [+] Все библиотеки (ezdxf, customtkinter)")
            print(f"    [+] Модули обработки (core/)")
            print(f"    [+] Работает БЕЗ Python")
            print(f"    [+] Работает БЕЗ КОМПАС (с DXF файлами)")
        else:
            print(f"\n[!] Ошибка: EXE файл не найден")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Ошибка при сборке: {e}")
        return False
    
    return True


if __name__ == "__main__":
    build_exe()

