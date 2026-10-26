# Build on the target OS: python -m PyInstaller --noconfirm GetItDone.spec
from pathlib import Path
import sys

root = Path(SPECPATH)
import json
sys.path.insert(0, str(root))
from app.build_info import source_revision
metadata = root / 'build/build-info.json'
metadata.parent.mkdir(exist_ok=True)
metadata.write_text(json.dumps({'revision': source_revision(root / 'app')}), encoding='utf-8')
hidden = ['app.terminal.child', 'app.terminal.macos' if sys.platform != 'win32' else 'app.terminal.windows']
if sys.platform == 'darwin':
    hidden += ['UserNotifications', 'Foundation', 'objc']
if sys.platform == 'win32':
    hidden += ['winpty']
a = Analysis([str(root / 'app/main.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'app/terminal/web'), 'app/terminal/web'),
                        (str(root / 'app/ui/assets'), 'app/ui/assets'),
                        (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
                        (str(root / 'README.md'), '.'), (str(root / 'VALIDATION.md'), '.'),
                        (str(metadata), 'app')],
    hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6'], noarchive=False)
if sys.platform == 'darwin':
    # Qt's hook can mistake a stray Versions/Resources directory in the wheel
    # for the framework version. Keep helpers/resources beside the actual binary.
    framework = 'PySide6/Qt/lib/QtWebEngineCore.framework/Versions/'
    version = next(destination[len(framework):].split('/')[0]
                   for destination, source, kind in a.binaries
                   if destination.startswith(framework) and destination.endswith('/QtWebEngineCore'))
    def fix_webengine_location(entries):
        return [(destination.replace(framework + 'Resources/', framework + version + '/'), source, kind)
                for destination, source, kind in entries]
    a.binaries = fix_webengine_location(a.binaries)
    a.datas = fix_webengine_location(a.datas)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='GetItDone', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=str(root / 'scripts/entitlements.plist') if sys.platform == 'darwin' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='GetItDone')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='GetItDone.app', icon=None,
        bundle_identifier='de.getitdone.notebook',
        info_plist={'CFBundleDisplayName': 'GetItDone', 'CFBundleShortVersionString': '0.1.0',
                    'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '12.0',
                    'NSUserNotificationAlertStyle': 'alert'})
