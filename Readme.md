# Smart Windows Cleaner & Booster

Утилита для очистки, ускорения и управления автозагрузкой в Windows 10/11.
Работает как готовый `.exe` (Python не нужен) или из исходников.

---

## 🚀 Быстрый старт (для обычного пользователя)

1. Скачай `SmartWindowsCleaner.exe`.
2. Положи его в удобную папку (например, `D:\Apps\SmartCleaner\`).
3. Запусти двойным кликом. Консоль не откроется.
4. По желанию — сделай ярлык на рабочем столе.

> **Python не требуется.** Всё упаковано внутри `.exe`.
> Рядом с `.exe` будет создан файл `disabled_autostart.json` — не удаляй его, там хранятся отключённые программы автозагрузки.

---

## 🛠 Для разработчика (запуск из кода)

Требуется **Python 3.10+**.

```bash
pip install customtkinter psutil
python main.py

# Smart Windows Cleaner & Booster

Utility for cleaning, boosting, and managing startup on Windows 10/11.
Available as a standalone `.exe` (no Python required) or from source.

---

## 🚀 Quick Start (Regular Users)

1. Download `SmartWindowsCleaner.exe`.
2. Move it to a convenient folder (e.g., `D:\Apps\SmartCleaner\`).
3. Double-click to run. No console window appears.
4. Optional — create a desktop shortcut.

> **Python is NOT required.** Everything is bundled inside the `.exe`.
> A `disabled_autostart.json` file will be created next to the `.exe` — do not delete it, it stores disabled startup entries.

---

## 🛠 For Developers (Run from Source)

Requires **Python 3.10+**.

```bash
pip install customtkinter psutil
python main.py
[Preview](preview.png)
