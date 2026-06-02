Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "E:\Clippy"
WshShell.Run "pythonw main.py", 0, False
