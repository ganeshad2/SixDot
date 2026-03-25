import os
import sys
import threading
import webbrowser

from PySide6.QtCore import QEasingCurve, QEvent, QLibraryInfo, QPropertyAnimation, QTimer, Qt, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

qt_plugin_path = QLibraryInfo.path(QLibraryInfo.PluginsPath)
os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", qt_plugin_path)
os.environ.setdefault("QT_PLUGIN_PATH", qt_plugin_path)

import cv2
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from Easyocr_integration import detect_words_from_latest_capture
from lookup import run_motor, servo_lut, translate_word

from camera import (
    EXTERNAL_CAMERA_INDICES,
    get_camera_info,
    list_available_cameras,
    open_camera_by_index,
    open_external_camera,
    save_snapshot,
)


POSITION_TO_DOT_INDEX = {
    "top left": 0,
    "middle left": 1,
    "bot left": 2,
    "top right": 3,
    "middle right": 4,
    "bot right": 5,
}

MAX_TRANSCRIBABLE_WORD_LENGTH = 5
IDLE_TIMEOUT_MS = 10000
IDLE_FADE_DURATION_MS = 350


class BraillePreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.cells = []
        self.setMinimumHeight(170)
        self.setStyleSheet("background-color: #f8fafc; border: 1px solid #d9e0ea; border-radius: 18px;")

    def set_word(self, word):
        self.cells = []
        results = translate_word(word, servo_lut)
        for _, motors in results[:8]:
            active_positions = {motor["position"] for motor in motors}
            self.cells.append(
                [POSITION_TO_DOT_INDEX[position] for position in active_positions if position in POSITION_TO_DOT_INDEX]
            )
        self.update()

    def clear_preview(self):
        self.cells = []
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(rect, QColor("#f8fafc"))

        if not self.cells:
            painter.setPen(QColor("#7b8794"))
            painter.drawText(rect, Qt.AlignCenter, "Braille preview will appear here")
            return

        cell_count = len(self.cells)
        cell_width = rect.width() / max(cell_count, 1)
        dot_radius = max(5, min(12, int(min(cell_width / 8, rect.height() / 10))))
        left_column_x_offset = 0.35
        right_column_x_offset = 0.65
        row_y_offsets = (0.25, 0.5, 0.75)

        inactive_brush = QBrush(QColor("#d9e2ec"))
        active_brush = QBrush(QColor("#0f172a"))
        painter.setPen(QPen(QColor("#c7d2de"), 1))

        for cell_index, active_dots in enumerate(self.cells):
            cell_left = rect.left() + cell_index * cell_width
            dot_centers = [
                (cell_left + cell_width * left_column_x_offset, rect.top() + rect.height() * row_y_offsets[0]),
                (cell_left + cell_width * left_column_x_offset, rect.top() + rect.height() * row_y_offsets[1]),
                (cell_left + cell_width * left_column_x_offset, rect.top() + rect.height() * row_y_offsets[2]),
                (cell_left + cell_width * right_column_x_offset, rect.top() + rect.height() * row_y_offsets[0]),
                (cell_left + cell_width * right_column_x_offset, rect.top() + rect.height() * row_y_offsets[1]),
                (cell_left + cell_width * right_column_x_offset, rect.top() + rect.height() * row_y_offsets[2]),
            ]

            for dot_index, (center_x, center_y) in enumerate(dot_centers):
                painter.setBrush(active_brush if dot_index in active_dots else inactive_brush)
                painter.drawEllipse(
                    int(center_x - dot_radius),
                    int(center_y - dot_radius),
                    dot_radius * 2,
                    dot_radius * 2,
                )


# class BrandWordmarkWidget(QWidget):
#     def __init__(self):
#         super().__init__()
#         self.setMinimumHeight(84)
#         self.setMaximumHeight(84)
#         self.setStyleSheet(
#             "background-color: #050505;"
#             "border-radius: 18px;"
#         )

#     def paintEvent(self, event):
#         super().paintEvent(event)
#         painter = QPainter(self)
#         painter.setRenderHint(QPainter.Antialiasing)
#         painter.setRenderHint(QPainter.TextAntialiasing)

#         rect = self.rect().adjusted(12, 8, -12, -8)

#         painter.setPen(Qt.NoPen)
#         painter.setBrush(QColor("#050505"))
#         painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 18, 18)

