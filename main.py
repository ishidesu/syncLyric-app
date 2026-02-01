import sys
import os

from PySide6 import QtCore

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QFileDialog, QListWidget, QLabel,
    QTableWidget, QHeaderView, QTableWidgetItem, QAbstractItemView
)
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl

from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggopus import OggOpus

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SyncLyrics")
        self.setGeometry(200, 200, 1000, 600)
        
        if getattr(sys, 'frozen', False):
            script_dir = sys._MEIPASS
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.ASSET_PATH = os.path.join(script_dir, "assets")
        icon_path = os.path.join(self.ASSET_PATH, "icon.ico")
        self.setWindowIcon(QIcon(icon_path))
        
        # <----- {Audio Setup} ----->
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # <----- {Auto Scroll Function} ----->
        self.is_syncing = False
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100) # Every 100ms
        self.timer.timeout.connect(self.update_auto_scroll)
        self.timer.start()
        
        # <----- {UI Setup} ----->
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        # --- [Lyrics Editor Panel] ---
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Line", "Timeline", "Lyric"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.layout.addWidget(self.table)
        
        # --- [Load Button] ---
        self.btn_load_audio = QPushButton("Load Audio")
        self.btn_load_audio.clicked.connect(self.load_audio)
        self.layout.addWidget(self.btn_load_audio)
        
        self.btn_load_txt = QPushButton("Load txt")
        self.btn_load_txt.clicked.connect(self.load_txt)
        self.layout.addWidget(self.btn_load_txt)
        
        # --- [Start Song Button] ---
        self.btn_start = QPushButton("Start Song")
        self.btn_start.clicked.connect(self.start_audio)
        self.layout.addWidget(self.btn_start)
        
        # --- [Sync Button Control] ---
        self.btn_sync = QPushButton("Sync")
        self.btn_sync.clicked.connect(self.sync_audio)
        self.layout.addWidget(self.btn_sync)
        
        # --- [Undo Button] ---
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.clicked.connect(self.undo_sync)
        self.layout.addWidget(self.btn_undo)
        
        # --- [Save To Metadata] ---
        self.btn_save = QPushButton("Save to Metadata")
        self.btn_save.clicked.connect(self.save_metadata)
        self.layout.addWidget(self.btn_save)
        
        # --- {Data Temp} ---
        self.audio_path = ""
        self.synced_data = []
    
    # <----- {Program Logic} ----->
    
    # <----- {Front Function} ----->
    def load_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio Files (*.flac *.mp3 *.ogg)")
        if file_path:
            self.audio_path = file_path
            self.player.setSource(QUrl.fromLocalFile(file_path))
    
    def load_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Lyric", "", "Text Lyric (*.txt)")
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                self.table.setRowCount(len(lines))
                for i, text in enumerate(lines):
                    self.table.setItem(i, 0, QTableWidgetItem(str(i+1))) # Line number at left side
                    self.table.setItem(i, 1, QTableWidgetItem("--:--.--")) # Empty Timeline at middle
                    self.table.setItem(i, 2, QTableWidgetItem(text)) # Lyric at right side
            self.table.setCurrentCell(0, 1)
    
    def start_audio(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.is_syncing = False
            self.player.pause()
            self.btn_start.setText("Resume")
        else:
            self.is_syncing = True
            self.player.play()
            self.btn_start.setText("Pause Song")
    
    def sync_audio(self):
        row = self.table.currentRow()
        if row < self.table.rowCount() and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self.player.position()
            ts_now = self.format_time(pos)
            
            # Undo Logic
            current_undo_step = []
            current_undo_step.append((row, self.table.item(row, 1).text()))
            if row > 0:
                current_undo_step.append((row-1, self.table.item(row-1, 1).text()))
                
                self.synced_data.append(current_undo_step)
            
            self.table.item(row, 1).setData(256, ts_now) # 256 is custom row
            self.table.item(row, 1).setText(f"{ts_now} <-> --:--.--")
            
            if row > 0:
                ts_prev_start = self.table.item(row-1, 1).data(256)
                if ts_prev_start:
                    self.table.item(row-1, 1).setText(f"{ts_prev_start} <-> {ts_now}")
            
            self.table.setCurrentCell(row + 1, 1)
    
    def undo_sync(self):
        if self.synced_data:
            last_changes = self.synced_data.pop()
            for row_index, old_text in last_changes:
                self.table.item(row_index, 1).setText(old_text)
                
                if "<->" in old_text:
                    pure_ts = old_text.split(" <-> ")[0]
                    self.table.item(row_index,1 ).setData(256, pure_ts)
            
            target_row = last_changes[0][0]
            self.table.setCurrentCell(target_row, 1)
    
    def save_metadata(self):
        if not self.audio_path:
            return
        
        lines = []
        for i in range(self.table.rowCount()):
            display_text = self.table.item(i, 1).text()
            lyric_text = self.table.item(i, 2).text()
            
            if "<->" in display_text:
                start_ts = display_text.split(" <-> ")[0]
                lines.append(f"{start_ts}{lyric_text}")
            elif display_text != "--:--.--":
                lines.append(f"{display_text}{lyric_text}")
        
        full_lrc = "\n".join(lines)
        
        try:
            audio = FLAC(self.audio_path)
            audio["LYRICS"] = full_lrc
            audio.save()
        except Exception as e:
            print("Error: {e}")
    
    # <----- {Background Function} ----->
    
    def format_time(self, ms):
        m = int(ms / 60000)
        s = int((ms % 60000) / 1000)
        ms_part = int((ms % 1000) / 10)
        return f"[{m:02}:{s:02}.{ms_part:02}]"
    
    def update_auto_scroll(self):
        if self.is_syncing or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
        
        current_ms = self.player.position()
        
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if not item: continue
            
            start_ts = item.data(256)
            if not start_ts: continue
            
            start_ms = self.lrc_to_ms(start_ts)
            
            end_ms = float('inf')
            if row + 1 < self.table.rowCount():
                next_ts = self.table.item(row + 1, 1).data(256)
                if next_ts:
                    end_ms = self.lrc_to_ms(next_ts)
            
            if start_ms <= current_ms < end_ms:
                self.table.selectRow(row)
                self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                break
    
    def lrc_to_ms(self, lrc_time):
        try:
            clean_time = lrc_time.replace("[", "").replace("]", "")
            min_sec, centi = clean_time.split(".")
            mins, secs = min_sec.split(":")
            
            total_ms = (int(mins) * 60000) + (int(secs) * 1000) + (int(centi) * 10)
            return total_ms
        except:
            return 0

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())