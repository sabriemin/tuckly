"""Not kartının metin alanı: yapılacaklar listesi, madde işaretleri, tıklanabilir bağlantılar.

Not, Markdown olarak saklanır (`md`); düz metin karşılığı (`text`) arama ve dışa aktarma içindir.
Eski sürümlerde yazılmış düz metin notlar olduğu gibi açılır.
"""

import re

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextListFormat,
)
from PySide6.QtWidgets import QFrame, QTextEdit

from .i18n import t

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
NO_MARKER = QTextBlockFormat.MarkerType.NoMarker
UNCHECKED = QTextBlockFormat.MarkerType.Unchecked
CHECKED = QTextBlockFormat.MarkerType.Checked


class LinkHighlighter(QSyntaxHighlighter):
    """Web adreslerini vurgu rengiyle ve altı çizili gösterir; belgeyi değiştirmez."""

    def __init__(self, document):
        super().__init__(document)
        self.color = QColor("#0a84ff")

    def highlightBlock(self, text):
        fmt = QTextCharFormat()
        fmt.setForeground(self.color)
        fmt.setFontUnderline(True)
        for m in URL_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), fmt)


class NoteEdit(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setObjectName("note")
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptRichText(False)  # yapıştırılan metin kendi yazı tipini ve rengini getirmesin
        self.setPlaceholderText(t("Buraya not yazın"))
        self.setToolTip("")
        self.links = LinkHighlighter(self.document())
        self._swallow_release = False

    # ---- Yükleme ve saklama
    def load(self, data: dict):
        self.blockSignals(True)
        if data.get("md") is not None:
            self.setMarkdown(data["md"])
        else:
            self.setPlainText(data.get("text", ""))
        # Qt, yapılacaklar listesinden sonraki düz paragrafa da onay kutusu işareti bırakabiliyor: temizle
        block = self.document().begin()
        while block.isValid():
            if block.textList() is None and block.blockFormat().marker() != NO_MARKER:
                fmt = block.blockFormat()
                fmt.setMarker(NO_MARKER)
                QTextCursor(block).setBlockFormat(fmt)
            block = block.next()
        self.document().setModified(False)
        self.blockSignals(False)

    def markdown(self) -> str:
        return self.toMarkdown()

    def set_accent(self, color: QColor):
        if color != self.links.color:
            self.links.color = QColor(color)
            self.links.rehighlight()

    # ---- Biçimlendirme: seçili metne (seçim yoksa imlecin altındaki sözcüğe ve yazılacak metne) uygulanır
    def _merge(self, fmt: QTextCharFormat):
        cur = self.textCursor()
        typing = not cur.hasSelection()
        if typing:
            cur.select(QTextCursor.WordUnderCursor)
        # Baştaki ve sondaki boşluklar biçime katılmaz: Markdown'da "*sözcük *" geçerli vurgu değildir
        start, end = cur.selectionStart(), cur.selectionEnd()
        text = cur.selectedText()
        start += len(text) - len(text.lstrip())
        end -= len(text) - len(text.rstrip())
        if end > start:
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.KeepAnchor)
        cur.mergeCharFormat(fmt)
        if typing:  # seçim yokken bundan sonra yazılacak metin de bu biçimi alır
            self.mergeCurrentCharFormat(fmt)

    def toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal if self.fontWeight() > QFont.Normal else QFont.Bold)
        self._merge(fmt)

    def toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.fontItalic())
        self._merge(fmt)

    def toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self.currentCharFormat().fontStrikeOut())
        self._merge(fmt)

    def toggle_heading(self):
        """Seçili satırları başlığa çevirir ya da düz metne döndürür."""
        blocks = self._blocks()
        make = any(b.blockFormat().headingLevel() == 0 for b in blocks)
        cur = self.textCursor()
        cur.beginEditBlock()
        for b in blocks:
            c = QTextCursor(b)
            bf = b.blockFormat()
            bf.setHeadingLevel(2 if make else 0)
            c.setBlockFormat(bf)
            c.select(QTextCursor.BlockUnderCursor)
            cf = QTextCharFormat()
            cf.setFontWeight(QFont.Bold if make else QFont.Normal)
            cf.setProperty(QTextFormat.FontSizeAdjustment, 2 if make else 0)
            c.mergeCharFormat(cf)
        cur.endEditBlock()

    def keyPressEvent(self, e):
        if e.modifiers() == Qt.ControlModifier and not self.isReadOnly():
            action = {Qt.Key_B: self.toggle_bold, Qt.Key_I: self.toggle_italic}.get(e.key())
            if action:
                action()
                e.accept()
                return
        super().keyPressEvent(e)

    # ---- Yapılacaklar ve madde işaretleri
    def _blocks(self):
        """Seçimin kapsadığı satırlar (seçim yoksa imlecin satırı)."""
        cur = self.textCursor()
        doc = self.document()
        block = doc.findBlock(cur.selectionStart())
        last = doc.findBlock(cur.selectionEnd())
        out = [block]
        while block != last and block.isValid():
            block = block.next()
            out.append(block)
        return out

    def _set_marker(self, block, marker):
        cur = QTextCursor(block)
        fmt = block.blockFormat()
        fmt.setMarker(marker)
        cur.setBlockFormat(fmt)
        # Tamamlanan maddenin üstü çizilir
        cur.select(QTextCursor.BlockUnderCursor)
        strike = QTextCharFormat()
        strike.setFontStrikeOut(marker == CHECKED)
        cur.mergeCharFormat(strike)

    def toggle_task(self):
        """Seçili satırları yapılacak maddesine çevirir; zaten maddeyse düz satıra döndürür."""
        blocks = self._blocks()
        make = any(b.blockFormat().marker() == NO_MARKER for b in blocks)
        cur = self.textCursor()
        cur.beginEditBlock()
        for b in blocks:
            if make:
                if b.textList() is None:
                    QTextCursor(b).createList(QTextListFormat.ListDisc)
                if b.blockFormat().marker() == NO_MARKER:
                    self._set_marker(b, UNCHECKED)
            else:
                self._set_marker(b, NO_MARKER)
                self._leave_list(b)
        cur.endEditBlock()

    def toggle_bullet(self):
        blocks = self._blocks()
        make = any(b.textList() is None for b in blocks)
        cur = self.textCursor()
        cur.beginEditBlock()
        for b in blocks:
            if make and b.textList() is None:
                QTextCursor(b).createList(QTextListFormat.ListDisc)
            elif not make:
                self._set_marker(b, NO_MARKER)
                self._leave_list(b)
        cur.endEditBlock()

    @staticmethod
    def _leave_list(block):
        lst = block.textList()
        if lst is not None:
            lst.remove(block)
            cur = QTextCursor(block)
            fmt = block.blockFormat()
            fmt.setIndent(0)
            cur.setBlockFormat(fmt)

    def counts(self):
        """(tamamlanan, toplam) yapılacak maddesi."""
        done = total = 0
        block = self.document().begin()
        while block.isValid():
            marker = block.blockFormat().marker()
            if marker != NO_MARKER and block.textList() is not None:
                total += 1
                done += marker == CHECKED
            block = block.next()
        return done, total

    # ---- Fare: onay kutusuna tıklama ve Ctrl+tıkla bağlantı açma
    def _task_at(self, pos):
        """pos, bir yapılacak maddesinin onay kutusunun üzerindeyse o satırı döndürür."""
        cur = self.cursorForPosition(pos)
        block = cur.block()
        if block.blockFormat().marker() == NO_MARKER or block.textList() is None:
            return None
        start = QTextCursor(block)
        text_x = self.cursorRect(start).left()
        rect = self.cursorRect(start)
        if text_x - 30 <= pos.x() < text_x - 2 and rect.top() - 2 <= pos.y() <= rect.bottom() + 2:
            return block
        return None

    def _url_at(self, pos):
        cur = self.cursorForPosition(pos)
        col = cur.positionInBlock()
        for m in URL_RE.finditer(cur.block().text()):
            if m.start() <= col <= m.end():
                return m.group(0).rstrip(".,;:!?)")
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.isReadOnly():
            block = self._task_at(e.position().toPoint())
            if block is not None:
                self._set_marker(block, UNCHECKED if block.blockFormat().marker() == CHECKED else CHECKED)
                self._swallow_release = True
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._swallow_release:
            self._swallow_release = False
            e.accept()
            return
        if e.button() == Qt.LeftButton and e.modifiers() & Qt.ControlModifier:
            url = self._url_at(e.position().toPoint())
            if url:
                QDesktopServices.openUrl(QUrl(url if "://" in url else "https://" + url))
                e.accept()
                return
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e):
        over = self._url_at(e.position().toPoint()) if e.modifiers() & Qt.ControlModifier else None
        self.viewport().setCursor(Qt.PointingHandCursor if over else Qt.IBeamCursor)
        super().mouseMoveEvent(e)
