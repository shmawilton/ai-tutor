"""Fingering chart viewer.

Loads instrument fingering/trill charts from ./charts (kept in the repo so they
are permanent). The fingering chart has no text layer, so note cells are located
by a fixed grid (4 cells per row) inside content bands found by a row-darkness
scan of the rendered page — each band contains one staff row + its diagrams.

FingeringView shows the crop for the currently played note; ChartDialog shows
whole pages scrollable (used for the full chart and the trill chart).
"""
import os

import numpy as np
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import theme
from theme import C

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS = {"flute": {"fingering": "charts/flute_fingering.pdf",
                    "trill": "charts/flute_trill.pdf"}}

RENDER_DPI = 150  # pixmaps are rendered once and reused for crops + dialogs

# midi -> (page, band_index, col) for the two-page flute chart. Bands are the
# staff+diagram rows found top-to-bottom on each page. Page 0: low + middle
# octave, 6 bands of 4 cells (C..B chromatic). Page 1: high octave, bands are
# [C D#], [E G], [G# A#], [B D7].
_P0_BASE, _P1_BASE = 60, 84


def _cell_for_midi(midi):
    if _P0_BASE <= midi < _P1_BASE:
        i = midi - _P0_BASE
        return 0, i // 4, i % 4
    if _P1_BASE <= midi <= 94:
        i = midi - _P1_BASE
        return 1, i // 4, i % 4
    if 95 <= midi <= 98:                      # B6 C7 C#7 D7 on the last band
        return 1, 3, midi - 95
    return None


def _render_pages(pdf_path, dpi=RENDER_DPI):
    """Render every page to (QPixmap, gray np array) — gray used for band scan."""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = QImage(pix.samples, pix.width, pix.height,
                     pix.stride, QImage.Format_RGB888).copy()
        arr = np.frombuffer(img.bits(), dtype=np.uint8)[:pix.height * pix.stride]
        gray = arr.reshape(pix.height, pix.stride)[:, :pix.width * 3:3]
        pages.append((QPixmap.fromImage(img), gray.astype(np.float32)))
    return pages


def _find_bands(gray, expect):
    """Locate `expect` note rows (label + staff + diagram).

    The diagrams themselves are too sparse for a darkness scan, so we anchor on
    the 5-line staves (dense continuous dark rows), then expand each staff into
    its cell band using the median staff-to-staff spacing."""
    h, w = gray.shape
    ink = (gray[:, int(w * 0.08):int(w * 0.95)] < 128).astype(np.float32)
    score = np.convolve(ink.mean(axis=1), np.ones(5) / 5, mode="same")
    limit = max(0.10, score.max() * 0.25)
    staves, start = [], None
    for y, on in enumerate(score > limit):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= 4:                # staff strips are ~10px tall
                staves.append((start, y))
            start = None
    if len(staves) < expect:
        return None
    staves = sorted(staves, key=lambda b: b[1] - b[0], reverse=True)[:expect]
    staves.sort()
    tops = [s[0] for s in staves]
    gaps = np.diff(tops)
    spacing = float(np.median(gaps)) if len(gaps) else h / expect
    return [(max(0, top - 0.20 * spacing), min(h, bot + 0.55 * spacing))
            for top, bot in staves]


class ChartDialog(QDialog):
    """Scrollable full-page view of a chart PDF (fingering / trill)."""

    def __init__(self, title, pdf_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 820)
        self._src = [pix for pix, _ in _render_pages(pdf_path)]
        self._labels = [QLabel() for _ in self._src]
        self._labels[0].setStyleSheet("background:white;")
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        for label in self._labels:
            label.setAlignment(Qt.AlignHCenter)
            label.setStyleSheet("background:white; border:1px solid #c8ccd2;")
            col.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        self._scroll = scroll
        self._fit()

    def _fit(self):
        width = self._scroll.viewport().width() - 14
        for label, pix in zip(self._labels, self._src):
            label.setPixmap(pix.scaledToWidth(max(200, width),
                                              Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class FingeringView(QWidget):
    """Cropped fingering diagram for the currently played note (flute for now)."""

    COLS = 4

    def __init__(self, instrument="flute", parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._note_label = ""
        self._crop = None
        self._ok = False
        try:
            charts = CHARTS[instrument]
            self._fingering_pdf = os.path.join(BASE_DIR, charts["fingering"])
            self._trill_pdf = os.path.join(BASE_DIR, charts["trill"])
            self._pages = _render_pages(self._fingering_pdf)
            self._bands = [_find_bands(gray, expect)
                           for expect, (_, gray) in zip((6, 4), self._pages)]
            self._ok = all(b is not None for b in self._bands)
        except Exception as e:
            print(f"Fingering chart unavailable: {e}")

    # ---- external API ----------------------------------------------------
    def set_note(self, midi, name):
        self._note_label = name or ""
        self._crop = None
        cell = _cell_for_midi(midi) if midi is not None else None
        if cell and self._ok:
            page_i, band_i, col = cell
            pix, _ = self._pages[page_i]
            y0, y1 = self._bands[page_i][band_i]
            w = pix.width()
            pad_y, pad_x = int(pix.height() * 0.01), int(w * 0.012)
            rect = QRect(int(w * 0.07 + col * w * 0.215) - pad_x,
                         max(0, y0 - pad_y),
                         int(w * 0.215) + 2 * pad_x,
                         min(pix.height() - y0, y1 - y0 + 2 * pad_y))
            self._crop = pix.copy(rect)
        self.update()

    # ---- painting --------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(C["card_edge"]), 1))
        p.setBrush(QColor(C["card"]))
        p.drawRoundedRect(rect, 10, 10)
        if not self._ok:
            p.setPen(QColor(C["faint"]))
            p.drawText(rect, Qt.AlignCenter, "Fingering chart not found")
            return
        p.setPen(QColor(C["subtext"]))
        head = QRectF(rect.left() + 10, rect.top() + 6, rect.width() - 20, 16)
        p.drawText(head, Qt.AlignLeft, f"Fingering {self._note_label}".rstrip())
        body = QRectF(rect.left() + 8, head.bottom() + 2,
                      rect.width() - 16, rect.bottom() - head.bottom() - 8)
        if self._crop is None:
            p.setPen(QColor(C["faint"]))
            p.drawText(body, Qt.AlignCenter, "Play a note C4 – D7")
            return
        scaled = self._crop.scaled(body.size().toSize(), Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
        target = QRectF(body.center().x() - scaled.width() / 2, body.top(),
                        scaled.width(), scaled.height())
        p.drawPixmap(target, self._crop, QRectF(self._crop.rect()))

    # ---- dialogs ---------------------------------------------------------
    def show_full_chart(self):
        self._dialog("Flute fingering chart", self._fingering_pdf)

    def show_trill_chart(self):
        self._dialog("Flute trill chart", self._trill_pdf)

    def _dialog(self, title, pdf):
        dialog = ChartDialog(title, pdf, self)
        dialog.exec()
