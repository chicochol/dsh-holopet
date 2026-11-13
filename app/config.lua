local config = {}

-- DSH 插件（dsh-holocubic）的地址：填运行 DSH 那台 PC 的局域网 IP
config.host = "192.168.1.100"
config.port = 17890
config.path = "/events"
config.state_path = "/state"
config.language = "system"

config.timeout_ms = 7000
config.reconnect_ms = 2000
config.stale_ms = 120000
config.watchdog_ms = 1000
config.serial_log = true

return config
