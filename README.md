# YouTube Downloader

## 다운로드
실행 파일은 다음 위치에서 다운로드할 수 있습니다:
- [최신 릴리즈](https://1drv.ms/u/s!AvURSZSJYcaoiL9bY2uTvNPcbpF-QQ?e=xxRAYc)

## 직접 빌드하기
소스 코드에서 직접 실행 파일을 빌드하려면:
```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --noupx --version-file=version_info.txt --icon=icon.ico --name="YouTube Downloader" main.py
