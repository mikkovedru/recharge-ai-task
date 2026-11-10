"""Generate the Windows executable's FileVersion and ProductVersion resource."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recharge_ai_task import __version__

parts = [int(part) for part in __version__.split('.')]
version = tuple((parts + [0] * 4)[:4])
Path(sys.argv[1]).write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'Recharge AI-task'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductName', 'Recharge AI-task'),
    StringStruct('ProductVersion', '{__version__}'),
    StringStruct('LegalCopyright', 'Recharge AI-task contributors; MIT license')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''')
