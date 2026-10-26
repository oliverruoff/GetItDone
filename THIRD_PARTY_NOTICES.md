# Third-party components

GetItDone uses the following independently licensed components. Corresponding license files and upstream sources remain authoritative.

- Python: Python Software Foundation License. https://www.python.org/psf/license/
- PySide6 / Shiboken / Qt, Qt WebEngine, Qt PDF: LGPL-3.0 / GPL / commercial licenses as applicable. Distributed as dynamically linked libraries; no modifications to Qt sources. Qt WebEngine contains Chromium and third-party code under additional licenses. https://www.qt.io/licensing/open-source-lgpl-obligations and https://code.qt.io/
- xterm.js 5.5.0 and addon-fit 0.10.0: MIT. Full notices are bundled in `app/terminal/web/LICENSE.xterm` and `LICENSE.addon-fit`. https://github.com/xtermjs/xterm.js
- python-docx: MIT. https://github.com/python-openxml/python-docx
- lxml: BSD and associated libxml2/libxslt licenses. https://lxml.de/copyright.html
- pywinpty (Windows): MIT. https://github.com/andfoy/pywinpty
- PyObjC (macOS): MIT. https://github.com/ronaldoussoren/pyobjc
- PyInstaller build bootloader: GPL with distribution exception. https://pyinstaller.org/en/stable/license.html

The source and build recipe in this repository allow users to rebuild GetItDone against replacement LGPL libraries. Public binary distributions must retain applicable license texts, Chromium notices and comply with the licenses of their chosen Qt distribution.
