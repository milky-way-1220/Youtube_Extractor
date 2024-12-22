from cx_Freeze import setup, Executable
import sys

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": [
        "os", 
        "sys", 
        "re",
        "threading",
        "concurrent.futures",
        "zipfile",
        "ssl",
        "certifi",
        "json",
        "PyQt6",
        "yt_dlp",
        "requests"
    ],
    "excludes": [],
    "include_files": [
        "icon.ico",
    ],
    "include_msvcr": True,
}

# GUI applications require a different base on Windows
base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name="YouTube Downloader",
    version="1.0.0",
    description="YouTube Video Downloader with Auto FFmpeg Installation",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "index.py",  # 메인 파일명
            base=base,
            icon="icon.ico",  # 아이콘 파일
            target_name="YouTube Downloader.exe",  # 생성될 exe 파일명
            shortcut_name="YouTube Downloader",    # 시작 메뉴 바로가기 이름
            shortcut_dir="DesktopFolder"          # 바탕화면에 바로가기 생성
        )
    ]
)