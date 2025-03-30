import sys
from app.ui import VMafTestApp
from PyQt5.QtWidgets import QApplication

def main():
    app = QApplication(sys.argv)
    window = VMafTestApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()