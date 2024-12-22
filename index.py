import sys
import os
import re
import threading
import concurrent.futures
import zipfile
import ssl
import certifi
import json
from datetime import timedelta
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLineEdit, QLabel, 
                           QProgressBar, QFileDialog, QButtonGroup, QRadioButton,
                           QSystemTrayIcon, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent
import yt_dlp
import requests

class FFmpegInstaller(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.ffmpeg_dir = os.path.join(os.path.expanduser('~'), '.ffmpeg')

    def run(self):
        try:
            if not self.check_ffmpeg():
                self.download_and_install_ffmpeg()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def check_ffmpeg(self):
        ffmpeg_path = os.path.join(self.ffmpeg_dir, 'ffmpeg.exe')
        return os.path.exists(ffmpeg_path)

    def download_and_install_ffmpeg(self):
        # FFmpeg 다운로드 URL (안정적인 버전 사용)
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        
        # 다운로드 디렉토리 생성
        os.makedirs(self.ffmpeg_dir, exist_ok=True)
        
        # FFmpeg 다운로드
        response = requests.get(ffmpeg_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        zip_path = os.path.join(self.ffmpeg_dir, 'ffmpeg.zip')
        block_size = 1024
        downloaded = 0
        
        with open(zip_path, 'wb') as f:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                f.write(data)
                progress = int((downloaded / total_size) * 100)
                self.progress.emit(progress)
        
        # 압축 해제
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.ffmpeg_dir)
        
        # 필요한 실행 파일만 이동
        extracted_dir = next(Path(self.ffmpeg_dir).glob('ffmpeg-*'))
        for file in ['ffmpeg.exe', 'ffprobe.exe']:
            src = extracted_dir / 'bin' / file
            dst = Path(self.ffmpeg_dir) / file
            if src.exists():
                os.replace(str(src), str(dst))
        
        # 임시 파일 정리
        os.remove(zip_path)
        import shutil
        shutil.rmtree(str(extracted_dir))

        # 환경 변수에 FFmpeg 경로 추가
        if sys.platform == 'win32':
            os.environ['PATH'] = f"{self.ffmpeg_dir};{os.environ['PATH']}"

class DownloadThread(QThread):
    progress = pyqtSignal(dict)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, format_type, download_path):
        super().__init__()
        self.url = url
        self.format_type = format_type
        self.download_path = download_path
        self.is_cancelled = False

    def progress_hook(self, d):
        if self.is_cancelled:
            raise Exception("Download cancelled")
            
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)

            progress_data = {
                'status': 'downloading',
                'downloaded_bytes': downloaded,
                'total_bytes': total,
                'speed': speed,
                'eta': eta,
                'percentage': (downloaded / total * 100) if total > 0 else 0
            }
            self.progress.emit(progress_data)

    def run(self):
        try:
            output_path = os.path.join(self.download_path, '%(title)s.%(ext)s')
            
            options = {
                'format': 'bestaudio/best' if self.format_type == 'mp3' else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                'outtmpl': output_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }] if self.format_type == 'mp3' else [],
                'progress_hooks': [self.progress_hook],
                'concurrent_fragment_downloads': 10,
                'buffersize': 1024 * 1024,
                'http_chunk_size': 10485760,
                'retries': 10,
                'fragment_retries': 10,
                'file_access_retries': 10,
                'extractor_retries': 10,
                'socket_timeout': 300,
                'noprogress': True,
            }

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(self.url, download=True)
                    filename = ydl.prepare_filename(info)
                    if self.format_type == 'mp3':
                        filename = os.path.splitext(filename)[0] + '.mp3'
                    self.finished.emit(filename)

        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self.is_cancelled = True

class VideoInfoThread(QThread):
    info_received = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            with yt_dlp.YoutubeDL() as ydl:
                info = ydl.extract_info(self.url, download=False)
                video_info = {
                    'title': info.get('title', ''),
                    'thumbnail_url': info.get('thumbnail', ''),
                    'duration': str(timedelta(seconds=info.get('duration', 0))),
                    'channel': info.get('uploader', '')
                }
                self.info_received.emit(video_info)
        except Exception as e:
            self.error.emit(str(e))

