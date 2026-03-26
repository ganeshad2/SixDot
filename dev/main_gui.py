import math
import os
import random
import sys
import threading
import time
import webbrowser

from PySide6.QtCore import QEasingCurve, QEvent, QLibraryInfo, QPropertyAnimation, QTimer, Qt, QUrl
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

qt_plugin_path = QLibraryInfo.path(QLibraryInfo.PluginsPath)
os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", qt_plugin_path)
os.environ.setdefault("QT_PLUGIN_PATH", qt_plugin_path)

import cv2
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from Easyocr_integration import detect_words_from_image
from lookup import run_motor, send_all_motors_home, servo_lut, translate_word

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
HOME_SETTLE_DELAY_SECONDS = 0.6


BRAILLE_ANIMATION_SEQUENCE = [
    ("S", [2, 3, 4]),
    ("I", [2, 4]),
    ("X", [1, 3, 4, 6]),
    ("D", [1, 4, 5]),
    ("O", [1, 3, 5]),
    ("T", [2, 3, 4, 5]),
]

BRAILLE_DOT_TO_INDEX = {1: 0, 4: 1, 2: 2, 5: 3, 3: 4, 6: 5}


class LocalHtmlView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_idle_variant = False
        self.animation_started_at = time.monotonic()
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update)
        self.animation_timer.start(33)
        self.stars = []
        self._init_starfield()

    def _init_starfield(self):
        rng = random.Random(42)
        self.stars = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "radius": rng.uniform(0.8, 2.2),
                "alpha": rng.uniform(0.08, 0.28),
                "speed": rng.uniform(0.9, 2.4),
                "phase": rng.uniform(0.0, math.tau),
            }
            for _ in range(130)
        ]

    def setUrl(self, url):
        filename = url.toLocalFile() if hasattr(url, "toLocalFile") else str(url)
        self.is_idle_variant = filename.endswith("SixDot_Logo_html_IDLE.html")
        self.update()

    def _timeline_state(self, elapsed_ms):
        letter_count = len(BRAILLE_ANIMATION_SEQUENCE)
        letters_visible = [False] * letter_count
        braille_visible = [False] * letter_count
        cursor_index = -1
        cursor_blinking = True
        tagline_progress = 0.0

        t = 300
        for idx in range(letter_count):
            if elapsed_ms >= t:
                letters_visible[idx] = True
                cursor_index = idx
            t += 140

        t += 700
        if elapsed_ms >= t - 120:
            cursor_blinking = False

        for idx in range(letter_count - 1, -1, -1):
            if elapsed_ms >= t:
                letters_visible[idx] = False
                cursor_index = idx - 1
            t += 135

        restart_cursor_at = t + 250
        if elapsed_ms >= restart_cursor_at:
            cursor_blinking = True
            cursor_index = -1

        t = restart_cursor_at + 150
        for idx in range(letter_count):
            if elapsed_ms >= t:
                braille_visible[idx] = True
                cursor_index = idx
            t += 190

        tagline_at = t - 100
        if elapsed_ms >= tagline_at:
            tagline_progress = min(1.0, (elapsed_ms - tagline_at) / 1000.0)

        t += 600
        if elapsed_ms >= t - 120:
            cursor_blinking = False

        for idx in range(letter_count - 1, -1, -1):
            if elapsed_ms >= t:
                braille_visible[idx] = False
                cursor_index = idx - 1
            t += 70

        reset_at = t + 200
        if elapsed_ms >= reset_at:
            cursor_blinking = True
            cursor_index = -1

        loop_duration = reset_at + 400
        return {
            "letters_visible": letters_visible,
            "braille_visible": braille_visible,
            "cursor_index": cursor_index,
            "cursor_blinking": cursor_blinking,
            "tagline_progress": tagline_progress,
            "loop_duration": loop_duration,
        }

    def _variant_metrics(self, rect):
        if self.is_idle_variant:
            dot_size = max(12.0, min(rect.width() / 38.0, rect.height() / 10.5))
            dot_gap = dot_size * 0.55
            col_gap = dot_size * 1.6
            letter_font_px = dot_size * 3.2
            tagline_font_px = dot_size * 0.75
            stage_offset_y = -dot_size * 0.5
        else:
            dot_size = max(8.0, min(rect.width() / 52.0, rect.height() / 8.5))
            dot_gap = dot_size * 0.6
            col_gap = dot_size * 1.8
            letter_font_px = dot_size * 2.7
            tagline_font_px = dot_size * 0.55
            stage_offset_y = dot_size * 1.1

        grid_width = (2 * dot_size) + dot_gap
        grid_height = (3 * dot_size) + (2 * dot_gap)
        return {
            "dot_size": dot_size,
            "dot_gap": dot_gap,
            "col_gap": col_gap,
            "grid_width": grid_width,
            "grid_height": grid_height,
            "letter_font_px": letter_font_px,
            "tagline_font_px": tagline_font_px,
            "stage_offset_y": stage_offset_y,
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111111"))

        now_ms = int((time.monotonic() - self.animation_started_at) * 1000)
        state = self._timeline_state(now_ms % self._timeline_state(0)["loop_duration"])
        rect = self.rect().adjusted(8, 8, -8, -8)
        metrics = self._variant_metrics(rect)

        self._paint_stars(painter, rect, now_ms)
        self._paint_animation(painter, rect, metrics, state, now_ms)

    def _paint_stars(self, painter, rect, now_ms):
        painter.save()
        painter.setPen(Qt.NoPen)
        for star in self.stars:
            twinkle = 0.5 + 0.5 * math.sin((now_ms / 1000.0) * star["speed"] + star["phase"])
            alpha = max(0.0, min(1.0, 0.15 + twinkle * star["alpha"]))
            color = QColor(255, 255, 255)
            color.setAlphaF(alpha)
            painter.setBrush(color)
            x = rect.left() + star["x"] * rect.width()
            y = rect.top() + star["y"] * rect.height()
            radius = star["radius"]
            painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2, radius * 2))
        painter.restore()

    def _paint_animation(self, painter, rect, metrics, state, now_ms):
        dot_size = metrics["dot_size"]
        dot_gap = metrics["dot_gap"]
        col_gap = metrics["col_gap"]
        grid_width = metrics["grid_width"]
        grid_height = metrics["grid_height"]
        display_width = len(BRAILLE_ANIMATION_SEQUENCE) * grid_width + (len(BRAILLE_ANIMATION_SEQUENCE) - 1) * col_gap
        start_x = rect.center().x() - (display_width / 2.0)
        center_y = rect.center().y() + metrics["stage_offset_y"]
        top_y = center_y - (grid_height / 2.0)

        letter_font = QFont("DejaVu Sans")
        letter_font.setBold(True)
        letter_font.setPixelSize(int(metrics["letter_font_px"]))

        active_dot = QColor("#ffffff")
        inactive_dot = QColor("#272727")
        text_color = QColor("#ffffff")

        painter.save()
        for idx, (letter, dots) in enumerate(BRAILLE_ANIMATION_SEQUENCE):
            cell_left = start_x + idx * (grid_width + col_gap)
            cell_rect = QRectF(cell_left, top_y, grid_width, grid_height)

            if state["letters_visible"][idx]:
                painter.setPen(text_color)
                painter.setFont(letter_font)
                painter.drawText(cell_rect, Qt.AlignCenter, letter)

            if state["braille_visible"][idx]:
                grid = [0, 0, 0, 0, 0, 0]
                for dot in dots:
                    grid[BRAILLE_DOT_TO_INDEX[dot]] = 1
                centers = [
                    (cell_left + (dot_size / 2.0), top_y + (dot_size / 2.0)),
                    (cell_left + dot_size + dot_gap + (dot_size / 2.0), top_y + (dot_size / 2.0)),
                    (cell_left + (dot_size / 2.0), top_y + dot_size + dot_gap + (dot_size / 2.0)),
                    (cell_left + dot_size + dot_gap + (dot_size / 2.0), top_y + dot_size + dot_gap + (dot_size / 2.0)),
                    (cell_left + (dot_size / 2.0), top_y + 2 * (dot_size + dot_gap) + (dot_size / 2.0)),
                    (cell_left + dot_size + dot_gap + (dot_size / 2.0), top_y + 2 * (dot_size + dot_gap) + (dot_size / 2.0)),
                ]
                painter.setPen(Qt.NoPen)
                for dot_idx, (cx, cy) in enumerate(centers):
                    painter.setBrush(active_dot if grid[dot_idx] else inactive_dot)
                    painter.drawEllipse(QRectF(cx - dot_size / 2.0, cy - dot_size / 2.0, dot_size, dot_size))

        self._paint_cursor(painter, top_y, grid_height, start_x, grid_width, col_gap, state, now_ms)
        self._paint_tagline(painter, rect, top_y + grid_height, metrics, state)
        painter.restore()

    def _paint_cursor(self, painter, top_y, grid_height, start_x, grid_width, col_gap, state, now_ms):
        cursor_index = state["cursor_index"]
        if cursor_index < 0:
            return

        if state["cursor_blinking"] and ((now_ms // 360) % 2 == 1):
            return

        cursor_width = 6 if self.is_idle_variant else 3
        cursor_x = start_x + ((cursor_index + 1) * grid_width) + (cursor_index * col_gap) + (col_gap * 0.5)
        cursor_rect = QRectF(cursor_x, top_y, cursor_width, grid_height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(cursor_rect, 2, 2)

    def _paint_tagline(self, painter, rect, grid_bottom, metrics, state):
        progress = state["tagline_progress"]
        if progress <= 0:
            return

        color = QColor(210, 210, 210)
        color.setAlphaF(min(0.85, progress * 0.85))
        font = QFont("DejaVu Sans")
        font.setPixelSize(int(metrics["tagline_font_px"]))
        font.setLetterSpacing(QFont.AbsoluteSpacing, max(2.0, metrics["tagline_font_px"] * 0.3))
        painter.setFont(font)
        painter.setPen(color)

        text_rect = QRectF(rect.left(), grid_bottom + metrics["dot_size"] * (1.6 if self.is_idle_variant else 1.0), rect.width(), metrics["tagline_font_px"] * 2.0)
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, "FEEL EVERY LETTER")


HtmlView = QWebEngineView or LocalHtmlView


class BraillePreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.cells = []
        self.labels = []
        self.setMinimumHeight(170)
        self.setStyleSheet("background-color: #f8fafc; border: 1px solid #d9e0ea; border-radius: 18px;")

    def set_word(self, word):
        self.cells = []
        self.labels = []
        results = translate_word(word, servo_lut)
        for letter, motors in results[:8]:
            active_positions = {motor["position"] for motor in motors}
            self.cells.append(
                [POSITION_TO_DOT_INDEX[position] for position in active_positions if position in POSITION_TO_DOT_INDEX]
            )
            self.labels.append(letter)
        self.update()

    def clear_preview(self):
        self.cells = []
        self.labels = []
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(rect, QColor("#f8fafc"))

        if not self.cells:
            painter.setPen(QColor("#7b8794"))
            painter.drawText(rect, Qt.AlignCenter, "Braille preview will appear here")
            return

        label_band_height = max(24, int(rect.height() * 0.18))
        braille_rect = QRectF(rect.left(), rect.top(), rect.width(), rect.height() - label_band_height)
        label_rect_top = braille_rect.bottom()

        cell_count = len(self.cells)
        cell_width = braille_rect.width() / max(cell_count, 1)
        dot_radius = max(5, min(12, int(min(cell_width / 8, braille_rect.height() / 10))))
        left_column_x_offset = 0.35
        right_column_x_offset = 0.65
        row_y_offsets = (0.24, 0.49, 0.74)

        inactive_brush = QBrush(QColor("#d9e2ec"))
        active_brush = QBrush(QColor("#0f172a"))
        painter.setPen(QPen(QColor("#c7d2de"), 1))

        label_font = QFont("DejaVu Sans")
        label_font.setPixelSize(max(12, min(18, int(label_band_height * 0.5))))
        label_font.setBold(True)

        for cell_index, active_dots in enumerate(self.cells):
            cell_left = braille_rect.left() + cell_index * cell_width
            dot_centers = [
                (cell_left + cell_width * left_column_x_offset, braille_rect.top() + braille_rect.height() * row_y_offsets[0]),
                (cell_left + cell_width * left_column_x_offset, braille_rect.top() + braille_rect.height() * row_y_offsets[1]),
                (cell_left + cell_width * left_column_x_offset, braille_rect.top() + braille_rect.height() * row_y_offsets[2]),
                (cell_left + cell_width * right_column_x_offset, braille_rect.top() + braille_rect.height() * row_y_offsets[0]),
                (cell_left + cell_width * right_column_x_offset, braille_rect.top() + braille_rect.height() * row_y_offsets[1]),
                (cell_left + cell_width * right_column_x_offset, braille_rect.top() + braille_rect.height() * row_y_offsets[2]),
            ]

            for dot_index, (center_x, center_y) in enumerate(dot_centers):
                painter.setBrush(active_brush if dot_index in active_dots else inactive_brush)
                painter.drawEllipse(
                    int(center_x - dot_radius),
                    int(center_y - dot_radius),
                    dot_radius * 2,
                    dot_radius * 2,
                )

            if cell_index < len(self.labels):
                painter.setFont(label_font)
                painter.setPen(QColor("#334155"))
                label_rect = QRectF(cell_left, label_rect_top, cell_width, label_band_height)
                painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignVCenter, self.labels[cell_index])
                painter.setPen(QPen(QColor("#c7d2de"), 1))


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
        self.frozen_frame = None
        self.preview_frozen = False
        self.is_idle_screen_visible = False
        self.is_idle_fading_out = False
        self.idle_transition_mode = None

        self.idle_overlay = HtmlView(self)
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

        self.brand_wordmark = HtmlView()

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
        self.connect_button = QPushButton("Connect Camera")
        self.capture_ocr_button = QPushButton("Capture + OCR")
        self.home_button = QPushButton("All Home")
        self.quit_button = QPushButton("Quit")
        self.capture_ocr_button.setObjectName("primaryButton")
        self.quit_button.setObjectName("dangerButton")

        self.connect_button.clicked.connect(self.handle_connect_camera)
        self.capture_ocr_button.clicked.connect(self.handle_capture_and_run_ocr)
        self.home_button.clicked.connect(self.handle_send_all_home)
        self.quit_button.clicked.connect(self.close)

        camera_label = QLabel("Camera Selection")
        camera_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")

        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(5)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(camera_label)
        controls_layout.addWidget(self.camera_selector)
        controls_layout.addWidget(self.connect_button)
        controls_layout.addWidget(self.capture_ocr_button)
        controls_layout.addWidget(self.home_button)
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
            self.capture_ocr_button.setEnabled(True)
            return

        self.set_active_camera(cap, camera_index)

    def set_active_camera(self, cap, camera_index):
        self.release_camera()
        self.cap = cap
        self.camera_index = camera_index
        self.last_frame = None
        self.frozen_frame = None
        self.preview_frozen = False
        self.status_label.setText(f"Camera connected. {get_camera_info(self.camera_index)}")
        self.capture_ocr_button.setEnabled(True)
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
        if self.preview_frozen:
            return

        self.display_frame(frame)

    def display_frame(self, frame):
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

    def handle_send_all_home(self):
        self.status_label.setText("Sending all motors to HOME position...")
        self.detected_word_value.setText("No word detected yet")
        self.braille_preview.clear_preview()
        self.preview_frozen = False
        self.frozen_frame = None
        if self.last_frame is not None:
            self.display_frame(self.last_frame)

        def worker():
            success = send_all_motors_home()
            if success:
                QTimer.singleShot(0, lambda: self.status_label.setText("All motors moved to HOME position."))
            else:
                QTimer.singleShot(0, lambda: self.status_label.setText("Motor drivers unavailable. Unable to send motors HOME."))

        threading.Thread(target=worker, daemon=True).start()

    def process_detected_word(self, word, image_name):
        self.detected_word_value.setText(word)
        self.braille_preview.set_word(word)

        def worker():
            home_success = send_all_motors_home()
            if home_success:
                time.sleep(HOME_SETTLE_DELAY_SECONDS)
            motor_success = run_motor(translate_word(word, servo_lut), hold_position=True)

            def update_status():
                if not home_success or not motor_success:
                    self.status_label.setText("Motor drivers unavailable. Braille preview updated, but motor output was skipped.")
                    return

                self.status_label.setText(
                    f"Using image: {image_name}. Transcribing '{word}' ({len(word)}/{MAX_TRANSCRIBABLE_WORD_LENGTH} letters)."
                )

            QTimer.singleShot(0, update_status)

        threading.Thread(target=worker, daemon=True).start()

    def handle_capture_and_run_ocr(self):
        self.status_label.setText("Capturing snapshot and running OCR...")
        success, message, filepath = save_snapshot(self.last_frame, self.camera_index)

        if success and self.last_frame is not None:
            self.frozen_frame = self.last_frame.copy()
            self.preview_frozen = True
            self.display_frame(self.frozen_frame)

        if not success or filepath is None:
            self.detected_word_value.setText(message)
            self.braille_preview.clear_preview()
            self.status_label.setText(message)
            return

        valid_words = detect_words_from_image(filepath)
        if not valid_words:
            self.detected_word_value.setText("No valid words found.")
            self.braille_preview.clear_preview()
            self.status_label.setText(f"No valid words found. Using image: {filepath.name}.")
            return

        transcribable_words = [word for word in valid_words if len(word) <= MAX_TRANSCRIBABLE_WORD_LENGTH]
        if not transcribable_words:
            message = f"No detected words fit the {MAX_TRANSCRIBABLE_WORD_LENGTH}-letter hardware limit."
            self.detected_word_value.setText(message)
            self.braille_preview.clear_preview()
            self.status_label.setText(f"{message} Using image: {filepath.name}.")
            return

        self.process_detected_word(transcribable_words[0], filepath.name)

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
