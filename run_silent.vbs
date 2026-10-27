Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & Replace(WScript.ScriptFullName, "run_silent.vbs", "run_scheduled.bat") & chr(34), 0
Set WshShell = Nothing