class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("미디어 다운로더")
        self.setMinimumWidth(600)
        self.setup_ui()
        self.setup_tray_icon()
        self.install_ffmpeg()

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2D2A4A;
            }
            QWidget {
                color: white;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit {
                padding: 8px;
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                color: white;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A47A3, stop:1 #3e3b8a);
                border: 1px solid #2d2a6e;
                color: white;
                min-width: 80px;
                outline: none;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5552bd, stop:1 #4744a1);
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3e3b8a, stop:1 #4A47A3);
            }
            QPushButton#downloadBtn {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFB347, stop:1 #ff9f2c);
                border: 1px solid #e59326;
                color: #2D2A4A;
                font-weight: bold;
            }
            QPushButton#cancelBtn {
                background-color: #ff6b6b;
                border: 1px solid #ff5252;
            }
            QPushButton#formatBtn {
                padding: 8px 16px;
                border-radius: 12px;
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.7);
                min-width: 100px;
            }
            QPushButton#formatBtn:checked {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFB347, stop:1 #ff9f2c);
                border: 1px solid #e59326;
                color: #2D2A4A;
                font-weight: bold;
            }
            QPushButton#formatBtn:hover {
                border-color: #FFB347;
            }
            QProgressBar {
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                text-align: center;
                color: white;
                background-color: rgba(255, 255, 255, 0.1);
            }
            QProgressBar::chunk {
                background-color: #FFB347;
                border-radius: 3px;
            }
        """)

        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)

        # FFmpeg 설치 진행률
        self.ffmpeg_progress = QProgressBar()
        self.ffmpeg_progress.hide()
        layout.addWidget(self.ffmpeg_progress)

        # 포맷 선택 버튼
        format_layout = QHBoxLayout()
        self.format_group = QButtonGroup(self)

        # MP4 버튼
        self.mp4_radio = QPushButton("MP4")
        self.mp4_radio.setCheckable(True)
        self.mp4_radio.setChecked(True)
        self.mp4_radio.setObjectName("formatBtn")
        self.mp4_radio.setIcon(QIcon("""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"></path><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
"""))

        # MP3 버튼
        self.mp3_radio = QPushButton("MP3")
        self.mp3_radio.setCheckable(True)
        self.mp3_radio.setObjectName("formatBtn")
        self.mp3_radio.setIcon(QIcon("""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
