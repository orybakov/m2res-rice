-- m2res: запасные базовые бинды. Подключается ТОЛЬКО если у вас не было ~/.config/hypr/hyprland.lua
-- (установщик создал его сам). Свои бинды потом можно добавлять сюда или в hyprland.lua.
hl.bind("SUPER + return", hl.dsp.exec_cmd("uwsm app -- ghostty"))
hl.bind("SUPER + B", hl.dsp.exec_cmd("uwsm app -- google-chrome-stable"))
hl.bind("SUPER + E", hl.dsp.exec_cmd("uwsm app -- nautilus --new-window"))
hl.bind("SUPER + Q", hl.dsp.window.close())
for i = 1, 10 do
    local key = i % 10
    hl.bind("SUPER + " .. key, hl.dsp.focus({ workspace = i }))
    hl.bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end
hl.bind("SUPER + F", hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" }))
hl.bind("SUPER + M", hl.dsp.window.fullscreen({ mode = "maximized", action = "toggle" }))
hl.bind("SUPER + T", hl.dsp.window.float({ action = "toggle" }))
hl.bind("SUPER + J", hl.dsp.layout("togglesplit"))
hl.bind("SUPER + left", hl.dsp.focus({ direction = "left" }))
hl.bind("SUPER + right", hl.dsp.focus({ direction = "right" }))
hl.bind("SUPER + up", hl.dsp.focus({ direction = "up" }))
hl.bind("SUPER + down", hl.dsp.focus({ direction = "down" }))

-- ── бинды самого райса (на основной машине они лежат в hypr/lua/binds.lua) ──
local m2 = os.getenv("HOME") .. "/.config/m2res/scripts/"
hl.bind("SUPER + Tab", hl.dsp.exec_cmd(m2 .. "m2res-overview toggle"))
hl.bind("SUPER + CTRL + Tab", hl.dsp.focus({ workspace = "m+1" }))
hl.bind("SUPER + SHIFT + Tab", hl.dsp.focus({ workspace = "m-1" }))
hl.bind("SUPER + CTRL + down", hl.dsp.focus({ workspace = "empty" }))
hl.bind("SUPER + D", hl.dsp.exec_cmd(m2 .. "m2res-launcher toggle"))
hl.bind("SUPER + Escape", hl.dsp.exec_cmd(m2 .. "m2res-power toggle"))
hl.bind("SUPER + V", hl.dsp.exec_cmd(m2 .. "m2res-clip toggle"))
hl.bind("SUPER + X", hl.dsp.exec_cmd(m2 .. "m2res-control toggle"))
hl.bind("SUPER + CTRL + N", hl.dsp.exec_cmd(m2 .. "m2res-night toggle"))
hl.bind("SUPER + CTRL + SHIFT + G", hl.dsp.exec_cmd(m2 .. "m2res-game toggle"))
hl.bind("ALT + Tab", hl.dsp.exec_cmd(m2 .. "m2res-switch next"))
hl.bind("ALT + SHIFT + Tab", hl.dsp.exec_cmd(m2 .. "m2res-switch prev"))
hl.bind("SUPER + L", hl.dsp.exec_cmd("hyprlock -c " .. os.getenv("HOME") .. "/.config/m2res/lock/hyprlock.conf"))
hl.bind("Print", hl.dsp.exec_cmd(m2 .. "m2res-shot area"))
hl.bind("SHIFT + Print", hl.dsp.exec_cmd(m2 .. "m2res-shot edit"))
hl.bind("CTRL + Print", hl.dsp.exec_cmd(m2 .. "m2res-shot screen"))
hl.bind("ALT + Print", hl.dsp.exec_cmd(m2 .. "m2res-shot window"))
-- громкость и медиа (wpctl + playerctl; индикатор рисует m2res-volume)
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"), { locked = true, repeating = true })
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"), { locked = true })
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"), { locked = true })
hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"), { locked = true })

-- ── раскладка us/ru (переключение Win+Space) и автозапуск того, что нужно райсу ──
hl.config({ input = { kb_layout = "us,ru", kb_options = "grp:win_space_toggle", follow_mouse = 1 } })
hl.on("hyprland.start", function()
    hl.exec_cmd("hyprpaper")   -- обои (hyprpaper.conf создаёт установщик)
    hl.exec_cmd("hypridle")    -- автоблокировка (hypridle.conf создаёт установщик)
end)
