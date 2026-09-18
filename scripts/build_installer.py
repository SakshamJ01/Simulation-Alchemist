"""Desktop Application Executable & Installer Wizard Builder (Phase 4J).

Provides automated build scripts for compiling Simulation Alchemist into a
standalone desktop executable (.exe / binary) with PyInstaller and generating
Inno Setup / NSIS installer build definitions.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def generate_pyinstaller_spec(output_dir: Path, app_name: str = "SimulationAlchemist") -> Path:
    """Generate PyInstaller .spec file for standalone desktop execution."""
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['workbench/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('worlds', 'worlds'),
        ('figures', 'figures'),
    ],
    hiddenimports=[
        'sim_alchemist.core',
        'sim_alchemist.core.couplings',
        'sim_alchemist.core.sensitivity',
        'sim_alchemist.core.intelligent_search',
        'sim_alchemist.core.deep_surrogates',
        'sim_alchemist.core.rl_agents',
        'sim_alchemist.core.quantization',
        'sim_alchemist.core.distribution',
        'workbench.auth',
        'workbench.reporting',
        'flask',
        'numpy',
        'scipy',
        'yaml',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib.tests', 'numpy.tests', 'scipy.tests'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{app_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
"""
    spec_path = output_dir / f"{app_name}.spec"
    spec_path.write_text(spec_content, encoding="utf-8")
    return spec_path


def build_installer_script(app_name: str = "SimulationAlchemist", version: str = "1.0.0") -> str:
    """Generate Inno Setup script (.iss) for Windows Installer Wizard."""
    iss_content = f"""[Setup]
AppName={app_name}
AppVersion={version}
DefaultDirName={{autopf}}\\{app_name}
DefaultGroupName={app_name}
UninstallDisplayIcon={{app}}\\{app_name}.exe
Compression=lzma2
SolidCompression=yes
OutputDir=dist
OutputBaseFilename={app_name}_Setup_v{version}

[Files]
Source: "dist\\{app_name}\\{app_name}.exe"; DestDir: "{{app}}"; Flags: ignoreversion
Source: "dist\\{app_name}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{{group}}\\{app_name}"; Filename: "{{app}}\\{app_name}.exe"
Name: "{{commondesktop}}\\{app_name}"; Filename: "{{app}}\\{app_name}.exe"
"""
    return iss_content


def main() -> None:
    parser = argparse.ArgumentParser(description="Build desktop application standalone binary / installer.")
    parser.add_argument("--spec-only", action="store_true", help="Generate PyInstaller spec and installer definition only without compiling.")
    parser.add_argument("--name", default="SimulationAlchemist", help="Application name.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)

    spec_path = generate_pyinstaller_spec(project_root, app_name=args.name)
    print(f"Generated PyInstaller specification at: {spec_path}")

    iss_script = build_installer_script(app_name=args.name)
    iss_path = dist_dir / "installer_setup.iss"
    iss_path.write_text(iss_script, encoding="utf-8")
    print(f"Generated Inno Setup installer script at: {iss_path}")

    if not args.spec_only:
        print("Compiling standalone binary via PyInstaller...")
        subprocess.run([sys.executable, "-m", "PyInstaller", str(spec_path)], check=True)
        print("Build complete.")


if __name__ == "__main__":
    main()
