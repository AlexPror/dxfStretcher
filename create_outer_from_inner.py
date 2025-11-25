"""
Скрипт создания развертки внешнего радиуса из внутреннего
для случаев, когда конфигурация отверстий идентична
"""
from pathlib import Path
from core.flat_pattern_service import FlatPatternService
from core.base_analyzer import BaseAnalyzer


def create_outer_from_inner(inner_radius_file: str, korpus_number: int, output_name: str = None):
    """
    Создает развертку внешнего радиуса на основе внутреннего.
    
    Args:
        inner_radius_file: Путь к DXF файлу внутреннего радиуса
        korpus_number: Номер корпуса (1, 2, 3, ...)
        output_name: Имя выходного файла (по умолчанию: auto)
    
    Пример:
        create_outer_from_inner(
            "test/Внутренний радиус Г1.корп4 - 1шт.dxf",
            korpus_number=4,
            output_name="Внешний радиус Г1.корп4 - 1шт.dxf"
        )
    """
    
    print("="*80)
    print("СОЗДАНИЕ ВНЕШНЕГО РАДИУСА ИЗ ВНУТРЕННЕГО")
    print("="*80)
    print()
    
    inner_path = Path(inner_radius_file)
    
    if not inner_path.exists():
        raise FileNotFoundError(f"Файл не найден: {inner_radius_file}")
    
    # Поиск основания для получения целевой длины
    test_dir = inner_path.parent
    base_files = list(test_dir.glob(f"Основание*корп{korpus_number}*.dxf")) + \
                 list(test_dir.glob(f"Основание*корп{korpus_number}*.DXF"))
    
    if not base_files:
        raise FileNotFoundError(
            f"Не найден файл основания для корп{korpus_number}\n"
            f"Ожидается: Основание Г1.корп{korpus_number} - 1шт.dxf"
        )
    
    base_file = base_files[0]
    
    # Анализ основания
    print(f"📁 Исходный файл:  {inner_path.name}")
    print(f"📐 Файл основания: {base_file.name}")
    print()
    
    analyzer = BaseAnalyzer()
    base_info = analyzer._analyze_base_file(base_file)
    
    print("Информация из основания:")
    print(f"  Дуга 1 (внешняя):  R={base_info.arc1.radius:.3f} мм, L={base_info.arc1.arc_length:.3f} мм")
    print(f"  Дуга 2 (внутренняя): R={base_info.arc2.radius:.3f} мм, L={base_info.arc2.arc_length:.3f} мм")
    print(f"  Разница: {base_info.arc1.arc_length - base_info.arc2.arc_length:.3f} мм")
    print()
    
    # Обработка
    service = FlatPatternService()
    
    # Измеряем текущую длину внутреннего радиуса
    print("📏 Измерение внутреннего радиуса...")
    measure_result = service.measure(str(inner_path), axis="X")
    current_length = measure_result.current_length
    print(f"  Текущая длина: {current_length:.3f} мм")
    print()
    
    # Целевая длина = длина дуги 1 (внешней) из основания
    target_length = base_info.outer_radius_length
    
    print(f"🎯 Целевая длина (дуга 1): {target_length:.3f} мм")
    print()
    
    # Проверка
    delta = target_length - current_length
    if abs(delta) < 0.01:
        print("⚠️  ВНИМАНИЕ: Длины уже совпадают!")
        print("   Возможно, у вас уже внешний радиус, а не внутренний?")
        return
    
    if delta < 0:
        print("⚠️  ВНИМАНИЕ: Целевая длина МЕНЬШЕ текущей!")
        print("   Обычно внешний радиус ДЛИННЕЕ внутреннего.")
        print("   Проверьте правильность входных данных.")
        response = input("   Продолжить? (y/n): ")
        if response.lower() != 'y':
            print("Отменено пользователем.")
            return
    
    print(f"📊 Операция: УДЛИНЕНИЕ на {delta:+.3f} мм ({delta/current_length*100:+.2f}%)")
    print()
    
    # Выполняем растяжение
    print("⚙️  Обработка...")
    result = service.stretch(target_length, axis="X", anchor="start")
    
    print(f"✅ Готово!")
    print(f"   Коэффициент: {result.scale:.6f}")
    print(f"   Результат: {result.stretched_dxf.name}")
    print()
    
    # Сохранение
    if output_name:
        output_path = test_dir / output_name
    else:
        # Автоматическое имя: заменяем "Внутренний" на "Внешний"
        auto_name = inner_path.stem.replace("Внутренний", "Внешний").replace("внутренний", "Внешний")
        output_path = test_dir / f"{auto_name}_from_inner.dxf"
    
    saved_path = service.save_stretched(str(output_path))
    
    print("="*80)
    print("💾 ФАЙЛ СОХРАНЁН")
    print("="*80)
    print(f"Путь: {saved_path}")
    print()
    print("ПРОВЕРЬТЕ РЕЗУЛЬТАТ:")
    print("1. Откройте файл в CAD программе")
    print("2. Измерьте длину по оси X")
    print(f"3. Должно быть: {target_length:.3f} мм")
    print("4. Проверьте, что отверстия не искажены")
    print("5. Проверьте, что дуги гибов сохранили форму")
    print("="*80)
    
    return saved_path


def main():
    """Пример использования"""
    import sys
    
    if len(sys.argv) < 3:
        print("ИСПОЛЬЗОВАНИЕ:")
        print("  python create_outer_from_inner.py <файл_внутреннего_радиуса> <номер_корпуса> [имя_выходного_файла]")
        print()
        print("ПРИМЕР:")
        print('  python create_outer_from_inner.py "test/Внутренний радиус Г1.корп4 - 1шт.dxf" 4')
        print()
        print("ИЛИ с указанием выходного имени:")
        print('  python create_outer_from_inner.py "test/Внутренний радиус Г1.корп4 - 1шт.dxf" 4 "Внешний радиус Г1.корп4 - 1шт.dxf"')
        print()
        
        # Интерактивный режим
        print("="*80)
        print("ИНТЕРАКТИВНЫЙ РЕЖИМ")
        print("="*80)
        
        inner_file = input("Введите путь к файлу внутреннего радиуса: ").strip('"')
        korpus = int(input("Введите номер корпуса (1, 2, 3, ...): ").strip())
        output = input("Введите имя выходного файла (или Enter для автоматического): ").strip('"')
        
        if not output:
            output = None
        
        try:
            create_outer_from_inner(inner_file, korpus, output)
        except Exception as e:
            print(f"\n❌ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()
        
        input("\nНажмите Enter для выхода...")
        return
    
    # Аргументы командной строки
    inner_file = sys.argv[1]
    korpus_number = int(sys.argv[2])
    output_name = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        create_outer_from_inner(inner_file, korpus_number, output_name)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


