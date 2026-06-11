"""Convert a .pptx to .pdf — PowerPoint COM first (best fidelity, colour emoji),
LibreOffice headless as a fallback."""

import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


def export_pdf(pptx_path: Path) -> bool:
    pdf_path = pptx_path.with_suffix(".pdf")
    if _via_powerpoint(pptx_path, pdf_path):
        return True
    if _via_soffice(pptx_path, pdf_path):
        return True
    return False


def _via_powerpoint(pptx_path: Path, pdf_path: Path) -> bool:
    try:
        import win32com.client
    except ImportError:
        return False
    powerpoint = None
    try:
        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        deck = powerpoint.Presentations.Open(
            str(pptx_path.resolve()), ReadOnly=True, WithWindow=False
        )
        deck.SaveAs(str(pdf_path.resolve()), 32)  # 32 = ppSaveAsPDF
        deck.Close()
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception as e:
        print(f"       PowerPoint export unavailable ({e}); trying LibreOffice ...")
        return False
    finally:
        try:
            if powerpoint is not None:
                powerpoint.Quit()
        except Exception:
            pass


@lru_cache(maxsize=1)
def _soffice_exe() -> str:
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for c in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if Path(c).exists():
            return c
    return ""


def _via_soffice(pptx_path: Path, pdf_path: Path) -> bool:
    exe = _soffice_exe()
    if not exe:
        return False
    profile = Path(tempfile.mkdtemp(prefix="sliderchat_lo_"))
    try:
        cmd = [
            exe, "--headless", "--norestore",
            f"-env:UserInstallation=file:///{profile.as_posix()}",
            "--convert-to", "pdf", "--outdir", str(pptx_path.parent.resolve()),
            str(pptx_path.resolve()),
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"       LibreOffice export failed ({e})")
        return False
    finally:
        shutil.rmtree(profile, ignore_errors=True)
