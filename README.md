# YouTube Downloader

## 다운로드
실행 파일은 다음 위치에서 다운로드할 수 있습니다:
- [최신 릴리스](None)
- [구글 드라이브]([https://drive.google.com/...](https://drive.google.com/file/d/1XmdQ_CVOjRwxcMsysKYtIg5aeB4Nzmxz/view?usp=sharing)

## 직접 빌드하기
소스 코드에서 직접 실행 파일을 빌드하려면:
```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --noupx --version-file=version_info.txt --icon=icon.ico --name="YouTube Downloader" main.py
