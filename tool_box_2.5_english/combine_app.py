import sys
from PyQt5.QtWidgets import QApplication
from main import AirfoilApp  # 导入你的类
from multi_main import MultiElementApp

def run_combined():
    app = QApplication(sys.argv)
    
    # 实例化两个窗口
    win1 = AirfoilApp()
    win2 = MultiElementApp()
    
    # 同时显示
    win1.show()
    win2.show()
    
    # 统一进入事件循环
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_combined()