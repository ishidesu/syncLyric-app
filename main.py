import sys
import os

from PySide6 import QtCore

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QFileDialog, QListWidget, QLabel,
    QTableWidget, QHeaderView, QTableWidgetItem, QAbstractItemView,
    QSizePolicy, QLineEdit, QSlider
)
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl, Qt, QPropertyAnimation, QEasingCurve

from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggopus import OggOpus

class LineNavWidget(QWidget):
    def __init__(self, table, line_number):
        super().__init__()
        self.table = table
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 0, 2, 0)
        self.layout.setSpacing(2)
        
        self.label = QLabel(str(line_number))
        self.layout.addWidget(self.label)
        
        self.btn_container = QWidget()
        self.btn_layout = QVBoxLayout(self.btn_container)
        self.btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_layout.setSpacing(0)
        
        self.btn_up = QPushButton("▲")
        self.btn_down = QPushButton("▼")
        
        for btn in [self.btn_up, self.btn_down]:
            btn.setFixedSize(16, 12)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    font-size: 8px;
                    border: none;
                    color: gray;
                }
                QPushButton:hover {
                    color: blue;
                }
            """)
            self.btn_layout.addWidget(btn)
            
        self.btn_up.clicked.connect(self.move_up)
        self.btn_down.clicked.connect(self.move_down)
        
        self.layout.addWidget(self.btn_container)
        self.btn_container.hide()
    
    def enterEvent(self, event):
        self.btn_container.show()
        return super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.btn_container.hide()
        return super().leaveEvent(event)
    
    def move_up(self):
        row = self.table.indexAt(self.pos()).row()
        if row > 0:
            self.swap_rows(row, row - 1)
    
    def move_down(self):
        row = self.table.indexAt(self.pos()).row()
        if row < self.table.rowCount() - 2:
            self.swap_rows(row, row + 1)
    
    def swap_rows(self, r1, r2):
        self.table.blockSignals(True)
        for col in range(self.table.columnCount()):
            item1 = self.table.takeItem(r1, col)
            item2 = self.table.takeItem(r2, col)
            self.table.setItem(r1, col, item2)
            self.table.setItem(r2, col, item1)
            
            w1 = self.table.cellWidget(r1, col)
            w2 = self.table.cellWidget(r2, col)
            if w1 or w2:
                t1 = w1.text() if hasattr(w1, 'text') else ""
                t2 = w2.text() if hasattr(w2, 'text') else ""
                
                if col == 2:
                    self.table.setCellWidget(r1, 2, HoverDeleteWidget(self.table, t2))
                    self.table.setCellWidget(r2, 2, HoverDeleteWidget(self.table, t1))
                elif col == 0:
                    self.table.setCellWidget(r1, 0, LineNavWidget(self.table, r1 + 1))
                    self.table.setCellWidget(r2, 0, LineNavWidget(self.table, r2 + 1))
        
        self.table.blockSignals(False)
        self.table.setCurrentCell(r2, 1)

class HoverDeleteWidget(QWidget):
    def __init__(self, table, initial_text=""):
        super().__init__()
        self.table = table
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 0, 5, 0)
        self.layout.setSpacing(0)

        self.lyric_label = QLineEdit(initial_text)
        self.lyric_label.setStyleSheet("background: transparent; border: none;")
        self.layout.addWidget(self.lyric_label)

        self.btn_delete = QPushButton("Delete Line")
        self.btn_delete.setFixedWidth(0)
        
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #ff4d4d;
                color: white;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #ff0000; }
        """)
        self.btn_delete.clicked.connect(self.delete_row)
        self.layout.addWidget(self.btn_delete)

        self.animation = QPropertyAnimation(self.btn_delete, b"minimumWidth")
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)

    def enterEvent(self, event):
        self.animation.setEndValue(80)
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animation.setEndValue(0)
        self.animation.start()
        super().leaveEvent(event)

    def delete_row(self):
        pos = self.mapTo(self.table.viewport(), self.rect().center())
        row = self.table.rowAt(pos.y())
        
        if row != -1:
            self.table.removeRow(row)
            for i in range(self.table.rowCount()):
                item = self.table.item(i, 0)
                if item: 
                    item.setText(str(i + 1))

    def text(self):
        return self.lyric_label.text()

    def setText(self, text):
        self.lyric_label.setText(text)

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
        self.DEFAULT_ARTWORK_PATH = os.path.join(self.ASSET_PATH, "default_artwork.png")
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
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalHeaderLabels(["Line", "Timeline", "Lyric"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        
        self.table.setDragEnabled(False)
        self.table.setAcceptDrops(False)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDropIndicatorShown(True)
        
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        
        self.table.itemChanged.connect(self.on_timeline_manual_edit)
        self.table.model().rowsMoved.connect(self.reorder_line_numbers)
        self.layout.addWidget(self.table)
        
        # --- {Bottom Panel Control} ---
        self.bottom_panel = QWidget()
        self.bottom_panel.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border-top: none;
            }
            QPushButton{
                background-color: #ffffff;
                border: 1px solid #bbb;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover{
                background-color: #e6e6e6;
            }
        """)
        
        bottom_layout = QVBoxLayout(self.bottom_panel)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        bottom_layout.setSpacing(10)
        
        top_buttons_widget = QWidget()
        top_buttons_layout = QHBoxLayout(top_buttons_widget)
        top_buttons_layout.setContentsMargins(0, 0, 0, 0)
        top_buttons_layout.setSpacing(8)
        top_buttons_layout.setAlignment(Qt.AlignLeft)
        
        # --- [Load Button] ---
        self.btn_load_audio = QPushButton("Load Audio")
        self.btn_load_audio.clicked.connect(self.load_audio)
        top_buttons_layout.addWidget(self.btn_load_audio)
        
        self.btn_load_txt = QPushButton("Load Lyric")
        self.btn_load_txt.clicked.connect(self.load_txt)
        top_buttons_layout.addWidget(self.btn_load_txt)
        
        # --- [Generate Lyric Button] ---
        self.btn_generate = QPushButton("Generate Lyric")
        # self.btn_generate.clicked.connect(self.generate_lyric)
        top_buttons_layout.addWidget(self.btn_generate)
        top_buttons_layout.addStretch()
        
        # --- [Sync Button Control] ---
        self.btn_sync = QPushButton("Sync")
        self.btn_sync.clicked.connect(self.sync_audio)
        top_buttons_layout.addWidget(self.btn_sync)
        
        # --- [Undo Button] ---
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.clicked.connect(self.undo_sync)
        top_buttons_layout.addWidget(self.btn_undo)
        top_buttons_layout.addStretch()
        
        # --- [Save To lrc] ---
        self.btn_save_lrc = QPushButton("Save to .lrc")
        self.btn_save_lrc.clicked.connect(self.save_lrc)
        top_buttons_layout.addWidget(self.btn_save_lrc)
        
        # --- [Save To Metadata] ---
        self.btn_save = QPushButton("Save to Metadata")
        self.btn_save.clicked.connect(self.save_metadata)
        top_buttons_layout.addWidget(self.btn_save)
        
        bottom_layout.addWidget(top_buttons_widget)
        
        # --- {Player Control Panel} ---
        player_section_widget = QWidget()
        player_section_layout = QHBoxLayout(player_section_widget)
        player_section_layout.setContentsMargins(0, 0, 0, 0)
        player_section_layout.setSpacing(15)
        
        # --- {Artwork} ---
        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(70, 70)
        self.artwork_label.setAlignment(Qt.AlignCenter)
        self.artwork_label.setStyleSheet("border: 1px solid #999; background-color: #ddd;")
        player_section_layout.addWidget(self.artwork_label)
        
        # --- {Title & Song Control} ---
        right_controls_widget = QWidget()
        right_controls_layout = QVBoxLayout(right_controls_widget)
        right_controls_layout.setContentsMargins(0, 0, 0, 0)
        right_controls_layout.setSpacing(5)
        
        # --- [Title] ---
        self.lbl_song_title = QLabel("No Audio Loaded")
        self.lbl_song_title.setStyleSheet("font-weight: bold; color: #333;")
        right_controls_layout.addWidget(self.lbl_song_title)
        
        # --- [Song Line Progress] ---
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #ddd;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 12px;
                height: 12px;
                margin: -4px 0; /* Menyeimbangkan posisi lingkaran ke tengah rel */
                border-radius: 6px; /* Membuat lingkaran murni */
            }
            QSlider::handle:horizontal:hover {
                background: #005a9e;
            }
        """)
        right_controls_layout.addWidget(self.progress_slider)
        
        # --- {Sub-row Play/Pause, Volume, Time Counter} ---
        sub_controls_widget = QWidget()
        sub_controls_layout = QHBoxLayout(sub_controls_widget)
        sub_controls_layout.setContentsMargins(0, 0, 0, 0)
        sub_controls_layout.setSpacing(10)
        
        # --- [Play/Pause] ---
        self.btn_start = QPushButton("⏸" if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState else "▶")
        self.btn_start.setFixedSize(35, 30)
        self.btn_start.clicked.connect(self.start_audio)
        sub_controls_layout.addWidget(self.btn_start)
        
        # --- [Volume] ---
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.audio_output.setVolume(0.5)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #ddd;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #666;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover {
                background: #333;
            }
        """)
        self.volume_slider.valueChanged.connect(lambda val: self.audio_output.setVolume(val / 100.0))
        sub_controls_layout.addWidget(QLabel("🔊"))
        sub_controls_layout.addWidget(self.volume_slider)
        
        # --- [Time Counter] ---
        self.lbl_time_counter = QLabel("00:00 / 00:00")
        self.lbl_time_counter.setStyleSheet("color: #555; font-family: Consolas;")
        sub_controls_layout.addStretch() # Beri space kosong
        sub_controls_layout.addWidget(self.lbl_time_counter)
        
        right_controls_layout.addWidget(sub_controls_widget)
        player_section_layout.addWidget(right_controls_widget, stretch=1)

        bottom_layout.addWidget(player_section_widget)

        self.layout.addWidget(self.bottom_panel)
        
        # --- {Data Temp} ---
        self.audio_path = ""
        self.synced_data = []
    
    # <----- {Program Logic} ----->
    
    # <----- {Front Function} ----->
    def add_newLine(self):
        current_plus_row = self.table.rowCount() - 1
                
        nav_widget = LineNavWidget(self.table, current_plus_row + 1)
        self.table.setCellWidget(current_plus_row, 0, nav_widget)
        self.table.setItem(current_plus_row, 1, QTableWidgetItem("--:--.--"))
        delete_widget = HoverDeleteWidget(self.table, "")
        self.table.setCellWidget(current_plus_row, 2, delete_widget)
        
        self.table.insertRow(current_plus_row + 1)
        self.add_plus_button_to_row(current_plus_row + 1)
        
        self.table.scrollToBottom()
    
    def load_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio Files (*.flac *.mp3 *.ogg)")
        if file_path:
            self.audio_path = file_path
            self.player.setSource(QUrl.fromLocalFile(file_path))
            
            self.load_artwork(file_path)
        
        self.lbl_song_title.setText(f"{os.path.basename(file_path)}")
            
        # Sinkronisasi Slider Durasi
        self.player.durationChanged.connect(lambda duration: self.progress_slider.setRange(0, duration))
        self.player.positionChanged.connect(self.on_player_position_changed)
        self.progress_slider.sliderMoved.connect(lambda pos: self.player.setPosition(pos))
    
    def load_artwork(self, file_path):
        from PySide6.QtGui import QPixmap
        
        ext = os.path.splitext(file_path)[1].lower()
        img_data = None
        
        try:
            if ext == '.flac':
                audio = FLAC(file_path)
                if audio.pictures:
                    img_data = audio.pictures[0].data
                    
            elif ext == '.mp3':
                audio = MP3(file_path)
                for tag in audio.tags.values():
                    if tag.Name == 'APIC':
                        img_data = tag.data
                        break
                        
            elif ext == '.ogg':
                audio = OggOpus(file_path)
                if 'metadata_block_picture' in audio:
                    from mutagen.flac import Picture
                    import base64
                    pic_data = base64.b64decode(audio['metadata_block_picture'][0])
                    picture = Picture(pic_data)
                    img_data = picture.data
        except Exception as e:
            print(f"Error reading artwork: {e}")
            
        if img_data:
            pixmap = QPixmap()
            if pixmap.loadFromData(img_data):
                scaled_pixmap = pixmap.scaled(
                    self.artwork_label.size(), 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                self.artwork_label.setPixmap(scaled_pixmap)
                return
        
        pixmap = QPixmap()
        if os.path.exists(self.DEFAULT_ARTWORK_PATH):
            pixmap.load(self.DEFAULT_ARTWORK_PATH)
            scaled_pixmap = pixmap.scaled(
                self.artwork_label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.artwork_label.setPixmap(scaled_pixmap)
        else:
            self.artwork_label.setPixmap(QPixmap())
    
    def load_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Lyric", "", "Text Lyric (*.txt)")
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                self.table.setRowCount(len(lines) + 1)
                
                for i, text in enumerate(lines):
                    nav_widget = LineNavWidget(self.table, i + 1)
                    self.table.setCellWidget(i, 0, nav_widget)
                    self.table.setItem(i, 1, QTableWidgetItem("--:--.--")) # Empty Timeline at middle                    
                    delete_widget = HoverDeleteWidget(self.table, text)
                    self.table.setCellWidget(i, 2, delete_widget)
                
                self.add_plus_button_to_row(len(lines))
                self.table.setCurrentCell(0, 1)
                
            self.table.setCurrentCell(0, 1)
    
    def start_audio(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.is_syncing = False
            self.player.pause()
            self.btn_start.setText("▶")
        else:
            self.is_syncing = True
            self.player.play()
            self.btn_start.setText("⏸")
    
    def on_player_position_changed(self, position):
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
            
        current_time = self.format_time(position).replace("[", "").replace("]", "")[:-3]
        total_duration = self.format_time(self.player.duration()).replace("[", "").replace("]", "")[:-3]
        self.lbl_time_counter.setText(f"{current_time} / {total_duration}")
    
    def sync_audio(self):
        row = self.table.currentRow()
        if row >= self.table.rowCount() - 1:
            return
        
        if row < self.table.rowCount() and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self.player.position()
            ts_now = self.format_time(pos)
            
            # Undo Logic
            current_undo_step = []
            current_undo_step.append((row, self.table.item(row, 1).text()))
            if row > 0:
                current_undo_step.append((row-1, self.table.item(row-1, 1).text()))
            self.synced_data.append(current_undo_step)
            
            ts_next_start = "--:--.--"
            self.table.item(row, 1).setData(256, ts_now)
            
            if row + 1 < self.table.rowCount() - 1:
                val = self.table.item(row + 1, 1).data(256)
                if val:
                    ts_next_start = val
            
            self.table.item(row, 1).setText(f"{ts_now} <-> {ts_next_start}")
            
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
    
    def save_lrc(self):
        if not self.audio_path:
            print("Error: No audio loaded to determine save path.")
            return
            
        lines = []
        for i in range(self.table.rowCount() - 1):
            display_text = self.table.item(i, 1).text()
            widget = self.table.cellWidget(i, 2)
            lyric_text = widget.text() if widget else ""
            
            if "<->" in display_text:
                start_ts = display_text.split(" <-> ")[0]
                lines.append(f"{start_ts}{lyric_text}")
            elif display_text != "--:--.--":
                lines.append(f"{display_text}{lyric_text}")
        
        full_lrc = "\n".join(lines)
        
        base_path = os.path.splitext(self.audio_path)[0]
        lrc_path = f"{base_path}.lrc"
        
        try:
            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write(full_lrc)
            print(f"Success: Lyric saved to {os.path.basename(lrc_path)}")
        except Exception as e:
            print(f"Error saving .lrc file: {e}")
    
    def save_metadata(self):
        if not self.audio_path:
            return
        
        lines = []
        for i in range(self.table.rowCount() - 1):
            display_text = self.table.item(i, 1).text()
            # lyric_text = self.table.item(i, 2).text()
            widget = self.table.cellWidget(i, 2)
            lyric_text = widget.text() if widget else ""
            
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
        
        for row in range(self.table.rowCount() - 1):
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
    
    def add_plus_button_to_row(self, row):
        btn_plus = QPushButton("+ Add New Line")
        btn_plus.setStyleSheet("""
            QPushButton {
                background-color:#f0f0f0;
                border: 1px dashed #ccc;
                color: #666;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        btn_plus.clicked.connect(self.add_newLine)
        self.table.setCellWidget(row, 2, btn_plus)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))
    
    def reorder_line_numbers(self):
        self.table.blockSignals(True)
        rows = self.table.rowCount()
        
        for i in range(rows - 1):
            line_item = self.table.item(i, 0)
            if line_item:
                line_item.setText(str(i + 1))
            else:
                self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
        
        current_timeline = self.table.item(i, 1)
        next_timeline = self.table.item(i + 1, 1)
        
        if current_timeline and next_timeline:
            ts_start = current_timeline.data(256) or "--:--.--"
            ts_next_start = next_timeline.data(256) or "--:--.--"

            if ts_start != "--:--.--":
                current_timeline.setText(f"{ts_start} <-> {ts_next_start}")
        
        if not self.table.cellWidget(i, 2):
            pass
        
        self.add_plus_button_to_row(rows - 1)
        self.table.blockSignals(False)
    
    def on_timeline_manual_edit(self, item):
        if item.column() != 1:
            return
        
        row = item.row()
        text = item.text()
        
        if " <-> " in text:
            ts_awal = text.split(" <-> ")[0]
            item.setData(256, ts_awal)
            
            if row > 0:
                prev_item = self.table.item(row - 1, 1)
                if prev_item:
                    p_text = prev_item.text()
                    if " <-> " in p_text:
                        p_awal = p_text.split(" <-> ")[0]
                        self.table.blockSignals(True)
                        prev_item.setText(f"{p_awal} <-> {ts_awal}")
                        self.table.blockSignals(False)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())