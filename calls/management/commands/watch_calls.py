import os
import time
import datetime
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from django.conf import settings
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from calls.models import Call, User

class CallHandler(FileSystemEventHandler):
    def __init__(self, stdout):
        self.stdout = stdout

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        if not filename.endswith('_full.wav'):
            return

        self.stdout.write(f"Detected new file: {filename}")
        self.process_file(event.src_path)

    def process_file(self, wav_path):
        # Wait a brief moment to ensure file write is complete (optional but safer)
        time.sleep(1)

        try:
            # Logic similar to sync_calls, but for a single file
            # Path structure: .../caller_id/filename.wav
            dir_path = os.path.dirname(wav_path)
            caller_id = os.path.basename(dir_path)
            filename = os.path.basename(wav_path)

            # Extract Session ID
            base_name = filename.replace('_full.wav', '')
            parts = base_name.split('_')
            session_id = parts[1] if len(parts) >= 2 else base_name

            # Check if User exists
            user = User.objects.filter(phone_number=caller_id).first()
            if not user:
                self.stdout.write(self.style.WARNING(f"Ignored call from {caller_id}: User not registered."))
                return

            # Paths
            txt_filename = filename.replace('_full.wav', '_full.txt')
            txt_path = os.path.join(dir_path, txt_filename)

            # Metadata
            wav_size = os.path.getsize(wav_path)
            created_timestamp = os.path.getmtime(wav_path)
            created_at = make_aware(datetime.datetime.fromtimestamp(created_timestamp))

            txt_size = 0
            transfer_reasons = ""
            transfer_reason_descriptions = ""

            if os.path.exists(txt_path):
                txt_size = os.path.getsize(txt_path)
                try:
                    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        for line in content.splitlines():
                            if line.startswith('TRANSFER_REASONS:'):
                                transfer_reasons = line.replace('TRANSFER_REASONS:', '').strip()
                            if line.startswith('TRANSFER_REASON_DESCRIPTIONS:'):
                                transfer_reason_descriptions = line.replace('TRANSFER_REASON_DESCRIPTIONS:', '').strip()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error reading txt file: {e}"))

            # Create Call
            Call.objects.update_or_create(
                session_id=session_id,
                defaults={
                    'user': user,
                    'caller_id': caller_id,
                    'wav_filename': os.path.join(caller_id, filename), # Relative path
                    'txt_filename': txt_filename,
                    'wav_size': wav_size,
                    'txt_size': txt_size,
                    'created_at': created_at,
                    'transfer_reasons': transfer_reasons,
                    'transfer_reason_descriptions': transfer_reason_descriptions,
                }
            )
            self.stdout.write(self.style.SUCCESS(f"Processed call {session_id} for user {caller_id}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error processing file {wav_path}: {e}"))


class Command(BaseCommand):
    help = 'Watches for new call recordings and processes them in real-time'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='/usr/local/share/asterisk/sounds/call_sessions', help='Path to watch')

    def handle(self, *args, **options):
        path = options['path']
        if not os.path.exists(path):
            self.stdout.write(self.style.WARNING(f"Path {path} does not exist. Waiting..."))
            
        # Initial Scan
        self.stdout.write(f"Performing initial scan of {path}...")
        handler = CallHandler(self.stdout)
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('_full.wav'):
                    handler.process_file(os.path.join(root, file))
        self.stdout.write(self.style.SUCCESS("Initial scan complete."))

        self.stdout.write(f"Starting watchdog on {path}...")
        
        # We use the native Observer (Inotify on Linux) for efficient event sensing
        observer = Observer()
        observer.schedule(handler, path, recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
