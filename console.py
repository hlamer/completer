#!/usr/bin/env python

import sip
sip.setapi('QString', 2)

from PyQt4.QtCore import pyqtSignal, QSize, Qt
from PyQt4.QtGui import QApplication, QFontMetrics, QPalette, QSizePolicy, QStyle, \
                        QStyle, QStyleOptionFrameV2, \
                        QTextCursor, QTextEdit, QTextOption, QListView, QVBoxLayout, QWidget

import os
import sys

from htmldelegate import HTMLDelegate
import commands

from PyQt4.QtCore import QAbstractItemModel, QModelIndex
from PyQt4.QtGui import qApp, QFileSystemModel

class ListModel(QAbstractItemModel):
    def __init__(self):
        QAbstractItemModel.__init__(self)
        self._completer = None
        self._fsModel = QFileSystemModel()

    def index(self, row, column, parent):
        return self.createIndex(row, column)
    
    def parent(self, index):
        return QModelIndex()
    
    def rowCount(self, index):
        if self._completer is None:
            return 0
        
        return self._completer.count()
    
    def columnCount(self, index):
        return 2
    
    def data(self, index, role):
        if self._completer is None:
            return 0
        
        itemType, item = self._completer.item(index.row())
        if role == Qt.DisplayRole:
            if itemType == 'error':
                return self._formatError(item)
            elif itemType == 'currentDir':
                return self._formatCurrentDir(item)
            elif itemType in ('file', 'directory'):
                return self._formatPath(item)
            elif itemType == 'message':
                return self._formatMessage(item)
            else:
                assert False
        elif role == Qt.DecorationRole:
            if itemType == 'error':
                return qApp.style().standardIcon(QStyle.SP_MessageBoxCritical)
            elif itemType == 'currentDir':
                return None
            elif itemType in ('file', 'directory'):
                index = self._fsModel.index(os.path.join(self._completer.path, item))
                return self._fsModel.data(index, role)
            
        return None
    
    def flags(self, index):
        if self._completer is None:
            return 0
        
        retVal = QAbstractItemModel.flags(self, index)
        itemType, item = self._completer.item(index.row())
        if itemType in ('error', 'currentDir'):
            retVal &= ~Qt.ItemIsSelectable  # clear flag
        return retVal
    
    def setCompleter(self, completer):
        self._completer = completer
        self.modelReset.emit()

    def _formatPath(self, text):
        typedLen = self._completer.lastTypedSegmentLength()
        typedLenPlusInline = typedLen + len(self._completer.inline())
        return '<b>%s</b><u>%s</u>%s' % \
            (text[:typedLen],
             text[typedLen:typedLenPlusInline],
             text[typedLenPlusInline:])

    def _formatError(self, text):
        return '<i>%s</i>' % text
    
    def _formatCurrentDir(self, text):
        return '<font style="background-color: %s; color: %s">%s</font>' % \
                (qApp.palette().color(QPalette.Window).name(),
                 qApp.palette().color(QPalette.WindowText).name(),
                 text)
    
    def _formatMessage(self, text):
        return '<i>%s</i>' % text

class CompletableLineEdit(QTextEdit):
    tryToComplete = pyqtSignal()
    def __init__(self, *args):
        QTextEdit.__init__(self, *args)
        self.setTabChangesFocus(True)
        self.setWordWrapMode(QTextOption.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(self.sizeHint().height())
        self._inlineCompletion = None
        
    def sizeHint(self):
        fm = QFontMetrics(self.font())
        h = max(fm.height(), 14) + 4
        w = fm.width('x') * 17 + 4
        opt = QStyleOptionFrameV2()
        opt.initFrom(self);
        return self.style().sizeFromContents(QStyle.CT_LineEdit,
                                             opt,
                                             QSize(w, h).expandedTo(QApplication.globalStrut()),
                                             self)

    def event(self, event):
        if event.type() == event.KeyPress and \
           event.key() == Qt.Key_Tab:
            if self._inlineCompletion is not None:
                color = self.palette().color(QPalette.Base).name()
                self.insertHtml('<font style="background-color: %s">%s</font>' % (color, self._inlineCompletion))
                self._clearInlineCompletion()
                self.tryToComplete.emit()
            return True
        else:
            return QTextEdit.event(self, event)
    
    def keyPressEvent(self, event):
        self._clearInlineCompletion()
        QTextEdit.keyPressEvent(self, event)
        self.tryToComplete.emit()
    
    def mousePressEvent(self, event):
        self._clearInlineCompletion()
        QTextEdit.mousePressEvent(self, event)
        if self.textCursor().atEnd():
            self.tryToComplete.emit()

    def _clearInlineCompletion(self):
        if self._inlineCompletion is not None:
            cursor = self.textCursor()
            for c in self._inlineCompletion:
                cursor.deleteChar()
            self._inlineCompletion = None
    
    def setInlineCompletion(self, text):
        self._inlineCompletion = text
        cursor = self.textCursor()
        pos = cursor.position()
        color = self.palette().color(QPalette.Highlight).name()
        cursor.insertHtml('<font style="background-color: %s">%s</font>' % (color, text))
        cursor.setPosition(pos)
        self.setTextCursor(cursor)
    
    def text(self):
        return self.toPlainText()

class CommandConsole(QWidget):
    def __init__(self, *args):
        QWidget.__init__(self, *args)
        
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(1)
        
        self._list = QListView(self)
        self._model = ListModel()
        self._list.setModel(self._model)
        self._list.setItemDelegate(HTMLDelegate())
        self.layout().addWidget(self._list)
        
        self._edit = CompletableLineEdit(self)
        self.layout().addWidget(self._edit)
        self._edit.tryToComplete.connect(self._tryToComplete)
        self.setFocusProxy(self._edit)
        
        #self._list.hide()
        self._edit.setFocus()
        self._tryToComplete()

    def _tryToComplete(self):
        text = self._edit.toPlainText()
        completer = None
        
        command = commands.parseCommand(text)
        if command is not None:
                completer = command.completion(self._edit.textCursor().position())
        
        if completer is not None:
            inline = completer.inline()
            if inline:
                self._edit.setInlineCompletion(inline)
        
        self._model.setCompleter(completer)

def main():
    app = QApplication(sys.argv)
    w = CommandConsole()
    w.show()
    return app.exec_()

if __name__ == '__main__':
    main()