"""))

        # 버튼 그룹에 추가
        self.format_group.addButton(self.mp4_radio)
        self.format_group.addButton(self.mp3_radio)

        # 레이아웃에 추가
        format_layout.addWidget(self.mp4_radio)
        format_layout.addWidget(self.mp3_radio)
        format_layout.addStretch()
        layout.addLayout(format_layout)

        # URL 입력 및 다운로드 버튼
        input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube URL을 입력하세요")
        self.location_btn = QPushButton("저장 위치")
        self.download_btn = QPushButton("다운로드")
        self.download_btn.setObjectName("downloadBtn")
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.hide()
        
        input_layout.addWidget(self.url_input)
        input_layout.addWidget(self.location_btn)
        input_layout.addWidget(self.download_btn)
        input_layout.addWidget(self.cancel_btn)
        layout.addLayout(input_layout)

        # 비디오 정보 표시 영역
        self.video_info_widget = QWidget()
        video_info_layout = QVBoxLayout(self.video_info_widget)
        self.thumbnail_label = QLabel()
        self.title_label = QLabel()
        self.channel_label = QLabel()
        self.duration_label = QLabel()
        
        video_info_layout.addWidget(self.thumbnail_label)
        video_info_layout.addWidget(self.title_label)
        video_info_layout.addWidget(self.channel_label)
        video_info_layout.addWidget(self.duration_label)
        self.video_info_widget.hide()
        layout.addWidget(self.video_info_widget)
        # 진행률 표시 영역
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        self.progress_bar = QProgressBar()
        self.speed_label = QLabel()
        self.eta_label = QLabel()
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.speed_label)
        progress_layout.addWidget(self.eta_label)
        self.progress_widget.hide()
        layout.addWidget(self.progress_widget)

        # 상태 메시지
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        # 이벤트 연결
        self.location_btn.clicked.connect(self.select_directory)
        self.download_btn.clicked.connect(self.start_download)
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.url_input.textChanged.connect(self.fetch_video_info)

        # 초기 설정
        self.download_path = ""
        self.download_thread = None
        self.video_info_thread = None
        self.status_timer = None

        # 드래그 앤 드롭 활성화
        self.setAcceptDrops(True)

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon('icon.ico'))
        
        tray_menu = QMenu()
        show_action = tray_menu.addAction("보이기")
        quit_action = tray_menu.addAction("종료")
        
        show_action.triggered.connect(self.show)
        quit_action.triggered.connect(self.quit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def install_ffmpeg(self):
        self.ffmpeg_installer = FFmpegInstaller()
        self.ffmpeg_installer.progress.connect(self.ffmpeg_progress.setValue)
        self.ffmpeg_installer.progress.connect(lambda: self.ffmpeg_progress.show())
        self.ffmpeg_installer.finished.connect(self.ffmpeg_installation_finished)
        self.ffmpeg_installer.error.connect(lambda msg: self.show_status(f"FFmpeg 설치 오류: {msg}", "error", 5000))
        self.ffmpeg_installer.start()

    def ffmpeg_installation_finished(self):
        self.ffmpeg_progress.hide()
        self.show_status("FFmpeg 설치가 완료되었습니다.", "success", 3000)

    def validate_url(self, url):
        if not url:
            return False
        youtube_patterns = [
            r'^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'^https?://youtu\.be/[\w-]+',
            r'^https?://(?:www\.)?youtube\.com/shorts/[\w-]+'
        ]
        return any(re.match(pattern, url) for pattern in youtube_patterns)

    def select_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "저장 위치 선택")
        if dir_path:
            self.download_path = dir_path
            self.location_btn.setText("✓ 저장 위치")
            self.show_status("저장 위치가 선택되었습니다.", "success", 3000)

    def fetch_video_info(self):
        url = self.url_input.text()
        if not self.validate_url(url):
            self.video_info_widget.hide()
            return

        self.video_info_thread = VideoInfoThread(url)
        self.video_info_thread.info_received.connect(self.update_video_info)
        self.video_info_thread.error.connect(lambda msg: self.show_status(msg, "error", 3000))
        self.video_info_thread.start()

    def update_video_info(self, info):
        try:
            response = requests.get(info['thumbnail_url'])
            if response.ok:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                scaled_pixmap = pixmap.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled_pixmap)

            self.title_label.setText(f"제목: {info['title']}")
            self.channel_label.setText(f"채널: {info['channel']}")
            self.duration_label.setText(f"재생 시간: {info['duration']}")
            self.video_info_widget.show()
        except Exception as e:
            self.show_status(f"썸네일 로딩 중 오류: {str(e)}", "error", 3000)

    def start_download(self):
        if not self.url_input.text():
            self.show_status("URL을 입력해주세요.", "error", 3000)
            return
        if not self.download_path:
            self.show_status("다운로드 위치를 선택해주세요.", "error", 3000)
            return
        if not self.validate_url(self.url_input.text()):
            self.show_status("올바른 YouTube URL이 아닙니다.", "error", 3000)
            return

        self.download_btn.hide()
        self.cancel_btn.show()
        self.progress_widget.show()
        self.progress_bar.setValue(0)

        format_type = 'mp3' if self.mp3_radio.isChecked() else 'mp4'
        self.download_thread = DownloadThread(
            self.url_input.text(),
            format_type,
            self.download_path
        )
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.error.connect(self.handle_download_error)
        self.download_thread.start()

    def cancel_download(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait()
            self.show_status("다운로드가 취소되었습니다.", "info", 3000)
            self.cancel_btn.hide()
            self.download_btn.show()
            self.progress_widget.hide()

    def update_progress(self, data):
        try:
            percentage = data['percentage']
            speed = data['speed']
            eta = data['eta']

            self.progress_bar.setValue(int(percentage))
            
            # Adjust speed display with 20% compensation
            adjusted_speed = speed * 1.2
            self.speed_label.setText(f"다운로드 속도: {self.format_speed(adjusted_speed)}")
            self.eta_label.setText(f"남은 시간: {self.format_time(eta)}")
            
            if percentage >= 99.9:
                self.speed_label.setText("처리중...")
                self.eta_label.setText("곧 완료됩니다...")
                
        except Exception as e:
            print(f"Progress update error: {str(e)}")

    def handle_download_error(self, error):
        self.cancel_btn.hide()
        self.download_btn.show()
        self.progress_widget.hide()
        
        error_messages = {
            'RegexNotFoundError': '올바른 YouTube URL이 아닙니다.',
            'ExtractorError': '동영상을 찾을 수 없습니다.',
            'DownloadError': '다운로드 중 오류가 발생했습니다.',
            'UnavailableVideoError': '이 동영상은 다운로드할 수 없습니다.',
        }
        
        error_type = type(error).__name__
        message = error_messages.get(error_type, f'오류가 발생했습니다: {str(error)}')
        self.show_status(message, "error", 5000)

    def download_finished(self, filename):
        self.cancel_btn.hide()
        self.download_btn.show()
        self.progress_widget.hide()
        self.show_status("다운로드가 완료되었습니다!", "success", 3000)
        
        # 완료 알림
        self.tray_icon.showMessage(
            "다운로드 완료",
            f"파일이 저장되었습니다: {filename}",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )

    def show_status(self, message, status_type="info", duration=3000):
        color = {
            "error": "#ff6b6b",
            "success": "#51cf66",
            "info": "#ffffff"
        }.get(status_type, "#ffffff")
        
        self.status_label.setStyleSheet(f"color: {color}")
        self.status_label.setText(message)

        if self.status_timer is not None:
            self.status_timer.stop()
            self.status_timer.deleteLater()

        if duration > 0:
            self.status_timer = QTimer()
            self.status_timer.setSingleShot(True)
            self.status_timer.timeout.connect(lambda: self.status_label.clear())
            self.status_timer.start(duration)

    def format_speed(self, speed):
        if not speed:
            return "계산중..."
        return f"{speed / 1024 / 1024:.2f} MB/s"

    def format_time(self, seconds):
        if not seconds:
            return "계산중..."
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = [url.toLocalFile() for url in event.mimeData().urls()]
        if urls:
            self.url_input.setText(urls[0])

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "미디어 다운로더",
            "프로그램이 시스템 트레이로 최소화되었습니다.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def quit_application(self):
        QApplication.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec())