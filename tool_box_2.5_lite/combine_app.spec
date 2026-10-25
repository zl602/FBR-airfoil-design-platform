# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['combine_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 程序只依赖 PyQt5 / numpy / matplotlib；即使误用了装有大量库的环境打包，也不会把这些牵连进来
    excludes=['tkinter', 'scipy', 'pandas', 'IPython', 'jedi', 'numba', 'llvmlite',
              'torch', 'torchvision', 'torchaudio', 'transformers', 'onnxruntime',
              'cv2', 'sklearn', 'sympy', 'h5py', 'pygame', 'librosa'],
    noarchive=False,
    optimize=0,
)

# --- 精简 Qt：界面和 matplotlib 画布都走 CPU 光栅绘制，不需要 OpenGL/ANGLE、QML 或网络 ---
QT_DROP = {
    # 软件 OpenGL 与 ANGLE（opengl32sw / D3D 编译器 / GLES / EGL）
    'opengl32sw.dll', 'd3dcompiler_47.dll', 'libglesv2.dll', 'libegl.dll',
    # 只被下面几个插件引用的模块
    'qt5quick.dll', 'qt5qml.dll', 'qt5qmlmodels.dll', 'qt5network.dll',
    'qt5websockets.dll', 'qt5dbus.dll',
    # 插件：WebGL 平台（拉入 Quick/Qml/Network）、Linux 桌面门户（DBus）、TUIO 触控（Network）、minimal 平台
    'qwebgl.dll', 'qxdgdesktopportal.dll', 'qtuiotouchplugin.dll', 'qminimal.dll',
}

def _keep(entry):
    dest = entry[0].replace('\\', '/').lower()
    if dest.rsplit('/', 1)[-1] in QT_DROP:
        return False
    # Qt 翻译文件（程序未加载 QTranslator）
    if dest.startswith('pyqt5/qt5/translations/'):
        return False
    return True

a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='combine_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='combine_app',
)