#         wordmark_font = QFont("Bahnschrift", 32, QFont.DemiBold)
#         wordmark_font.setLetterSpacing(QFont.AbsoluteSpacing, 2.8)
#         wordmark_font.setStretch(92)
#         painter.setFont(wordmark_font)
#         painter.setPen(QColor("#f5f7fb"))
#         painter.drawText(rect, Qt.AlignCenter, "SIXDOT")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cap = None
        self.camera_index = None
        self.last_frame = None
        self.is_idle_screen_visible = False
        self.is_idle_fading_out = False
        self.idle_transition_mode = None

        self.idle_overlay = QWebEngineView(self)
        self.idle_transition_overlay = QLabel(self)
        self.idle_transition_overlay.setScaledContents(True)
        self.idle_transition_overlay.hide()
        self.idle_transition_effect = QGraphicsOpacityEffect(self.idle_transition_overlay)
        self.idle_transition_overlay.setGraphicsEffect(self.idle_transition_effect)
        self.idle_transition_effect.setOpacity(0.0)
        self.idle_fade_animation = QPropertyAnimation(self.idle_transition_effect, b"opacity", self)
        self.idle_fade_animation.setDuration(IDLE_FADE_DURATION_MS)
        self.idle_fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.idle_fade_animation.finished.connect(self._handle_idle_animation_finished)

        file_path = os.path.abspath("SixDot_Logo_html_IDLE.html")
        self.idle_overlay.setUrl(QUrl.fromLocalFile(file_path))

        self.idle_overlay.setStyleSheet("background-color: #000000;")
        self.idle_overlay.hide()  # start hidden

        self.setWindowTitle("SixDot Camera Control")
        self.resize(1100, 700)
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #edf2f7;
            }
            QLabel {
                color: #0f172a;
            }
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #d6dee8;
                border-radius: 14px;
                padding: 5px 12px;
                font-size: 14px;
                font-weight: 600;
                min-height: 14px;
                max-height: 32px;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #bfd0e2;
            }
            QPushButton:pressed {
                background-color: #eef2f7;
            }
            QPushButton#primaryButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #2563eb;
            }
            QPushButton#primaryButton:hover {
                background-color: #1d4ed8;
                border-color: #1d4ed8;
            }
            QPushButton#primaryButton:pressed {
                background-color: #1e40af;
                border-color: #1e40af;
            }
            QPushButton#dangerButton {
                background-color: #ffffff;
                color: #b42318;
                border: 1px solid #f0c4c1;
            }
            QPushButton#dangerButton:hover {
                background-color: #fff4f4;
                border-color: #eaa7a2;
            }
            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #d6dee8;
                border-radius: 14px;
                padding: 5px 10px;
                font-size: 12px;
                min-height: 14px;
                max-height: 32px;
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #d6dee8;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }
            """
        )

        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.show_idle_screen)
        self.idle_timer.start(IDLE_TIMEOUT_MS)

        self.setMouseTracking(True)

        self.video_label = QLabel("Starting camera...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(720, 420)
        self.video_label.setStyleSheet(
            "background-color: #111111;"
            "color: #f8fafc;"
            "border: none;"
            "border-radius: 16px;"
            "font-size: 18px;"
        )

        self.status_label = QLabel("Initializing...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "font-size: 13px;"
            "color: #52606d;"
            "background-color: transparent;"
            "padding: 4px 6px;"
        )

        self.brand_wordmark = QWebEngineView()

        file_path = os.path.abspath("SixDot_Logo_html.html")
        self.brand_wordmark.setUrl(QUrl.fromLocalFile(file_path))

        self.brand_wordmark.setFixedHeight(100)

        self.detected_word_title = QLabel("Detected Word:")
        self.detected_word_title.setStyleSheet(
            "font-size: 15px;"
            "font-weight: 600;"
            "color: #334155;"
            "padding-left: 2px;"
        )

        self.detected_word_value = QLabel("No word detected yet")
        self.detected_word_value.setAlignment(Qt.AlignCenter)
        self.detected_word_value.setMinimumHeight(96)
        self.detected_word_value.setMaximumHeight(96)
        self.detected_word_value.setWordWrap(True)
        self.detected_word_value.setFrameShape(QFrame.Box)
        self.detected_word_value.setStyleSheet(
            "background-color: #f8fafc;"
            "border: 1px solid #d9e0ea;"
            "border-radius: 16px;"
            "padding: 10px 14px;"
            "font-size: 34px;"
            "font-weight: 600;"
            "color: #0f172a;"
        )

        self.braille_preview_title = QLabel("Braille Output Preview:")
        self.braille_preview_title.setStyleSheet(
            "font-size: 15px;"
            "font-weight: 600;"
            "color: #334155;"
            "padding-left: 2px;"
        )
        self.braille_preview = BraillePreviewWidget()

        self.camera_selector = QComboBox()
        self.refresh_button = QPushButton("Refresh Cameras")
        self.connect_button = QPushButton("Connect Camera")
        self.save_button = QPushButton("Save Snapshot")
        self.ocr_button = QPushButton("Run OCR")
        self.info_button = QPushButton("Camera Info")
        self.quit_button = QPushButton("Quit")
        self.ocr_button.setObjectName("primaryButton")
        self.quit_button.setObjectName("dangerButton")

        self.refresh_button.clicked.connect(self.populate_camera_selector)
        self.connect_button.clicked.connect(self.handle_connect_camera)
        self.save_button.clicked.connect(self.handle_save_snapshot)
        self.ocr_button.clicked.connect(self.handle_run_ocr)
        self.info_button.clicked.connect(self.handle_camera_info)
        self.quit_button.clicked.connect(self.close)

        camera_label = QLabel("Camera Selection")
        camera_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")

        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(5)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(camera_label)
        controls_layout.addWidget(self.camera_selector)
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addWidget(self.connect_button)
        controls_layout.addWidget(self.save_button)
        controls_layout.addWidget(self.ocr_button)
        controls_layout.addWidget(self.info_button)
        controls_layout.addSpacing(6)
        controls_layout.addWidget(self.detected_word_title)
        controls_layout.addWidget(self.detected_word_value)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(self.quit_button)

        right_panel_layout = QVBoxLayout()
        right_panel_layout.setSpacing(6)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.addWidget(self.brand_wordmark)
        right_panel_layout.addLayout(controls_layout)

        video_card = QFrame()
        video_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dbe3ec; border-radius: 22px; }"
        )
        video_card_layout = QVBoxLayout(video_card)
        video_card_layout.setContentsMargins(12, 12, 12, 12)
        video_card_layout.addWidget(self.video_label)

        controls_card = QFrame()
        controls_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dbe3ec; border-radius: 22px; }"
        )
        controls_card_layout = QVBoxLayout(controls_card)
        controls_card_layout.setContentsMargins(16, 8, 16, 14)
        controls_card_layout.addLayout(right_panel_layout)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(16)
        top_layout.addWidget(video_card, stretch=3)
        top_layout.addWidget(controls_card, stretch=2)

        preview_card = QFrame()
        preview_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dbe3ec; border-radius: 22px; }"
        )
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 14, 18, 18)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(self.braille_preview_title)
        preview_layout.addWidget(self.braille_preview)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(14, 14, 14, 10)
        root_layout.setSpacing(10)
        root_layout.addLayout(top_layout, stretch=7)
        root_layout.addWidget(preview_card, stretch=3)
        root_layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(root_layout)
        self.setCentralWidget(container)
        container.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        self.populate_camera_selector()
        self.initialize_camera()

    def populate_camera_selector(self):
        available_cameras = list_available_cameras(EXTERNAL_CAMERA_INDICES)
        self.camera_selector.clear()

        if not available_cameras:
            self.camera_selector.addItem("No cameras found", None)
            self.connect_button.setEnabled(False)
            return

        for camera_index in available_cameras:
            self.camera_selector.addItem(f"Camera {camera_index}", camera_index)

        self.connect_button.setEnabled(True)

    def initialize_camera(self):
        cap, camera_index = open_external_camera(EXTERNAL_CAMERA_INDICES)

        if cap is None:
            self.video_label.setText("No camera connected.")
            self.status_label.setText(
                "Make sure the webcam is plugged in, then click Refresh Cameras."
            )
            self.save_button.setEnabled(False)
            self.ocr_button.setEnabled(True)
            self.info_button.setEnabled(False)
            return

        self.set_active_camera(cap, camera_index)

    def set_active_camera(self, cap, camera_index):
        self.release_camera()
        self.cap = cap
        self.camera_index = camera_index
        self.last_frame = None
        self.status_label.setText(f"Camera connected. {get_camera_info(self.camera_index)}")
        self.save_button.setEnabled(True)
        self.ocr_button.setEnabled(True)
        self.info_button.setEnabled(True)
        self.timer.start(30)

    def update_frame(self):
        if self.cap is None:
            return

        ret, frame = self.cap.read()
        if not ret:
            self.status_label.setText("Error: Failed to read frame.")
            self.timer.stop()
            return

        self.last_frame = frame.copy()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channel_count = rgb_frame.shape
        bytes_per_line = channel_count * width

        image = QImage(
            rgb_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(image)
        self.video_label.setPixmap(self.create_filled_pixmap(pixmap))

    def create_filled_pixmap(self, pixmap):
        target_size = self.video_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return pixmap

        scaled = pixmap.scaled(
            target_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )

        x_offset = max(0, (scaled.width() - target_size.width()) // 2)
        y_offset = max(0, (scaled.height() - target_size.height()) // 2)
        return scaled.copy(x_offset, y_offset, target_size.width(), target_size.height())

    def mouseMoveEvent(self, event):
        self.hide_idle_screen()
        self.reset_idle_timer()
        super().mouseMoveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() in {
            QEvent.MouseMove,
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.KeyPress,
            QEvent.TouchBegin,
        }:
            self.hide_idle_screen()
            self.reset_idle_timer()

        return super().eventFilter(watched, event)

    def reset_idle_timer(self):
        self.idle_timer.start(IDLE_TIMEOUT_MS)

    def show_idle_screen(self):
        if self.is_idle_screen_visible or self.is_idle_fading_out:
            return

        gui_snapshot = self.grab()
        self.idle_fade_animation.stop()
        self.idle_overlay.setGeometry(0, 0, self.width(), self.height())
        self.idle_overlay.show()
        self.idle_overlay.raise_()
        self.idle_transition_overlay.setGeometry(0, 0, self.width(), self.height())
        self.idle_transition_overlay.setPixmap(gui_snapshot)
        self.idle_transition_overlay.show()
        self.idle_transition_overlay.raise_()
        self.idle_transition_effect.setOpacity(1.0)
        self.idle_transition_mode = "fade_in_idle"
        self.is_idle_screen_visible = True
        self.idle_fade_animation.setStartValue(1.0)
        self.idle_fade_animation.setEndValue(0.0)
        self.idle_fade_animation.start()

    def hide_idle_screen(self):
        if not self.is_idle_screen_visible:
            return

        self.is_idle_screen_visible = False
        self.is_idle_fading_out = True
        self.idle_fade_animation.stop()
        self.idle_transition_overlay.setGeometry(0, 0, self.width(), self.height())
        self.idle_transition_overlay.setPixmap(self.idle_overlay.grab())
        self.idle_transition_overlay.show()
        self.idle_transition_overlay.raise_()
        self.idle_transition_effect.setOpacity(1.0)
        self.idle_overlay.hide()
        self.idle_transition_mode = "fade_out_idle"
        self.idle_fade_animation.setStartValue(1.0)
        self.idle_fade_animation.setEndValue(0.0)
        self.idle_fade_animation.start()

    def _handle_idle_animation_finished(self):
        if self.idle_transition_mode == "fade_in_idle":
            self.idle_transition_overlay.hide()
            self.idle_transition_overlay.clear()
            self.idle_transition_effect.setOpacity(0.0)
            self.idle_transition_mode = None
            return

        self.idle_transition_overlay.hide()
        self.idle_transition_overlay.clear()
        self.idle_transition_effect.setOpacity(0.0)
        self.is_idle_fading_out = False
        self.idle_transition_mode = None

    def handle_connect_camera(self):
        selected_index = self.camera_selector.currentData()
        if selected_index is None:
            self.status_label.setText("No selectable camera was found.")
            return

        cap, camera_index = open_camera_by_index(selected_index)
        if cap is None:
            self.status_label.setText(f"Unable to open camera {selected_index}.")
            return

        self.set_active_camera(cap, camera_index)

    def handle_save_snapshot(self):
        success, message, filepath = save_snapshot(self.last_frame, self.camera_index)
        if success and filepath is not None:
            self.status_label.setText(f"{message} Saved to: {filepath}")
        else:
            self.status_label.setText(message)

    def handle_camera_info(self):
        if self.camera_index is None:
            self.status_label.setText("No active camera.")
            return

        info = get_camera_info(self.camera_index)
        self.status_label.setText(info)
        QMessageBox.information(self, "Camera Info", info)

    def handle_run_ocr(self):
        self.status_label.setText("Running OCR on latest saved snapshot...")
        image_path, valid_words, error_message = detect_words_from_latest_capture()

        if error_message:
            self.detected_word_value.setText(error_message)
            self.braille_preview.clear_preview()
            self.status_label.setText(error_message)
            return

        transcribable_words = [word for word in valid_words if len(word) <= MAX_TRANSCRIBABLE_WORD_LENGTH]
        if not transcribable_words:
            message = f"No detected words fit the {MAX_TRANSCRIBABLE_WORD_LENGTH}-letter hardware limit."
            self.detected_word_value.setText(message)
            self.braille_preview.clear_preview()
            self.status_label.setText(f"{message} Using image: {image_path.name}.")
            return

        detected_word = transcribable_words[0]
        self.detected_word_value.setText(detected_word)
        self.braille_preview.set_word(detected_word)

        results = translate_word(detected_word, servo_lut)
        threading.Thread(target=run_motor, args=(results,), daemon=True).start()

        self.status_label.setText(
            f"OCR complete. Using image: {image_path.name}. "
            f"Transcribing '{detected_word}' ({len(detected_word)}/{MAX_TRANSCRIBABLE_WORD_LENGTH} letters). Motor output triggered."
        )

    def release_camera(self):
        self.timer.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def closeEvent(self, event):
        self.release_camera()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.idle_overlay.setGeometry(0, 0, self.width(), self.height())
        self.idle_transition_overlay.setGeometry(0, 0, self.width(), self.height())
        if self.last_frame is not None:
            self.update_frame()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
