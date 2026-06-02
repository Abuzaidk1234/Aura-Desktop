from PyQt6.QtCore import QObject, pyqtSignal

class Communicate(QObject):
    toggle_click = pyqtSignal()
    wake_up = pyqtSignal()
    open_text_prompt = pyqtSignal()
    hide_avatar = pyqtSignal()
    show_avatar = pyqtSignal()
    exit_app = pyqtSignal()
    move_avatar = pyqtSignal(str)
    change_state = pyqtSignal(str)
    show_subtitle = pyqtSignal(str)
    start_pomodoro = pyqtSignal()
    initiate_shutdown = pyqtSignal(int)
