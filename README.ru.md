<h1 align="center">m2res</h1>

<p align="center">
  <b>Полный райс для Hyprland</b> — панель, док, замок, уведомления, плеер, лаунчер, профили, запись экрана, скриншоты, OCR и диктовка, с переключением оформления одной командой.
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.ru.md"><b>Русский</b></a>
</p>

<p align="center">
  <img alt="Arch Linux" src="https://img.shields.io/badge/Arch_Linux-1793D1?logo=archlinux&logoColor=white">
  <img alt="Hyprland 0.56+" src="https://img.shields.io/badge/Hyprland-0.56%2B_(Lua)-58E1FF">
  <img alt="32:9" src="https://img.shields.io/badge/дисплей-32%3A9-b0d500">
  <img alt="Темы" src="https://img.shields.io/badge/тем-14-b0d500">
</p>

<p align="center">
  <img src="docs/hero.jpg" alt="Рабочий стол m2res 5120×1440" width="100%">
</p>

<p align="center"><i>Waybar, плеер с визуализацией и терминалы — снимок с реального монитора 5120×1440@120.</i></p>

---

## Содержание

- [Возможности](#возможности)
- [Галерея](#галерея)
- [Райсы: переключение оформления одной командой](#райсы-переключение-оформления-одной-командой)
- [Горячие клавиши](#горячие-клавиши)
- [Установка](#установка)
- [Удаление](#удаление)
- [Документация](#документация)

## Возможности

| | |
|---|---|
| 🎛️ **Панель и док** | Waybar с версткой под райс и авто-скрывающийся боковой или нижний док |
| 🔒 **Экран блокировки** | HUD в стиле ретро-ТВ с палитрой райса и понятной причиной отказа |
| 🔔 **Уведомления** | Mako в стиле райса и центр уведомлений (`SUPER+N`) |
| 🎵 **Плеер** | Музыкальный плеер с визуализацией звука (`SUPER+P`) |
| 🚀 **Лаунчер** | Запуск приложений (`SUPER+D`), центр управления (`SUPER+X`), шпаргалка по биндам (`SUPER+F1`) |
| 🖼️ **Обои** | Выбор обоев-револьвером с переходами (`SUPER+W`); акцент следует за обоями |
| 🎨 **Райсы** | Смена всего оформления разом, с предпросмотром и автооткатом |
| 🗂️ **Профили и раскладки** | Переключение рабочих профилей (`SUPER+CTRL+P`) и пресеты окон по столам |
| 🎙️ **Запись и захват** | Запись экрана, скриншоты с редактором, история буфера обмена |
| 🔤 **OCR и диктовка** | Текст с области экрана и офлайн-распознавание речи через Whisper |
| 🩺 **Самопроверка** | `m2res-doctor` проверяет всю конфигурацию (66 проверок) |

## Галерея

<table>
  <tr>
    <td align="center" width="50%"><img src="docs/launcher.jpg" alt="Лаунчер"><br><sub><b>Лаунчер</b> · <code>SUPER+D</code></sub></td>
    <td align="center" width="50%"><img src="docs/binds.jpg" alt="Шпаргалка по биндам"><br><sub><b>Шпаргалка по биндам</b> · <code>SUPER+F1</code></sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/control.jpg" alt="Центр управления" width="420"><br><sub><b>Центр управления</b> · <code>SUPER+X</code></sub></td>
    <td align="center"><img src="docs/wallpick.jpg" alt="Выбор обоев"><br><sub><b>Выбор обоев</b> · <code>SUPER+W</code></sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/notif.jpg" alt="Уведомления"><br><sub><b>Уведомления</b></sub></td>
    <td align="center"><img src="docs/dock.jpg" alt="Док" width="100"><br><sub><b>Док</b> · <code>SUPER+SHIFT+B</code></sub></td>
  </tr>
</table>

## Райсы: переключение оформления одной командой

**Райс** — это целостный внешний вид. Применение меняет палитру, обои, Waybar, геометрию и анимации Hyprland, форму виджетов, уведомления, экран блокировки, Ghostty, док и звуки.

- **8 авторских райсов:** `m2res`, `paper`, `zen`, `brutal`, `cyber`, `glass`, `tty`, `macos`
- **6 тем с палитрами:** Catppuccin, Everforest, Matte Black, Nord, Osaka Jade, Ristretto

![Райсы: m2res, paper, zen, brutal, cyber, glass, tty, nord, osaka-jade](docs/rices.jpg)

Нажмите **`SUPER+ALT+R`**, чтобы открыть карусель. **Enter** примеряет райс на 10 секунд и спрашивает, оставить ли его: Enter — оставить, Esc — вернуть, без ответа вернётся само.

Из терминала:

```bash
m2res-rice list                # доступные райсы
m2res-rice apply <имя>         # переключиться на райс
m2res-rice preview <имя>       # примерить временно
m2res-rice back                # вернуться к предыдущему
m2res-rice import-themes       # импорт тем с палитрами
```

Подробная документация: [.config/m2res/README.md](.config/m2res/README.md#райсы--переключатель-оформления-m2res-rice).

## Горячие клавиши

`SUPER+F1` показывает полный список, он всегда актуален. Основные:

| Клавиша | Действие |
|---|---|
| `SUPER+D` | Лаунчер |
| `SUPER+X` | Центр управления |
| `SUPER+N` | Центр уведомлений |
| `SUPER+P` | Музыкальный плеер |
| `SUPER+W` | Выбор обоев |
| `SUPER+ALT+R` | Карусель райсов |
| `SUPER+CTRL+P` | Следующий рабочий профиль |
| `SUPER+SHIFT+B` | Показать/скрыть док |
| `SUPER+L` | Экран блокировки |
| `SUPER+F1` | Шпаргалка по биндам |

## Требования

- Arch Linux с `pacman` и, при желании, AUR-помощником
- Hyprland **0.56+** с Lua-конфигом (`~/.config/hypr/hyprland.lua`)
- Широкий монитор: раскладки рассчитаны на **32:9** (5120×1440), на других размерах тоже работают

## Установка

```bash
git clone https://github.com/orybakov/m2res-rice.git
cd m2res-rice
bash install.sh
```

Установщик:

1. ставит недостающие пакеты через `pacman` и AUR (при необходимости сначала соберёт `yay` и один раз спросит пароль sudo);
2. сохраняет прежний `~/.config/m2res` в `~/Backups/m2res/pre-install-*.tar.gz`;
3. копирует райс, подключает автозапуск и бинды и запускает `m2res-doctor`;
4. создаёт `~/.config/hypr/hyprland.lua` с базовыми биндами, если его нет.

Ключи:

| Флаг | Что делает |
|---|---|
| `--check` | Только проверяет зависимости и конфиг Hyprland, ничего не меняет |
| `--no-user` | Не ставит Whisper (~0,5 ГБ) и словарь OCR |
| `--no-enable` | Не трогает `hyprland.lua` |
| `--yes` | Не задаёт вопросов |
| `--info` | Показывает краткую справку по установщику |

После установки: `SUPER+F1` — шпаргалка по биндам.

## Удаление

```bash
~/.config/m2res/scripts/m2res-enable off
```

Убирает автозапуск и бинды из `hyprland.lua`. Резервная копия остаётся в `~/Backups/m2res/`.

## Документация

- [Полное руководство](.config/m2res/README.md) — райсы, скрипты, настройка
- [English version of this README](README.md)

<p align="center"><sub>Issues и pull requests приветствуются.</sub></p>
